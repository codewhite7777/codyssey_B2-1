"""10만 행 CSV를 빈 거래 저장소에 가져오고 건수·합계를 확인한다."""

import csv
import json
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from budget_app.csv_io import CSV_COLUMNS
from budget_app.service import BudgetService
from .benchmark import measured


def main():
    count = 100000
    with tempfile.TemporaryDirectory(prefix="budget-import-benchmark-") as directory:
        root = Path(directory)
        service = BudgetService(root / "data")
        service.add_category("food")
        source = root / "source.csv"
        with source.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(CSV_COLUMNS)
            for index in range(count):
                writer.writerow((f"2026-10-{index % 28 + 1:02}", "expense", "food", 100, "일괄 등록", "test,bulk"))
        imported, measurement = measured(lambda: service.import_csv(source))
        summary = service.summary("2026-10")
        assert imported == count and summary.count == count and summary.expense == count * 100
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
            "platform": platform.platform(), "records": count, "measurement": measurement,
            "verified_count": summary.count, "verified_expense": summary.expense,
            "note": "빈 거래 저장소에 10만 행 CSV를 전체 검증 후 반영. tracemalloc 활성, 단일 실행. 입력 버퍼와 ID 집합은 건수에 비례해 증가한다.",
        }
    output = Path(__file__).resolve().parents[1] / "reports" / "benchmark_import.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
