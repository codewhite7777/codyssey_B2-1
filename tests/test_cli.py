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
        result = self.cli("add", input_text="2026-10-06\nexpense\nfood\n15000\n점심\nmeal,lunch\n")
        identifier = re.search(r"id=(TX-[a-f0-9]+)", result.stdout).group(1)
        listing = self.cli("list", "--limit", "1")
        self.assertIn(identifier, listing.stdout)
        self.assertIn("15,000", listing.stdout)

    def test_invalid_interactive_input_reprompts(self):
        result = self.cli("add", input_text="2026-02-30\n2026-10-06\nbad\nexpense\nunknown\nfood\n0\n-1\n100\n메모\nmeal\n")
        self.assertIn("[저장 완료]", result.stdout)
        self.assertGreaterEqual(result.stderr.count("[오류]"), 5)
        self.assertEqual(len(list(self.service.search())), 1)

    def test_empty_category_blocks_add_without_waiting(self):
        for name in self.service.list_categories():
            self.service.remove_category(name)
        result = self.cli("add", expected=2)
        self.assertIn("category add", result.stderr)

    def test_eof_cancels_no_transaction_saved(self):
        before = self.snapshot()
        self.cli("add", input_text="2026-10-06\nexpense\n", expected=130)
        self.assertEqual(self.snapshot(), before)

    def test_empty_list_and_empty_summary(self):
        self.assertIn("데이터 없음", self.cli("list").stdout)
        self.assertIn("데이터 없음", self.cli("summary", "--month", "2026-10").stdout)

    def test_interactive_category_add_list_remove(self):
        self.cli("category", "add", input_text="카페\n")
        self.assertIn("카페", self.cli("category", "list").stdout)
        self.cli("category", "remove", input_text="카페\n")
        self.assertNotIn("카페", self.cli("category", "list").stdout)

    def test_used_category_cli_error(self):
        self.add()
        self.cli("category", "remove", input_text="food\n", expected=1)

    def test_budget_set_show_summary_over_warning(self):
        self.add(amount=15000)
        self.cli("budget", "set", "--month", "2026-10", "--amount", "10000")
        self.assertIn("10,000", self.cli("budget", "show", "--month", "2026-10").stdout)
        result = self.cli("summary", "--month", "2026-10", "--top", "1")
        self.assertIn("150.0%", result.stdout)
        self.assertIn("[경고]", result.stdout)
        self.assertIn("5,000", result.stdout)

    def test_missing_budget_show_is_informational(self):
        self.assertIn("미설정", self.cli("budget", "show", "--month", "2026-10").stdout)

    def test_update_cli_clear_optional_then_delete(self):
        value = self.add()
        self.cli("update", "--id", value.id, "--amount", "100", "--memo", "", "--tags", "")
        changed = list(self.service.search())[0]
        self.assertEqual((changed.amount, changed.memo, changed.tags), (100, "", ()))
        self.cli("delete", "--id", value.id)
        self.assertEqual(list(self.service.search()), [])

    def test_missing_update_delete_id_error(self):
        self.cli("update", "--id", "missing", "--memo", "new", expected=1)
        self.cli("delete", "--id", "missing", expected=1)

    def test_update_requires_at_least_one_field(self):
        value = self.add()
        self.cli("update", "--id", value.id, expected=2)

    def test_search_all_flags(self):
        value = self.add()
        result = self.cli("search", "--from", "2026-10-01", "--to", "2026-10-31", "--category", "food",
                          "--type", "expense", "--q", "점심", "--tag", "meal", "--limit", "2")
        self.assertIn(value.id, result.stdout)

    def test_invalid_usage_and_single_dash_rejected(self):
        cases = [(), ("missing",), ("list", "-limit", "2"), ("list", "--lim", "2"),
                 ("list", "--limit", "0"), ("list", "--limit", "abc"),
                 ("summary",), ("budget",), ("delete",), ("category",),
                 ("search", "--type", "bad"), ("summary", "--month", "2026-13"),
                 ("search", "--from", "2026-10-31", "--to", "2026-10-01")]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.cli(*arguments, expected=2)

    def test_import_export_commands_and_counts(self):
        source = self.csv_file([self.row()])
        self.assertIn("imported=1", self.cli("import", "--from", str(source)).stdout)
        output = self.root / "out.csv"
        self.assertIn("1 records", self.cli("export", "--out", str(output), "--month", "2026-10").stdout)
        self.assertTrue(output.is_file())

    def test_invalid_import_cli_reports_zero_and_nonzero_exit(self):
        source = self.csv_file([self.row(), self.row(amount="0")])
        before = self.snapshot()
        result = self.cli("import", "--from", str(source), expected=2)
        self.assertIn("imported=0", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_missing_import_file_no_stacktrace(self):
        self.cli("import", "--from", str(self.root / "missing.csv"), expected=1)

    def test_export_missing_period_is_error_no_output(self):
        target = self.root / "out.csv"
        self.cli("export", "--out", str(target), expected=2)
        self.assertFalse(target.exists())

    def test_corrupt_storage_no_stacktrace_nonzero(self):
        (self.data / "transactions.jsonl").write_text("not-json\n", encoding="utf-8")
        self.cli("list", expected=1)

    def test_locked_directory_cli_nonzero(self):
        lock = self.data / ".budget_app.lock"
        lock.write_text("pid=99999999\n")
        self.cli("list", expected=1)
        self.assertTrue(lock.exists())

    def test_data_dir_option_before_or_after_nested_command(self):
        for arguments in (("--data-dir", str(self.data), "category", "list"),
                          ("category", "--data-dir", str(self.data), "list"),
                          ("category", "list", "--data-dir", str(self.data))):
            result = subprocess.run([sys.executable, "-S", "-m", "budget_app", *arguments], cwd=ROOT,
                                    text=True, encoding="utf-8", capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("food", result.stdout)

    def test_help_does_not_create_data_directory(self):
        target = self.root / "not_created"
        result = subprocess.run([sys.executable, "-S", "-m", "budget_app", "--data-dir", str(target), "--help"],
                                cwd=ROOT, text=True, encoding="utf-8", capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(target.exists())

    def test_active_lock_blocks_separate_cli_process(self):
        with self.service.store.session():
            self.cli("category", "add", input_text="blocked\n", expected=1)
        self.assertNotIn("blocked", self.service.list_categories())

    def test_broken_output_pipe_has_no_traceback(self):
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
        for error, code in ((ValidationError("bad", "fix"), 2), (OSError("denied"), 1),
                            (EOFError(), 130), (KeyboardInterrupt(), 130), (RuntimeError("bug"), 1)):
            with self.subTest(error=type(error).__name__):
                @handle_cli_errors
                def failure():
                    raise error
                stream = io.StringIO()
                with contextlib.redirect_stderr(stream):
                    self.assertEqual(failure(), code)
                self.assertIn("[오류]", stream.getvalue())
                self.assertIn("[힌트]", stream.getvalue())
                self.assertNotIn("Traceback", stream.getvalue())

    def test_error_during_generator_iteration_is_caught(self):
        def broken(*args, **kwargs):
            yield from ()
            raise OSError("late read failure")
        output = io.StringIO()
        with patch("budget_app.cli.BudgetService.list_transactions", side_effect=broken), contextlib.redirect_stderr(output):
            self.assertEqual(main(["list"]), 1)
        self.assertIn("late read failure", output.getvalue())

    def test_cli_fault_injection_permission_error(self):
        output = io.StringIO()
        with patch("budget_app.cli.BudgetService.list_categories", side_effect=PermissionError("denied")), contextlib.redirect_stderr(output):
            self.assertEqual(main(["category", "list"]), 1)
        self.assertIn("권한", output.getvalue())

    def test_safe_text_preserves_data_but_escapes_controls_for_display(self):
        self.assertEqual(safe_text("a\nb\r\t\x1b[2J"), "a\\nb\\r\\t\\x1b[2J")

    def test_prompt_retries_validation_only(self):
        with patch("builtins.input", side_effect=["bad", "good"]), contextlib.redirect_stderr(io.StringIO()):
            def parse(value):
                if value == "bad":
                    raise ValidationError("bad", "retry")
                return value
            self.assertEqual(prompt("input", parse), "good")
