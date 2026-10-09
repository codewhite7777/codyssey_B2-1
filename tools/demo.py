"""전체 흐름을 실제 CLI 하위 프로세스로 실행한다. 개인 data 폴더에는 쓰지 않는다."""

import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    lines = ["B2-1 실제 CLI 시연", f"실행 시각(UTC): {datetime.now(timezone.utc).isoformat()}", ""]
    with tempfile.TemporaryDirectory(prefix="budget-demo-") as directory:
        root = Path(directory)
        data = root / "data"
        def run(arguments, user_input="", expected=0):
            command = [sys.executable, "-S", "-m", "budget_app", "--data-dir", str(data), *arguments]
            result = subprocess.run(command, cwd=ROOT, input=user_input, text=True, encoding="utf-8",
                                    capture_output=True, timeout=20)
            rendered = "python -m budget_app --data-dir <임시폴더>/data " + " ".join(arguments)
            lines.extend(["$ " + rendered.replace(str(root), "<임시폴더>")])
            if user_input:
                lines.append("입력: " + repr(user_input))
            lines.extend([result.stdout.replace(str(root), "<임시폴더>").rstrip(),
                          result.stderr.replace(str(root), "<임시폴더>").rstrip(), f"exit={result.returncode}", ""])
            assert result.returncode == expected, result.stderr
            assert "Traceback" not in result.stdout + result.stderr
            return result
        run(["category", "add"], "salary\n")
        run(["category", "add"], "food\n")
        run(["add"], "2026-10-01\nincome\nsalary\n100000\n용돈\nmonthly\n")
        response = run(["add"], "2026-10-06\nexpense\nfood\n15000\n점심\nmeal\n")
        identifier = re.search(r"id=(TX-[a-f0-9]+)", response.stdout).group(1)
        run(["budget", "set", "--month", "2026-10", "--amount", "50000"])
        summary = run(["summary", "--month", "2026-10", "--top", "3"])
        assert "85,000원" in summary.stdout and "30.0%" in summary.stdout
        run(["list", "--limit", "3"])
        run(["search", "--category", "food", "--tag", "meal"])
        run(["update", "--id", identifier, "--amount", "55000"])
        summary = run(["summary", "--month", "2026-10"])
        assert "110.0%" in summary.stdout and "[경고]" in summary.stdout
        run(["export", "--out", str(root / "export.csv"), "--month", "2026-10"])
        before = (data / "transactions.jsonl").read_bytes()
        invalid = root / "invalid.csv"
        invalid.write_text("date,type,category,amount\n2026-10-06,expense,food,100\n2026-10-07,expense,food,0\n", encoding="utf-8")
        run(["import", "--from", str(invalid)], expected=2)
        assert (data / "transactions.jsonl").read_bytes() == before
        run(["category", "remove"], "food\n", expected=1)
        run(["delete", "--id", identifier])
        run(["delete", "--id", identifier], expected=1)
        run(["import", "--from", str(root / "export.csv")])
        run(["summary", "--month", "2026-11"])
        run(["category", "add"], "unused\n")
        run(["category", "remove"], "unused\n")
    text = "\n".join(lines).rstrip() + "\n"
    output = ROOT / "reports" / "cli_demo.txt"
    output.parent.mkdir(exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
