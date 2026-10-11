"""실행: python -m tools.run_tests. 실제 실행 로그와 기계 판독용 결과를 남긴다."""

import ast
import json
import platform
import sys
import time
import unittest
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def flatten(suite):
    """중첩된 unittest 테스트 묶음을 재귀적으로 풀어 개별 테스트를 하나씩 전달한다."""
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def main() -> int:
    """테스트를 실행하고 실제 결과·3.10 문법 검사·표준 의존성 검사 기록을 저장한다.

    reports에 로그와 JSON을 쓰며 모두 성공하면 0, 실패 항목이 있으면 1을 반환한다.
    AST 문법 검사는 Python 3.10 실행이나 정적 타입 검사를 대신하지 않는다.
    """
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    counts = Counter(test.__class__.__module__ for test in flatten(suite))
    syntax_errors = []
    imports = set()
    for path in (ROOT / "budget_app").glob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 10))
        except SyntaxError as exc:
            syntax_errors.append(f"{path.name}:{exc.lineno}: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".")[0])
    nonstdlib = sorted(imports - sys.stdlib_module_names)
    started = time.perf_counter()
    with (reports / "unit_test_log.txt").open("w", encoding="utf-8") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    elapsed = time.perf_counter() - started
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(),
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "elapsed_seconds": round(elapsed, 3),
        "by_module": dict(sorted(counts.items())),
        "python_3_10_ast_syntax_errors": syntax_errors,
        "application_import_roots": sorted(imports), "non_standard_library_imports": nonstdlib,
        "note": "문법 검사는 Python 3.10 실제 인터프리터 실행/정적 타입 검사와 다릅니다. CLI 하위 프로세스는 -S로 site 패키지 없이 실행합니다.",
    }
    (reports / "test_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() and not syntax_errors and not nonstdlib else 1


if __name__ == "__main__":
    raise SystemExit(main())
