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
        """임시 폴더와 원본 바이트 파일을 만들어 교체 성공·실패 비교를 준비한다."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "records.jsonl"
        self.path.write_bytes(b"original\n")

    def assert_original(self):
        """원본 바이트가 그대로이며 남은 임시 파일이 없는지 공통으로 검사한다."""
        self.assertEqual(self.path.read_bytes(), b"original\n")
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_successful_replace(self):
        """임시 파일 작성을 마치면 새 내용으로 교체되고 임시 파일이 사라지는지 확인한다."""
        with atomic_text(self.path) as stream:
            stream.write("새로운 내용\n")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "새로운 내용\n")
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_writer_exception_preserves_original(self):
        """쓰기 도중 예외를 발생시켜 원본과 임시 파일 정리를 확인한다."""
        with self.assertRaises(ValueError):
            with atomic_text(self.path) as stream:
                stream.write("partial")
                raise ValueError("fault")
        self.assert_original()

    def test_interrupt_preserves_original(self):
        """쓰기 도중 KeyboardInterrupt를 발생시켜 취소해도 원본이 유지되는지 확인한다."""
        with self.assertRaises(KeyboardInterrupt):
            with atomic_text(self.path) as stream:
                stream.write("partial")
                raise KeyboardInterrupt
        self.assert_original()

    def test_fsync_failure_preserves_original(self):
        """동기화 실패를 주입해 원본 보존과 임시 파일 정리를 확인한다."""
        with patch("budget_app.storage.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                with atomic_text(self.path) as stream:
                    stream.write("replacement")
        self.assert_original()

    def test_replace_failure_preserves_original(self):
        """교체 시 권한 오류를 주입해 기존 파일이 유지되는지 확인한다."""
        with patch("budget_app.storage.os.replace", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                with atomic_text(self.path) as stream:
                    stream.write("replacement")
        self.assert_original()

    def test_temp_creation_failure_preserves_original(self):
        """임시 파일 생성 오류를 주입해 원본에 접근하거나 비우지 않는지 확인한다."""
        with patch("budget_app.storage.tempfile.mkstemp", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                with atomic_text(self.path):
                    pass
        self.assert_original()

    def test_temp_is_created_in_same_directory(self):
        """작성 중 임시 파일 위치가 원본과 같은 폴더인지 확인한다."""
        with atomic_text(self.path) as stream:
            temporary = list(self.root.glob("*.tmp"))
            self.assertEqual(len(temporary), 1)
            self.assertEqual(temporary[0].parent, self.path.parent)

    def test_write_unicode_and_newline_as_one_json_line(self):
        """한글·개행을 저장해 물리적 한 줄을 유지하고 읽을 때 원문이 복원되는지 확인한다."""
        with atomic_text(self.path) as stream:
            write_record(stream, {"memo": "점심, 커피\n다음 줄"})
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 1)
        self.assertEqual(list(iter_jsonl(self.path))[0][1]["memo"], "점심, 커피\n다음 줄")


class StoreSafetyTests(ServiceCase):
    def test_three_files_created(self):
        """서비스 초기화 후 세 JSONL 파일이 있고 작업 잠금은 정리되었는지 확인한다."""
        self.assertTrue(all((self.data / name).is_file() for name in DATA_NAMES))
        self.assertFalse((self.data / LOCK_NAME).exists())

    def test_new_directory_initializes_three_empty_files(self):
        """새 저장 폴더에 접근하면 세 빈 파일이 생성되는지 확인한다."""
        store = DataStore(self.root / "brand_new")
        with store.session():
            self.assertTrue(all((store.directory / name).is_file() for name in DATA_NAMES))
        self.assertTrue(all((store.directory / name).read_bytes() == b"" for name in DATA_NAMES))

    def test_missing_file_with_existing_data_is_not_recreated(self):
        """기존 저장 파일 하나를 제거해 유실 오류가 나고 조용히 재생성하지 않는지 확인한다."""
        (self.data / "transactions.jsonl").unlink()
        with self.assertRaises(StorageError):
            self.service.list_categories()
        self.assertFalse((self.data / "transactions.jsonl").exists())

    def test_partial_empty_initialization_can_recover(self):
        """아직 전부 빈 초기화 상태이면 없는 파일만 생성해 세 파일을 완성하는지 확인한다."""
        directory = self.root / "partial"
        directory.mkdir()
        (directory / "categories.jsonl").touch()
        with DataStore(directory).session():
            pass
        self.assertEqual(len(list(directory.glob("*.jsonl"))), 3)

    def test_file_replaced_by_directory_is_error(self):
        """저장 파일 위치에 폴더를 놓아 오류가 나고 잠금이 해제되는지 확인한다."""
        target = self.data / "budgets.jsonl"
        target.unlink()
        target.mkdir()
        with self.assertRaises(StorageError):
            self.service.list_categories()
        self.assertFalse((self.data / LOCK_NAME).exists())

    def test_storage_symlink_is_rejected(self):
        """내부 저장 파일을 외부 파일의 심볼릭 링크로 바꾸어 접근 거부와 외부 원본 보존을 확인한다."""
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
        """이미 잠금이 있을 때 두 번째 세션은 거부하고 첫 세션 종료 후 정상 접근하는지 확인한다."""
        with self.service.store.session():
            with self.assertRaises(ConflictError):
                self.service.list_categories()
        self.assertFalse((self.data / LOCK_NAME).exists())
        self.assertIn("food", self.service.list_categories())

    def test_stale_lock_not_silently_removed(self):
        """남은 잠금 파일을 임의로 지우지 않고 충돌 오류로 안내하는지 확인한다."""
        lock = self.data / LOCK_NAME
        lock.write_text("pid=999999999\n")
        with self.assertRaises(ConflictError):
            self.service.list_categories()
        self.assertTrue(lock.exists())

    def test_lock_released_on_exception(self):
        """세션 내부 오류가 발생해도 자신이 획득한 잠금 파일을 정리하는지 확인한다."""
        with self.assertRaises(RuntimeError):
            with self.service.store.session():
                raise RuntimeError("fault")
        self.assertFalse((self.data / LOCK_NAME).exists())

    def test_corrupt_json_blocks_mutation_and_preserves_bytes(self):
        """거래 뒤에 깨진 JSON을 추가해 행 번호 오류와 다음 쓰기의 원본 보존을 확인한다."""
        self.add()
        with (self.data / "transactions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("broken json\n")
        before = self.snapshot()
        with self.assertRaises(StorageError) as caught:
            self.add()
        self.assertIn(":2", caught.exception.message)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_stored_schema_cases(self):
        """잘못된 구조·값·카테고리 참조의 저장 레코드를 순회해 모두 거부되는지 확인한다."""
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
        """중복 JSON 키·NaN·빈 줄을 저장 손상으로 처리하는지 확인한다."""
        for text in ('{"name":"food","name":"rent"}\n', '{"name":NaN}\n', '\n'):
            with self.subTest(text=text):
                (self.data / "categories.jsonl").write_text(text, encoding="utf-8")
                with self.assertRaises(StorageError):
                    self.service.list_categories()

    def test_utf8_decode_error_is_application_error(self):
        """잘못된 저장 바이트를 읽으면 인코딩 예외 대신 StorageError로 안내하는지 확인한다."""
        (self.data / "transactions.jsonl").write_bytes(b"\xff\xfe\n")
        with self.assertRaises(StorageError):
            list(self.service.list_transactions())

    def test_unordered_file_is_rejected(self):
        """오래된 거래를 먼저 둔 파일을 만들어 저장 순서 오류가 검출되는지 확인한다."""
        records = [Transaction("a", "expense", "2026-01-01", 1, "food"),
                   Transaction("b", "expense", "2026-12-01", 1, "food")]
        with (self.data / "transactions.jsonl").open("w", encoding="utf-8") as stream:
            for record in records:
                write_record(stream, asdict(record))
        with self.assertRaises(StorageError):
            list(self.service.search())

    def test_limit_may_leave_later_corruption_unread_by_design(self):
        """limit=1은 첫 거래만 읽고 전체 검색은 뒤의 손상을 발견함을 확인해 검사 범위를 구분한다."""
        first = self.add()
        with (self.data / "transactions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("bad-json\n")
        self.assertEqual(list(self.service.list_transactions(1)), [first])
        with self.assertRaises(StorageError):
            list(self.service.search())

    def test_invalid_budget_records(self):
        """0원·필수 필드 누락·월 중복 예산을 저장 손상으로 거부하는지 확인한다."""
        for text in ('{"month":"2026-10","amount":0}\n', '{"month":"2026-10"}\n',
                     '{"month":"2026-10","amount":1}\n{"month":"2026-10","amount":2}\n'):
            with self.subTest(text=text):
                (self.data / "budgets.jsonl").write_text(text, encoding="utf-8")
                with self.assertRaises(StorageError):
                    self.service.get_budget("2026-10")

    def test_duplicate_category_records(self):
        """카테고리 파일의 같은 이름 중복을 오류로 발견하는지 확인한다."""
        (self.data / "categories.jsonl").write_text('{"name":"food"}\n{"name":"food"}\n', encoding="utf-8")
        with self.assertRaises(StorageError):
            self.service.list_categories()

    def test_update_and_delete_replace_failures_preserve_all_files(self):
        """수정과 삭제 각각의 교체 실패에서 원본·임시 파일·잠금 정리를 확인한다."""
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
        """전체 읽기를 금지한 스트림으로 저장소를 실행해 반복만 사용하고 파일을 닫는지 확인한다."""
        class IterationOnly(io.StringIO):
            def read(self, *args, **kwargs):
                """파일 전체 read 호출이 사용되면 테스트를 즉시 실패시키는 검사 대역이다."""
                raise AssertionError("whole-file read forbidden")
            def readlines(self, *args, **kwargs):
                """전체 행 수집이 사용되면 테스트를 즉시 실패시키는 검사 대역이다."""
                raise AssertionError("whole-file readlines forbidden")
        record = asdict(Transaction("id", "expense", "2026-10-06", 1, "food"))
        stream = IterationOnly(json.dumps(record) + "\n")
        with patch.object(Path, "open", return_value=stream):
            values = list(TransactionRepository(self.root / "unused").iter_transactions())
        self.assertEqual(len(values), 1)
        self.assertTrue(stream.closed)
