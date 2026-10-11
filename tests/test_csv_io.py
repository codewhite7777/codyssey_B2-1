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
        """기존 거래에 날짜 순서가 섞인 CSV를 병합해 최신순과 ID 유일성을 확인한다."""
        old = self.add(date="2026-10-02")
        source = self.csv_file([self.row(date="2026-10-01"), self.row(date="2026-10-03")])
        self.assertEqual(self.service.import_csv(source), 2)
        values = list(self.service.search())
        self.assertEqual([t.date for t in values], ["2026-10-03", "2026-10-02", "2026-10-01"])
        self.assertEqual(len({t.id for t in values}), 3)
        self.assertIn(old, values)

    def test_optional_columns_may_be_omitted(self):
        """메모·태그 열을 생략한 CSV를 가져와 빈 선택값이 채워지는지 확인한다."""
        row = {k: v for k, v in self.row().items() if k in CSV_COLUMNS[:4]}
        source = self.csv_file([row], columns=CSV_COLUMNS[:4])
        self.assertEqual(self.service.import_csv(source), 1)
        value = list(self.service.search())[0]
        self.assertEqual((value.memo, value.tags), ("", ()))

    def test_csv_utf8_bom_crlf_multiline_and_quotes(self):
        """BOM·한글·쉼표·따옴표·여러 줄 메모를 가져와 원문과 태그 정리가 보존되는지 비교한다."""
        memo = '점심, "커피"\r\n다음 줄'
        source = self.csv_file([self.row(memo=memo, tags="meal, lunch,meal,,")], encoding="utf-8-sig")
        self.assertEqual(self.service.import_csv(source), 1)
        value = list(self.service.search())[0]
        self.assertEqual(value.memo, memo)
        self.assertEqual(value.tags, ("meal", "lunch"))
        self.assertEqual(len((self.data / "transactions.jsonl").read_text(encoding="utf-8").splitlines()), 1)

    def test_bad_middle_row_rolls_back_all_three_files(self):
        """정상 행 사이에 0원 행을 넣어 오류 위치·0건 반영·세 파일 원본 보존을 확인한다."""
        self.add()
        before = self.snapshot()
        source = self.csv_file([self.row(amount="1"), self.row(amount="0"), self.row(amount="3")])
        with self.assertRaises(ImportDataError) as caught:
            self.service.import_csv(source)
        self.assertIn("3행", caught.exception.message)
        self.assertIn("imported=0", caught.exception.message)
        self.assertEqual(self.snapshot(), before)

    def test_unknown_category_whole_batch_unapplied(self):
        """미등록 카테고리가 섞인 CSV의 전체 가져오기가 미반영되는지 확인한다."""
        before = self.snapshot()
        source = self.csv_file([self.row(), self.row(category="unknown")])
        with self.assertRaises(ImportDataError) as caught:
            self.service.import_csv(source)
        self.assertIn("미등록", caught.exception.message)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_field_values_are_rejected(self):
        """잘못된 날짜·타입·금액의 CSV를 각각 가져와 오류와 원본 보존을 확인한다."""
        for changes in (dict(date="2026-02-30"), dict(date="2026-1-1"), dict(type="bad"),
                        dict(amount="-1"), dict(amount="1.2"), dict(amount="1,000"), dict(amount="0")):
            with self.subTest(changes=changes):
                before = self.snapshot()
                with self.assertRaises(ImportDataError):
                    self.service.import_csv(self.csv_file([self.row(**changes)]))
                self.assertEqual(self.snapshot(), before)

    def test_missing_duplicate_unknown_and_empty_header(self):
        """누락·중복·알 수 없는 열과 빈 헤더를 가진 CSV를 거부하는지 확인한다."""
        texts = ["", "date,type,amount\n", "date,type,category,amount,amount\n",
                 "date,type,category,amount,id\n", "Date,type,category,amount\n"]
        for text in texts:
            with self.subTest(text=text):
                source = self.root / "header.csv"
                source.write_text(text, encoding="utf-8")
                with self.assertRaises(ImportDataError):
                    self.service.import_csv(source)

    def test_header_only_imports_zero_without_rewriting(self):
        """헤더만 있는 CSV는 0건이며 거래 파일 재작성 함수도 호출하지 않는지 확인한다."""
        source = self.csv_file([])
        before = self.snapshot()
        with patch.object(self.service.store.transactions, "replace_all", side_effect=AssertionError("no rewrite")):
            self.assertEqual(self.service.import_csv(source), 0)
        self.assertEqual(self.snapshot(), before)

    def test_extra_or_missing_row_columns(self):
        """헤더보다 열이 많거나 적은 행을 가진 CSV를 거부하는지 확인한다."""
        for line in ("2026-10-06,expense,food,1,memo,tags,extra\n", "2026-10-06,expense,food,1\n"):
            with self.subTest(line=line):
                source = self.root / "bad_shape.csv"
                source.write_text(",".join(CSV_COLUMNS) + "\n" + line, encoding="utf-8")
                with self.assertRaises(ImportDataError):
                    self.service.import_csv(source)

    def test_invalid_csv_quoting_rolls_back(self):
        """닫히지 않은 따옴표 CSV를 거부하고 기존 파일이 유지되는지 확인한다."""
        source = self.root / "broken.csv"
        source.write_text('date,type,category,amount,memo,tags\n2026-10-06,expense,food,1,"unfinished,meal\n', encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(ImportDataError):
            self.service.import_csv(source)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_utf8_is_reported(self):
        """UTF-8로 해석할 수 없는 바이트가 CSV 입력 오류로 바뀌는지 확인한다."""
        source = self.root / "bad_encoding.csv"
        source.write_bytes(b"date,type,category,amount,memo,tags\n\xff\xfe")
        with self.assertRaises(ImportDataError):
            self.service.import_csv(source)

    def test_missing_file_is_oserror(self):
        """없는 CSV 파일은 FileNotFoundError이고 기존 저장 파일은 그대로인지 확인한다."""
        before = self.snapshot()
        with self.assertRaises(FileNotFoundError):
            self.service.import_csv(self.root / "missing.csv")
        self.assertEqual(self.snapshot(), before)

    def test_reimport_duplicates_content_but_never_ids(self):
        """같은 CSV를 두 번 가져와 내용은 추가되지만 ID는 새로 생성되는지 확인한다."""
        source = self.csv_file([self.row()])
        self.service.import_csv(source)
        self.service.import_csv(source)
        values = list(self.service.search())
        self.assertEqual(len(values), 2)
        self.assertNotEqual(values[0].id, values[1].id)

    def test_import_replace_failure_preserves_existing(self):
        """가져오기 교체 단계에 오류를 주입해 원본 보존과 임시 파일 정리를 확인한다."""
        self.add()
        source = self.csv_file([self.row()])
        before = self.snapshot()
        with patch("budget_app.storage.os.replace", side_effect=OSError("fault")):
            with self.assertRaises(OSError):
                self.service.import_csv(source)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.data.glob("*.tmp")), [])

    def test_import_protected_storage_path(self):
        """내부 거래 파일을 CSV 입력으로 지정하면 거부되고 원본도 유지되는지 확인한다."""
        before = self.snapshot()
        with self.assertRaises(ValidationError):
            self.service.import_csv(self.data / "transactions.jsonl")
        self.assertEqual(self.snapshot(), before)

    def test_blank_csv_physical_lines_are_ignored(self):
        """완전히 빈 물리 행을 건너뛰고 실제 거래만 가져오는지 확인한다."""
        source = self.root / "blank_lines.csv"
        source.write_text("date,type,category,amount\n\n2026-10-06,expense,food,1\n\n", encoding="utf-8")
        self.assertEqual(self.service.import_csv(source), 1)


class ExportTests(ServiceCase):
    def test_export_month_and_exact_schema(self):
        """인접 월 거래를 섞어 대상 월만 내보내고 열 순서·ID 제외·BOM 없는 UTF-8을 확인한다."""
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
        """기간 양끝의 날짜를 포함한 정확한 건수가 내보내지는지 확인한다."""
        self.add(date="2026-09-30")
        self.add(date="2026-10-01")
        self.add(date="2026-10-02")
        target = self.root / "output.csv"
        self.assertEqual(self.service.export_csv(target, start="2026-09-30", end="2026-10-01"), 2)

    def test_export_empty_outputs_header_only(self):
        """거래가 없을 때 0건과 고정 헤더만 있는 CSV가 생성되는지 확인한다."""
        target = self.root / "empty.csv"
        self.assertEqual(self.service.export_csv(target, month="2026-01"), 0)
        self.assertEqual(target.read_text(encoding="utf-8"), ",".join(CSV_COLUMNS) + "\n")

    def test_export_requires_unambiguous_complete_period(self):
        """조건 누락·불완전 기간·월과 기간 혼용·역전 기간을 거부하고 파일도 생성하지 않는지 확인한다."""
        for fields in ({}, {"start": "2026-10-01"}, {"end": "2026-10-31"},
                       {"month": "2026-10", "start": "2026-10-01"},
                       {"start": "2026-10-31", "end": "2026-10-01"}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                self.service.export_csv(self.root / "out.csv", **fields)
        self.assertFalse((self.root / "out.csv").exists())

    def test_export_prevents_overwriting_all_internal_files_and_lock(self):
        """세 저장 파일과 잠금 파일을 출력 경로로 사용해 덮어쓰기가 차단되는지 확인한다."""
        before = self.snapshot()
        for name in ("transactions.jsonl", "categories.jsonl", "budgets.jsonl", ".budget_app.lock"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.service.export_csv(self.data / name, month="2026-10")
            self.assertEqual(self.snapshot(), before)

    def test_export_hardlink_alias_is_rejected(self):
        """내부 거래 파일의 하드링크를 CSV 출력으로 지정해 동일 파일 덮어쓰기를 차단하는지 확인한다."""
        target = self.root / "alias.csv"
        try:
            target.hardlink_to(self.data / "transactions.jsonl")
        except (OSError, NotImplementedError):
            self.skipTest("hardlink unavailable")
        with self.assertRaises(ValidationError):
            self.service.export_csv(target, month="2026-10")

    def test_export_symlink_is_rejected(self):
        """심볼릭 링크를 CSV 출력 대상으로 지정하면 거부하는지 확인한다."""
        target = self.root / "alias.csv"
        try:
            target.symlink_to(self.data / "transactions.jsonl")
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        with self.assertRaises(ValidationError):
            self.service.export_csv(target, month="2026-10")

    def test_export_corrupt_input_preserves_old_output(self):
        """거래 파일 뒤쪽에 손상을 넣어 내보내기 실패가 기존 CSV를 바꾸지 않는지 확인한다."""
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
        """CSV 동기화 단계에 오류를 주입해 이전 출력 파일이 유지되는지 확인한다."""
        self.add()
        target = self.root / "out.csv"
        target.write_bytes(b"old output")
        with patch("budget_app.storage.os.fsync", side_effect=OSError("fault")):
            with self.assertRaises(OSError):
                self.service.export_csv(target, month="2026-10")
        self.assertEqual(target.read_bytes(), b"old output")

    def test_export_missing_output_parent(self):
        """없는 폴더로 내보내면 경로 오류가 나는지 확인한다."""
        with self.assertRaises(FileNotFoundError):
            self.service.export_csv(self.root / "missing" / "out.csv", month="2026-10")

    def test_export_import_roundtrip_preserves_business_fields_not_id(self):
        """CSV 왕복으로 메모·태그 등 업무 필드가 같고 ID만 새로 부여되는지 확인한다."""
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
