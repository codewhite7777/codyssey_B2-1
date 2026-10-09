import io
import json
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from budget_app.errors import ConflictError, StorageError
from budget_app.models import Transaction
from budget_app.storage import (
    DATA_NAMES, LOCK_NAME, DataStore, TransactionRepository, atomic_text, iter_jsonl, write_record,
)
from tests.common import ServiceCase


class AtomicFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "records.jsonl"
        self.path.write_bytes(b"original\n")

    def assert_original(self):
        self.assertEqual(self.path.read_bytes(), b"original\n")
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_successful_replace(self):
        with atomic_text(self.path) as stream:
            stream.write("새로운 내용\n")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "새로운 내용\n")
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_writer_exception_preserves_original(self):
        with self.assertRaises(ValueError):
            with atomic_text(self.path) as stream:
                stream.write("partial")
                raise ValueError("fault")
        self.assert_original()

    def test_interrupt_preserves_original(self):
        with self.assertRaises(KeyboardInterrupt):
            with atomic_text(self.path) as stream:
                stream.write("partial")
                raise KeyboardInterrupt
        self.assert_original()

    def test_fsync_failure_preserves_original(self):
        with patch("budget_app.storage.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                with atomic_text(self.path) as stream:
                    stream.write("replacement")
        self.assert_original()

    def test_replace_failure_preserves_original(self):
        with patch("budget_app.storage.os.replace", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                with atomic_text(self.path) as stream:
                    stream.write("replacement")
        self.assert_original()

    def test_temp_creation_failure_preserves_original(self):
        with patch("budget_app.storage.tempfile.mkstemp", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                with atomic_text(self.path):
                    pass
        self.assert_original()

    def test_temp_is_created_in_same_directory(self):
        with atomic_text(self.path) as stream:
            temporary = list(self.root.glob("*.tmp"))
            self.assertEqual(len(temporary), 1)
            self.assertEqual(temporary[0].parent, self.path.parent)

    def test_write_unicode_and_newline_as_one_json_line(self):
        with atomic_text(self.path) as stream:
            write_record(stream, {"memo": "점심, 커피\n다음 줄"})
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 1)
        self.assertEqual(list(iter_jsonl(self.path))[0][1]["memo"], "점심, 커피\n다음 줄")


class StoreSafetyTests(ServiceCase):
    def test_three_files_created(self):
        self.assertTrue(all((self.data / name).is_file() for name in DATA_NAMES))
        self.assertFalse((self.data / LOCK_NAME).exists())

    def test_new_directory_initializes_three_empty_files(self):
        store = DataStore(self.root / "brand_new")
        with store.session():
            self.assertTrue(all((store.directory / name).is_file() for name in DATA_NAMES))
        self.assertTrue(all((store.directory / name).read_bytes() == b"" for name in DATA_NAMES))

    def test_missing_file_with_existing_data_is_not_recreated(self):
        (self.data / "transactions.jsonl").unlink()
        with self.assertRaises(StorageError):
            self.service.list_categories()
        self.assertFalse((self.data / "transactions.jsonl").exists())

    def test_partial_empty_initialization_can_recover(self):
        directory = self.root / "partial"
        directory.mkdir()
        (directory / "categories.jsonl").touch()
        with DataStore(directory).session():
            pass
        self.assertEqual(len(list(directory.glob("*.jsonl"))), 3)

    def test_file_replaced_by_directory_is_error(self):
        target = self.data / "budgets.jsonl"
        target.unlink()
        target.mkdir()
        with self.assertRaises(StorageError):
            self.service.list_categories()
        self.assertFalse((self.data / LOCK_NAME).exists())

    def test_storage_symlink_is_rejected(self):
        target = self.data / "transactions.jsonl"
        target.unlink()
        outside = self.root / "outside"
        outside.write_text("safe", encoding="utf-8")
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        with self.assertRaises(StorageError):
            list(self.service.list_transactions())
        self.assertEqual(outside.read_text(), "safe")

    def test_lock_conflict_and_cleanup(self):
        with self.service.store.session():
            with self.assertRaises(ConflictError):
                self.service.list_categories()
        self.assertFalse((self.data / LOCK_NAME).exists())
        self.assertIn("food", self.service.list_categories())

    def test_stale_lock_not_silently_removed(self):
        lock = self.data / LOCK_NAME
        lock.write_text("pid=999999999\n")
        with self.assertRaises(ConflictError):
            self.service.list_categories()
        self.assertTrue(lock.exists())

    def test_lock_released_on_exception(self):
        with self.assertRaises(RuntimeError):
            with self.service.store.session():
                raise RuntimeError("fault")
        self.assertFalse((self.data / LOCK_NAME).exists())

    def test_corrupt_json_blocks_mutation_and_preserves_bytes(self):
        self.add()
        with (self.data / "transactions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("broken json\n")
        before = self.snapshot()
        with self.assertRaises(StorageError) as caught:
            self.add()
        self.assertIn(":2", caught.exception.message)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_stored_schema_cases(self):
        valid = dict(id="id", type="expense", date="2026-10-06", amount=1, category="food")
        invalid = [[], {**valid, "amount": 0}, {**valid, "tags": "meal"}, {**valid, "type": "bad"},
                   {**valid, "unexpected": 1}, {**valid, "category": "unknown"},
                   {**valid, "memo": 10}, {**valid, "tags": ["a", "a"]}]
        for record in invalid:
            with self.subTest(record=record):
                (self.data / "transactions.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
                with self.assertRaises(StorageError):
                    list(self.service.list_transactions())

    def test_duplicate_json_keys_and_non_json_numbers_rejected(self):
        for text in ('{"name":"food","name":"rent"}\n', '{"name":NaN}\n', '\n'):
            with self.subTest(text=text):
                (self.data / "categories.jsonl").write_text(text, encoding="utf-8")
                with self.assertRaises(StorageError):
                    self.service.list_categories()

    def test_utf8_decode_error_is_application_error(self):
        (self.data / "transactions.jsonl").write_bytes(b"\xff\xfe\n")
        with self.assertRaises(StorageError):
            list(self.service.list_transactions())

    def test_unordered_file_is_rejected(self):
        records = [Transaction("a", "expense", "2026-01-01", 1, "food"),
                   Transaction("b", "expense", "2026-12-01", 1, "food")]
        with (self.data / "transactions.jsonl").open("w", encoding="utf-8") as stream:
            for record in records:
                write_record(stream, asdict(record))
        with self.assertRaises(StorageError):
            list(self.service.search())

    def test_limit_may_leave_later_corruption_unread_by_design(self):
        first = self.add()
        with (self.data / "transactions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("bad-json\n")
        self.assertEqual(list(self.service.list_transactions(1)), [first])
        with self.assertRaises(StorageError):
            list(self.service.search())

    def test_invalid_budget_records(self):
        for text in ('{"month":"2026-10","amount":0}\n', '{"month":"2026-10"}\n',
                     '{"month":"2026-10","amount":1}\n{"month":"2026-10","amount":2}\n'):
            with self.subTest(text=text):
                (self.data / "budgets.jsonl").write_text(text, encoding="utf-8")
                with self.assertRaises(StorageError):
                    self.service.get_budget("2026-10")

    def test_duplicate_category_records(self):
        (self.data / "categories.jsonl").write_text('{"name":"food"}\n{"name":"food"}\n', encoding="utf-8")
        with self.assertRaises(StorageError):
            self.service.list_categories()

    def test_update_and_delete_replace_failures_preserve_all_files(self):
        transaction = self.add()
        before = self.snapshot()
        for operation in (lambda: self.service.update(transaction.id, amount=7), lambda: self.service.delete(transaction.id)):
            with patch("budget_app.storage.os.replace", side_effect=PermissionError("fault")):
                with self.assertRaises(PermissionError):
                    operation()
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(list(self.data.glob("*.tmp")), [])
            self.assertFalse((self.data / LOCK_NAME).exists())

    def test_stream_reader_uses_iteration_not_read_or_readlines(self):
        class IterationOnly(io.StringIO):
            def read(self, *args, **kwargs):
                raise AssertionError("whole-file read forbidden")
            def readlines(self, *args, **kwargs):
                raise AssertionError("whole-file readlines forbidden")
        record = asdict(Transaction("id", "expense", "2026-10-06", 1, "food"))
        stream = IterationOnly(json.dumps(record) + "\n")
        with patch.object(Path, "open", return_value=stream):
            values = list(TransactionRepository(self.root / "unused").iter_transactions())
        self.assertEqual(len(values), 1)
        self.assertTrue(stream.closed)
