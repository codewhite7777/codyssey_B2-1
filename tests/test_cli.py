import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from budget_app.cli import build_parser, main, prompt
from budget_app.decorators import handle_cli_errors, safe_text
from budget_app.errors import ValidationError
from budget_app.service import BudgetService
from tests.common import ServiceCase

ROOT = Path(__file__).resolve().parents[1]


class CLISubprocessTests(ServiceCase):
    def cli(self, *arguments, input_text="", expected=0):
        """CLI를 별도 프로세스로 실행해 종료 코드와 출력·오류 안내를 검증하고 결과를 반환한다."""
        result = subprocess.run([sys.executable, "-S", "-m", "budget_app", "--data-dir", str(self.data), *arguments],
                                cwd=ROOT, input=input_text, text=True, encoding="utf-8", capture_output=True,
                                timeout=20, env={**os.environ, "PYTHONUTF8": "1"})
        self.assertEqual(result.returncode, expected, msg=result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        if expected != 0:
            self.assertIn("[오류]", result.stderr)
            self.assertIn("[힌트]", result.stderr)
        return result

    def test_every_command_and_subcommand_help(self):
        """모든 명령의 --help를 실행해 사용법 표시와 데이터 미변경을 확인한다."""
        commands = [(), ("add",), ("list",), ("search",), ("summary",), ("budget",),
                    ("budget", "set"), ("budget", "show"), ("category",), ("category", "add"),
                    ("category", "list"), ("category", "remove"), ("update",), ("delete",),
                    ("import",), ("export",)]
        before = self.snapshot()
        for command in commands:
            with self.subTest(command=command):
                result = self.cli(*command, "--help")
                self.assertIn("usage:", result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_interactive_add_and_restart(self):
        """대화형 추가에서 출력한 ID를 다른 CLI 조회 프로세스에서 다시 확인한다."""
        result = self.cli("add", input_text="2026-10-06\nexpense\nfood\n15000\n점심\nmeal,lunch\n")
        identifier = re.search(r"id=(TX-[a-f0-9]+)", result.stdout).group(1)
        listing = self.cli("list", "--limit", "1")
        self.assertIn(identifier, listing.stdout)
        self.assertIn("15,000", listing.stdout)

    def test_invalid_interactive_input_reprompts(self):
        """잘못된 날짜·타입·분류·금액 뒤에 정상 입력을 보내 재입력 후 한 건만 저장되는지 확인한다."""
        result = self.cli("add", input_text="2026-02-30\n2026-10-06\nbad\nexpense\nunknown\nfood\n0\n-1\n100\n메모\nmeal\n")
        self.assertIn("[저장 완료]", result.stdout)
        self.assertGreaterEqual(result.stderr.count("[오류]"), 5)
        self.assertEqual(len(list(self.service.search())), 1)

    def test_empty_category_blocks_add_without_waiting(self):
        """카테고리를 모두 지우고 add를 실행해 입력 대기 없이 등록 안내로 종료하는지 확인한다."""
        for name in self.service.list_categories():
            self.service.remove_category(name)
        result = self.cli("add", expected=2)
        self.assertIn("category add", result.stderr)

    def test_eof_cancels_no_transaction_saved(self):
        """입력을 중간에 끝내 취소 코드 130과 저장 파일 미변경을 확인한다."""
        before = self.snapshot()
        self.cli("add", input_text="2026-10-06\nexpense\n", expected=130)
        self.assertEqual(self.snapshot(), before)

    def test_empty_list_and_empty_summary(self):
        """거래가 없는 목록과 월별 요약에서 데이터 없음 안내를 확인한다."""
        self.assertIn("데이터 없음", self.cli("list").stdout)
        self.assertIn("데이터 없음", self.cli("summary", "--month", "2026-10").stdout)

    def test_interactive_category_add_list_remove(self):
        """한글 카테고리를 대화형으로 등록·조회·삭제하고 각 상태를 확인한다."""
        self.cli("category", "add", input_text="카페\n")
        self.assertIn("카페", self.cli("category", "list").stdout)
        self.cli("category", "remove", input_text="카페\n")
        self.assertNotIn("카페", self.cli("category", "list").stdout)

    def test_used_category_cli_error(self):
        """거래가 사용하는 카테고리를 CLI로 삭제해 오류 코드와 안내를 확인한다."""
        self.add()
        self.cli("category", "remove", input_text="food\n", expected=1)

    def test_budget_set_show_summary_over_warning(self):
        """지출보다 낮은 예산을 설정·조회하고 요약의 150.0%와 초과 경고를 확인한다."""
        self.add(amount=15000)
        self.cli("budget", "set", "--month", "2026-10", "--amount", "10000")
        self.assertIn("10,000", self.cli("budget", "show", "--month", "2026-10").stdout)
        result = self.cli("summary", "--month", "2026-10", "--top", "1")
        self.assertIn("150.0%", result.stdout)
        self.assertIn("[경고]", result.stdout)
        self.assertIn("5,000", result.stdout)

    def test_missing_budget_show_is_informational(self):
        """미설정 예산 조회가 오류가 아닌 정상 안내로 끝나는지 확인한다."""
        self.assertIn("미설정", self.cli("budget", "show", "--month", "2026-10").stdout)

    def test_update_cli_clear_optional_then_delete(self):
        """CLI 수정으로 금액·빈 메모·빈 태그를 반영하고 이어서 삭제되는지 확인한다."""
        value = self.add()
        self.cli("update", "--id", value.id, "--amount", "100", "--memo", "", "--tags", "")
        changed = list(self.service.search())[0]
        self.assertEqual((changed.amount, changed.memo, changed.tags), (100, "", ()))
        self.cli("delete", "--id", value.id)
        self.assertEqual(list(self.service.search()), [])

    def test_missing_update_delete_id_error(self):
        """없는 ID의 수정·삭제를 실제 CLI에서 실행해 비정상 종료를 확인한다."""
        self.cli("update", "--id", "missing", "--memo", "new", expected=1)
        self.cli("delete", "--id", "missing", expected=1)

    def test_update_requires_at_least_one_field(self):
        """ID만 주고 수정 필드를 생략하면 사용 오류가 나는지 확인한다."""
        value = self.add()
        self.cli("update", "--id", value.id, expected=2)

    def test_search_all_flags(self):
        """기간·분류·타입·메모·태그·limit을 함께 지정해 해당 거래가 출력되는지 확인한다."""
        value = self.add()
        result = self.cli("search", "--from", "2026-10-01", "--to", "2026-10-31", "--category", "food",
                          "--type", "expense", "--q", "점심", "--tag", "meal", "--limit", "2")
        self.assertIn(value.id, result.stdout)

    def test_invalid_usage_and_single_dash_rejected(self):
        """필수 명령·옵션 누락, 축약·단일 하이픈, 잘못된 값을 순회해 오류 안내를 확인한다."""
        cases = [(), ("missing",), ("list", "-limit", "2"), ("list", "--lim", "2"),
                 ("list", "--limit", "0"), ("list", "--limit", "abc"),
                 ("summary",), ("budget",), ("delete",), ("category",),
                 ("search", "--type", "bad"), ("summary", "--month", "2026-13"),
                 ("search", "--from", "2026-10-31", "--to", "2026-10-01")]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.cli(*arguments, expected=2)

    def test_import_export_commands_and_counts(self):
        """실제 CSV 가져오기·내보내기를 실행해 건수 메시지와 출력 파일 생성을 확인한다."""
        source = self.csv_file([self.row()])
        self.assertIn("imported=1", self.cli("import", "--from", str(source)).stdout)
        output = self.root / "out.csv"
        self.assertIn("1 records", self.cli("export", "--out", str(output), "--month", "2026-10").stdout)
        self.assertTrue(output.is_file())

    def test_invalid_import_cli_reports_zero_and_nonzero_exit(self):
        """오류 행이 있는 CSV에서 0건 반영 메시지·종료 코드 2·원본 보존을 확인한다."""
        source = self.csv_file([self.row(), self.row(amount="0")])
        before = self.snapshot()
        result = self.cli("import", "--from", str(source), expected=2)
        self.assertIn("imported=0", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_missing_import_file_no_stacktrace(self):
        """없는 CSV 경로가 스택트레이스 없이 파일 오류와 힌트로 표시되는지 확인한다."""
        self.cli("import", "--from", str(self.root / "missing.csv"), expected=1)

    def test_export_missing_period_is_error_no_output(self):
        """기간 없는 내보내기를 거부하고 출력 파일도 남기지 않는지 확인한다."""
        target = self.root / "out.csv"
        self.cli("export", "--out", str(target), expected=2)
        self.assertFalse(target.exists())

    def test_corrupt_storage_no_stacktrace_nonzero(self):
        """손상된 거래 파일 조회가 스택트레이스 없이 비정상 종료하는지 확인한다."""
        (self.data / "transactions.jsonl").write_text("not-json\n", encoding="utf-8")
        self.cli("list", expected=1)

    def test_locked_directory_cli_nonzero(self):
        """남아 있는 잠금 때문에 CLI가 실패해도 기존 잠금은 삭제하지 않는지 확인한다."""
        lock = self.data / ".budget_app.lock"
        lock.write_text("pid=99999999\n")
        self.cli("list", expected=1)
        self.assertTrue(lock.exists())

    def test_data_dir_option_before_or_after_nested_command(self):
        """--data-dir를 명령 전·중간·뒤에 배치해 모두 같은 폴더의 카테고리를 읽는지 확인한다."""
        for arguments in (("--data-dir", str(self.data), "category", "list"),
                          ("category", "--data-dir", str(self.data), "list"),
                          ("category", "list", "--data-dir", str(self.data))):
            result = subprocess.run([sys.executable, "-S", "-m", "budget_app", *arguments], cwd=ROOT,
                                    text=True, encoding="utf-8", capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("food", result.stdout)

    def test_help_does_not_create_data_directory(self):
        """새 경로로 --help를 실행해 도움말만 출력하고 저장 폴더는 만들지 않는지 확인한다."""
        target = self.root / "not_created"
        result = subprocess.run([sys.executable, "-S", "-m", "budget_app", "--data-dir", str(target), "--help"],
                                cwd=ROOT, text=True, encoding="utf-8", capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(target.exists())

    def test_active_lock_blocks_separate_cli_process(self):
        """서비스가 잠금을 가진 동안 별도 CLI의 카테고리 등록을 차단하는지 확인한다."""
        with self.service.store.session():
            self.cli("category", "add", input_text="blocked\n", expected=1)
        self.assertNotIn("blocked", self.service.list_categories())

    def test_broken_output_pipe_has_no_traceback(self):
        """CLI stdout 파이프를 닫아 종료 시 스택트레이스와 남은 잠금이 없는지 확인한다."""
        self.add()
        process = subprocess.Popen(
            [sys.executable, "-S", "-m", "budget_app", "--data-dir", str(self.data), "list"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        process.stdout.close()
        with process.stderr:
            stderr = process.stderr.read().decode("utf-8")
        code = process.wait(timeout=20)
        self.assertNotEqual(code, 0)
        self.assertNotIn("Traceback", stderr)
        self.assertNotIn("Exception ignored", stderr)
        self.assertFalse((self.data / ".budget_app.lock").exists())

    def test_e2e_entire_workflow(self):
        """추가·예산·요약·수정·검색·내보내기·삭제를 연결해 최종 거래 상태까지 확인한다."""
        self.cli("add", input_text="2026-10-01\nincome\nsalary\n100000\n용돈\n\n")
        self.cli("add", input_text="2026-10-02\nexpense\nfood\n15000\n점심\nmeal\n")
        self.cli("budget", "set", "--month", "2026-10", "--amount", "50000")
        summary = self.cli("summary", "--month", "2026-10")
        self.assertIn("85,000원", summary.stdout)
        self.assertIn("30.0%", summary.stdout)
        values = list(self.service.search())
        expense = next(t for t in values if t.type == "expense")
        self.cli("update", "--id", expense.id, "--amount", "20000")
        self.assertIn("20,000", self.cli("search", "--tag", "meal").stdout)
        target = self.root / "full.csv"
        self.cli("export", "--out", str(target), "--month", "2026-10")
        self.cli("delete", "--id", expense.id)
        self.cli("category", "remove", input_text="food\n")
        self.assertEqual(len(list(self.service.search())), 1)


class DecoratorAndParserUnitTests(unittest.TestCase):
    def test_decorator_preserves_name_doc_and_annotations(self):
        """데코레이터 적용 뒤 함수 이름·문서·타입·__wrapped__와 정상 반환값이 유지되는지 확인한다."""
        @handle_cli_errors
        def example() -> int:
            """demo doc"""
            return 0
        self.assertEqual(example.__name__, "example")
        self.assertEqual(example.__doc__, "demo doc")
        self.assertIn("return", example.__annotations__)
        self.assertTrue(hasattr(example, "__wrapped__"))
        self.assertEqual(example(), 0)

    def test_decorator_error_branches(self):
        """업무·파일·취소·예상 밖 오류를 주입해 각 종료 코드와 원인·힌트를 확인한다."""
        for error, code in ((ValidationError("bad", "fix"), 2), (OSError("denied"), 1),
                            (EOFError(), 130), (KeyboardInterrupt(), 130), (RuntimeError("bug"), 1)):
            with self.subTest(error=type(error).__name__):
                @handle_cli_errors
                def failure():
                    """현재 반복에서 선택한 오류를 발생시켜 데코레이터의 오류 분기를 검증한다."""
                    raise error
                stream = io.StringIO()
                with contextlib.redirect_stderr(stream):
                    self.assertEqual(failure(), code)
                self.assertIn("[오류]", stream.getvalue())
                self.assertIn("[힌트]", stream.getvalue())
                self.assertNotIn("Traceback", stream.getvalue())

    def test_error_during_generator_iteration_is_caught(self):
        """제너레이터 생성 후 순회 중 발생한 읽기 오류도 main의 데코레이터가 처리하는지 확인한다."""
        def broken(*args, **kwargs):
            """소비 시점에 읽기 오류를 발생시켜 지연 실행 오류 상황을 재현한다."""
            yield from ()
            raise OSError("late read failure")
        output = io.StringIO()
        with patch("budget_app.cli.BudgetService.list_transactions", side_effect=broken), contextlib.redirect_stderr(output):
            self.assertEqual(main(["list"]), 1)
        self.assertIn("late read failure", output.getvalue())

    def test_cli_fault_injection_permission_error(self):
        """카테고리 읽기에 권한 오류를 주입해 CLI가 원인과 권한 힌트를 출력하는지 확인한다."""
        output = io.StringIO()
        with patch("budget_app.cli.BudgetService.list_categories", side_effect=PermissionError("denied")), contextlib.redirect_stderr(output):
            self.assertEqual(main(["category", "list"]), 1)
        self.assertIn("권한", output.getvalue())

    def test_safe_text_preserves_data_but_escapes_controls_for_display(self):
        """출력용 문자열의 개행·탭·터미널 제어 문자가 눈에 보이는 표기로 바뀌는지 비교한다."""
        self.assertEqual(safe_text("a\nb\r\t\x1b[2J"), "a\\nb\\r\\t\\x1b[2J")

    def test_prompt_retries_validation_only(self):
        """첫 입력은 검증 오류, 두 번째는 정상값을 보내 재입력 후 결과를 반환하는지 확인한다."""
        with patch("builtins.input", side_effect=["bad", "good"]), contextlib.redirect_stderr(io.StringIO()):
            def parse(value):
                """bad 입력만 검증 오류로 거부하고 다른 입력은 그대로 반환하는 재입력 검사 대역이다."""
                if value == "bad":
                    raise ValidationError("bad", "retry")
                return value
            self.assertEqual(prompt("input", parse), "good")
