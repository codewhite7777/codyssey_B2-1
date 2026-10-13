"""README의 직접 입력·CSV 예제를 임시 경로에 재현하는 CLI 통합 검사.

각 명령은 실제 별도 프로세스다. README의 연습 경로만 TemporaryDirectory 아래로
옮기며, 개인 ./data를 읽거나 변경하지 않는다. 설명문 존재 검사는 다른 테스트가 담당한다.
"""

import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReadmeWorkflowTests(unittest.TestCase):
    """처음 사용하는 사람이 문서 순서대로 실행했을 때의 결과·오류·저장을 확인한다."""

    def setUp(self) -> None:
        """테스트마다 빈 연습 경로를 만들고 종료 시 자동 정리하여 개인 데이터와 격리한다."""
        temporary = tempfile.TemporaryDirectory(prefix="budget-readme-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.practice = self.root / "data" / "practice"
        self.csv_practice = self.root / "data" / "csv-practice"

    def run_cli(
        self, directory: Path, *arguments: str, input_text: str = "", expected: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        """README 명령을 별도 Python 프로세스로 실행해 종료 코드·오류 형식을 검사한다.

        입력은 stdin으로 보내고 -S로 외부 site 패키지를 로딩하지 않는다.
        프로세스마다 같은 directory를 전달해 재실행 후 데이터 유지도 함께 확인한다.
        """
        result = subprocess.run(
            [sys.executable, "-S", "-m", "budget_app", "--data-dir", str(directory), *arguments],
            cwd=ROOT, input=input_text, text=True, encoding="utf-8", capture_output=True,
            timeout=20, env={**os.environ, "PYTHONUTF8": "1"},
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        if expected:
            self.assertIn("[오류]", result.stderr)
            self.assertIn("[힌트]", result.stderr)
        return result

    def test_manual_first_run_matches_readme(self) -> None:
        """빈 가계부에서 두 거래·예산·검색·수정·삭제를 실행해 README의 수치와 흐름을 확인한다."""
        self.run_cli(self.practice, "--help")
        self.assertFalse(self.practice.exists())
        self.assertIn("데이터 없음", self.run_cli(self.practice, "category", "list").stdout)
        for category in ("salary", "food"):
            self.run_cli(self.practice, "category", "add", input_text=category + "\n")
        self.run_cli(
            self.practice, "add",
            input_text="2026-10-01\nincome\nsalary\n100000\n용돈\nmonthly\n",
        )
        expense = self.run_cli(
            self.practice, "add",
            input_text="2026-10-06\nexpense\nfood\n15000\n점심\nmeal,lunch\n",
        )
        match = re.search(r"id=(TX-[a-f0-9]+)", expense.stdout)
        self.assertIsNotNone(match)
        identifier = match.group(1)
        listing = self.run_cli(self.practice, "list", "--limit", "5")
        self.assertIn(identifier, listing.stdout)
        self.assertIn("2건", listing.stdout)
        self.run_cli(self.practice, "budget", "set", "--month", "2026-10", "--amount", "50000")
        summary = self.run_cli(self.practice, "summary", "--month", "2026-10", "--top", "3")
        for expected_text in ("총 수입: 100,000원", "총 지출: 15,000원", "잔액: 85,000원", "사용률 30.0%"):
            self.assertIn(expected_text, summary.stdout)
        self.assertIn(
            identifier,
            self.run_cli(self.practice, "search", "--category", "food", "--tag", "meal").stdout,
        )
        self.run_cli(self.practice, "update", "--id", identifier, "--amount", "55000")
        summary = self.run_cli(self.practice, "summary", "--month", "2026-10")
        self.assertIn("110.0%", summary.stdout)
        self.assertIn("예산을 5,000원 초과", summary.stdout)
        self.run_cli(self.practice, "category", "remove", input_text="food\n", expected=1)
        self.run_cli(self.practice, "delete", "--id", identifier)
        self.run_cli(self.practice, "category", "remove", input_text="food\n")
        self.assertIn("1건", self.run_cli(self.practice, "list").stdout)
        self.run_cli(self.practice, "delete", "--id", identifier, expected=1)
        self.assertEqual(len(list(self.practice.glob("*.jsonl"))), 3)
        self.assertFalse((self.practice / ".budget_app.lock").exists())

    def test_sample_csv_and_failed_import_match_readme(self) -> None:
        """제공 CSV의 3건·합계·내보내기를 대조하고 오류 전체 미반영과 저장 경로 분리를 확인한다."""
        for category in ("salary", "food", "transport"):
            self.run_cli(self.csv_practice, "category", "add", input_text=category + "\n")
        imported = self.run_cli(self.csv_practice, "import", "--from", "examples/sample_import.csv")
        self.assertIn("imported=3, skipped=0", imported.stdout)
        summary = self.run_cli(self.csv_practice, "summary", "--month", "2026-10")
        for expected_text in ("총 수입: 100,000원", "총 지출: 17,000원", "잔액: 83,000원"):
            self.assertIn(expected_text, summary.stdout)
        target = self.root / "data" / "csv-export.csv"
        exported = self.run_cli(self.csv_practice, "export", "--out", str(target), "--month", "2026-10")
        self.assertIn("3 records", exported.stdout)
        with target.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames, ["date", "type", "category", "amount", "memo", "tags"])
            self.assertEqual(len(list(reader)), 3)
        before = {path.name: path.read_bytes() for path in self.csv_practice.glob("*.jsonl")}
        invalid = self.run_cli(
            self.csv_practice, "import", "--from", "examples/invalid_import.csv", expected=2,
        )
        self.assertIn("imported=0 (전체 미반영)", invalid.stderr)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.csv_practice.glob("*.jsonl")})
        self.assertIn("데이터 없음", self.run_cli(self.practice, "list").stdout)
        self.assertIn("3건", self.run_cli(self.csv_practice, "list").stdout)
        records = [json.loads(line) for line in (self.csv_practice / "transactions.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len({record["id"] for record in records}), 3)
