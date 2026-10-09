"""실행: python -m tools.benchmark --sizes 10000 100000. 실제 사용자 데이터를 건드리지 않는다."""

import argparse
import gc
import json
import platform
import sys
import tempfile
import time
import tracemalloc
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from budget_app.models import SearchFilter, Transaction
from budget_app.service import BudgetService


def measured(operation):
    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()
    result = operation()
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, {"seconds": round(elapsed, 6), "peak_traced_bytes": peak}


def consume(generator):
    with closing(generator):
        return sum(1 for _ in generator)


def benchmark(count, operations):
    with tempfile.TemporaryDirectory(prefix="budget-benchmark-") as directory:
        root = Path(directory)
        service = BudgetService(root / "data")
        service.add_category("food")
        service.add_category("salary")
        def synthetic():
            for index in range(count, 0, -1):
                income = index % 10 == 0
                yield Transaction(f"TX-{index:012d}", "income" if income else "expense", "2026-10-06",
                                  1000 if income else 100, "salary" if income else "food", "benchmark", ("sample",))
        with service.store.session():
            service.store.transactions.replace_all(synthetic())
        result = {"records": count, "file_bytes": (root / "data" / "transactions.jsonl").stat().st_size}
        if "list_20" in operations:
            found, result["list_20"] = measured(lambda: consume(service.list_transactions(20)))
            assert found == min(20, count)
        if "search_no_match_full_scan" in operations:
            found, result["search_no_match_full_scan"] = measured(lambda: consume(service.search(SearchFilter(tag="not_found"))))
            assert found == 0
        if "summary" in operations:
            summary, result["summary"] = measured(lambda: service.summary("2026-10"))
            assert summary.count == count
            assert summary.income == count // 10 * 1000
            assert summary.expense == (count - count // 10) * 100
            result["expected_totals_verified"] = {"income": summary.income, "expense": summary.expense, "balance": summary.balance}
        if "export" in operations:
            exported, result["export"] = measured(lambda: service.export_csv(root / "out.csv", month="2026-10"))
            assert exported == count
        target = f"TX-{count:012d}"
        expected_count = count
        if "add" in operations:
            added, result["add"] = measured(lambda: service.add(date="2026-10-07", type="expense", category="food", amount=1))
            target = added.id
            expected_count += 1
        if "update" in operations:
            updated, result["update"] = measured(lambda: service.update(target, date="2026-10-01", amount=2))
            assert updated.amount == 2 and updated.date == "2026-10-01"
        if "delete" in operations:
            _, result["delete"] = measured(lambda: service.delete(target))
            expected_count -= 1
        assert consume(service.search()) == expected_count
        result["post_operation_count_verified"] = expected_count
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[10000, 100000])
    parser.add_argument("--operations", nargs="+", default=["list_20", "search_no_match_full_scan", "summary", "export", "add", "update", "delete"],
                        choices=["list_20", "search_no_match_full_scan", "summary", "export", "add", "update", "delete"])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "reports" / "benchmark_results.json")
    args = parser.parse_args()
    results = []
    for count in args.sizes:
        if count <= 0:
            parser.error("sizes must be positive")
        item = benchmark(count, args.operations)
        results.append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)
    output = args.out
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
        "platform": platform.platform(),
        "measurement": "한 환경에서 각 작업 1회, tracemalloc 활성. OS RSS/캐시/화면 렌더링 비용 제외. 합성 데이터 사용.",
        "results": results,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
