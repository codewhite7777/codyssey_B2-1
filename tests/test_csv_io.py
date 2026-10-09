import csv
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from budget_app.csv_io import CSV_COLUMNS
from budget_app.errors import ImportDataError, StorageError, ValidationError
from budget_app.models import transaction_key
from budget_app.service import BudgetService, export_filter
from tests.common import ServiceCase


class ImportTests(ServiceCase):
    def test_import_multiple_out_of_order_rows_and_fresh_ids(self):
        old = self.add(date="2026-10-02")
        source = self.csv_file([self.row(date="2026-10-01"), self.row(date="2026-10-03")])
        self.assertEqual(self.service.import_csv(source), 2)
        values = list(self.service.search())
        self.assertEqual([t.date for t in values], ["2026-10-03", "2026-10-02", "2026-10-01"])
        self.assertEqual(len({t.id for t in values}), 3)
        self.assertIn(old, values)

    def test_optional_columns_may_be_omitted(self):
        row = {k: v for k, v in self.row().items() if k in CSV_COLUMNS[:4]}
        source = self.csv_file([row], columns=CSV_COLUMNS[:4])
        self.assertEqual(self.service.import_csv(source), 1)
        value = list(self.service.search())[0]
        self.assertEqual((value.memo, value.tags), ("", ()))

    def test_csv_utf8_bom_crlf_multiline_and_quotes(self):
        memo = '점심, "커피"\r\n다음 줄'
        source = self.csv_file([self.row(memo=memo, tags="meal, lunch,meal,,")], encoding="utf-8-sig")
        self.assertEqual(self.service.import_csv(source), 1)
        value = list(self.service.search())[0]
        self.assertEqual(value.memo, memo)
        self.assertEqual(value.tags, ("meal", "lunch"))
        self.assertEqual(len((self.data / "transactions.jsonl").read_text(encoding="utf-8").splitlines()), 1)

    def test_bad_middle_row_rolls_back_all_three_files(self):
        self.add()
        before = self.snapshot()
        source = self.csv_file([self.row(amount="1"), self.row(amount="0"), self.row(amount="3")])
        with self.assertRaises(ImportDataError) as caught:
            self.service.import_csv(source)
        self.assertIn("3행", caught.exception.message)
        self.assertIn("imported=0", caught.exception.message)
        self.assertEqual(self.snapshot(), before)

    def test_unknown_category_whole_batch_unapplied(self):
        before = self.snapshot()
        source = self.csv_file([self.row(), self.row(category="unknown")])
        with self.assertRaises(ImportDataError) as caught:
            self.service.import_csv(source)
        self.assertIn("미등록", caught.exception.message)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_field_values_are_rejected(self):
        for changes in (dict(date="2026-02-30"), dict(date="2026-1-1"), dict(type="bad"),
                        dict(amount="-1"), dict(amount="1.2"), dict(amount="1,000"), dict(amount="0")):
            with self.subTest(changes=changes):
                before = self.snapshot()
                with self.assertRaises(ImportDataError):
                    self.service.import_csv(self.csv_file([self.row(**changes)]))
                self.assertEqual(self.snapshot(), before)

    def test_missing_duplicate_unknown_and_empty_header(self):
        texts = ["", "date,type,amount\n", "date,type,category,amount,amount\n",
                 "date,type,category,amount,id\n", "Date,type,category,amount\n"]
        for text in texts:
            with self.subTest(text=text):
                source = self.root / "header.csv"
                source.write_text(text, encoding="utf-8")
                with self.assertRaises(ImportDataError):
                    self.service.import_csv(source)

    def test_header_only_imports_zero_without_rewriting(self):
        source = self.csv_file([])
        before = self.snapshot()
        with patch.object(self.service.store.transactions, "replace_all", side_effect=AssertionError("no rewrite")):
            self.assertEqual(self.service.import_csv(source), 0)
        self.assertEqual(self.snapshot(), before)

    def test_extra_or_missing_row_columns(self):
        for line in ("2026-10-06,expense,food,1,memo,tags,extra\n", "2026-10-06,expense,food,1\n"):
            with self.subTest(line=line):
                source = self.root / "bad_shape.csv"
                source.write_text(",".join(CSV_COLUMNS) + "\n" + line, encoding="utf-8")
                with self.assertRaises(ImportDataError):
                    self.service.import_csv(source)

    def test_invalid_csv_quoting_rolls_back(self):
        source = self.root / "broken.csv"
        source.write_text('date,type,category,amount,memo,tags\n2026-10-06,expense,food,1,"unfinished,meal\n', encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(ImportDataError):
            self.service.import_csv(source)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_utf8_is_reported(self):
        source = self.root / "bad_encoding.csv"
        source.write_bytes(b"date,type,category,amount,memo,tags\n\xff\xfe")
        with self.assertRaises(ImportDataError):
            self.service.import_csv(source)

    def test_missing_file_is_oserror(self):
        before = self.snapshot()
        with self.assertRaises(FileNotFoundError):
            self.service.import_csv(self.root / "missing.csv")
        self.assertEqual(self.snapshot(), before)

    def test_reimport_duplicates_content_but_never_ids(self):
        source = self.csv_file([self.row()])
        self.service.import_csv(source)
        self.service.import_csv(source)
        values = list(self.service.search())
        self.assertEqual(len(values), 2)
        self.assertNotEqual(values[0].id, values[1].id)

    def test_import_replace_failure_preserves_existing(self):
        self.add()
        source = self.csv_file([self.row()])
        before = self.snapshot()
        with patch("budget_app.storage.os.replace", side_effect=OSError("fault")):
            with self.assertRaises(OSError):
                self.service.import_csv(source)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.data.glob("*.tmp")), [])

    def test_import_protected_storage_path(self):
        before = self.snapshot()
        with self.assertRaises(ValidationError):
            self.service.import_csv(self.data / "transactions.jsonl")
        self.assertEqual(self.snapshot(), before)

    def test_blank_csv_physical_lines_are_ignored(self):
        source = self.root / "blank_lines.csv"
        source.write_text("date,type,category,amount\n\n2026-10-06,expense,food,1\n\n", encoding="utf-8")
        self.assertEqual(self.service.import_csv(source), 1)


class ExportTests(ServiceCase):
    def test_export_month_and_exact_schema(self):
        self.add(date="2026-09-30")
        kept = self.add(date="2026-10-01")
        self.add(date="2026-11-01")
        target = self.root / "output.csv"
        self.assertEqual(self.service.export_csv(target, month="2026-10"), 1)
        with target.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames, list(CSV_COLUMNS))
            rows = list(reader)
        self.assertEqual(rows[0]["date"], kept.date)
        self.assertNotIn("id", rows[0])
        self.assertFalse(target.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_export_inclusive_range(self):
        self.add(date="2026-09-30")
        self.add(date="2026-10-01")
        self.add(date="2026-10-02")
        target = self.root / "output.csv"
        self.assertEqual(self.service.export_csv(target, start="2026-09-30", end="2026-10-01"), 2)

    def test_export_empty_outputs_header_only(self):
        target = self.root / "empty.csv"
        self.assertEqual(self.service.export_csv(target, month="2026-01"), 0)
        self.assertEqual(target.read_text(encoding="utf-8"), ",".join(CSV_COLUMNS) + "\n")

    def test_export_requires_unambiguous_complete_period(self):
        for fields in ({}, {"start": "2026-10-01"}, {"end": "2026-10-31"},
                       {"month": "2026-10", "start": "2026-10-01"},
                       {"start": "2026-10-31", "end": "2026-10-01"}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                self.service.export_csv(self.root / "out.csv", **fields)
        self.assertFalse((self.root / "out.csv").exists())

    def test_export_prevents_overwriting_all_internal_files_and_lock(self):
        before = self.snapshot()
        for name in ("transactions.jsonl", "categories.jsonl", "budgets.jsonl", ".budget_app.lock"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.service.export_csv(self.data / name, month="2026-10")
            self.assertEqual(self.snapshot(), before)

    def test_export_hardlink_alias_is_rejected(self):
        target = self.root / "alias.csv"
        try:
            target.hardlink_to(self.data / "transactions.jsonl")
        except (OSError, NotImplementedError):
            self.skipTest("hardlink unavailable")
        with self.assertRaises(ValidationError):
            self.service.export_csv(target, month="2026-10")

    def test_export_symlink_is_rejected(self):
        target = self.root / "alias.csv"
        try:
            target.symlink_to(self.data / "transactions.jsonl")
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        with self.assertRaises(ValidationError):
            self.service.export_csv(target, month="2026-10")

    def test_export_corrupt_input_preserves_old_output(self):
        self.add()
        target = self.root / "out.csv"
        target.write_bytes(b"old output")
        with (self.data / "transactions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("broken\n")
        with self.assertRaises(StorageError):
            self.service.export_csv(target, month="2026-10")
        self.assertEqual(target.read_bytes(), b"old output")
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_export_fsync_failure_preserves_old_output(self):
        self.add()
        target = self.root / "out.csv"
        target.write_bytes(b"old output")
        with patch("budget_app.storage.os.fsync", side_effect=OSError("fault")):
            with self.assertRaises(OSError):
                self.service.export_csv(target, month="2026-10")
        self.assertEqual(target.read_bytes(), b"old output")

    def test_export_missing_output_parent(self):
        with self.assertRaises(FileNotFoundError):
            self.service.export_csv(self.root / "missing" / "out.csv", month="2026-10")

    def test_export_import_roundtrip_preserves_business_fields_not_id(self):
        original = self.add(memo='한글, "메모"\n두 번째 줄', tags=("meal", "coffee"))
        target = self.root / "out.csv"
        self.service.export_csv(target, month="2026-10")
        other = BudgetService(self.root / "other")
        other.add_category("food")
        other.import_csv(target)
        imported = list(other.search())[0]
        self.assertNotEqual(original.id, imported.id)
        self.assertEqual((original.date, original.type, original.amount, original.category, original.memo, original.tags),
                         (imported.date, imported.type, imported.amount, imported.category, imported.memo, imported.tags))
