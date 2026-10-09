"""CSV 교환 스키마. 가져오기 검증과 내보내기를 내부 JSONL 저장에서 분리한다."""

import csv
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import TextIO, TypedDict

from .errors import AppError, ImportDataError
from .models import Transaction
from .validators import TransactionType, parse_amount, parse_tags, validate_date, validate_transaction_type, validate_category_name

CSV_COLUMNS = ("date", "type", "category", "amount", "memo", "tags")
REQUIRED_COLUMNS = frozenset(CSV_COLUMNS[:4])


class CSVTransactionInput(TypedDict):
    date: str
    type: TransactionType
    category: str
    amount: int
    memo: str
    tags: tuple[str, ...]
    source_line: int


def iter_csv(path: Path) -> Iterator[CSVTransactionInput]:
    """행 값에 오류가 있으면 첫 오류의 위치를 보고하고 즉시 전체 가져오기를 중단한다.

    UTF-8 BOM은 입력에서만 허용. 빈 물리 행은 csv.reader의 관례대로 무시한다.
    실제 반영은 이 제너레이터가 끝난 뒤 서비스에서 한 번 수행한다.
    """
    reader = None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            fields = reader.fieldnames
            if (
                not fields
                or len(fields) != len(set(fields))
                or not REQUIRED_COLUMNS <= set(fields)
                or not set(fields) <= set(CSV_COLUMNS)
            ):
                raise ImportDataError(
                    "CSV 헤더가 올바르지 않습니다. imported=0 (전체 미반영)",
                    "필수: date,type,category,amount / 선택: memo,tags. 중복/알 수 없는 열은 허용하지 않습니다.",
                )
            for row in reader:
                line = reader.line_num
                if None in row or any(value is None for value in row.values()):
                    raise ImportDataError(
                        f"CSV {line}행 부근: 열 개수가 헤더와 다릅니다. imported=0 (전체 미반영)",
                        '값 속 쉼표는 큰따옴표로 묶으세요. 예: "meal,lunch". 빈 필드도 구분 쉼표가 필요합니다.',
                    )
                try:
                    yield {
                        "date": validate_date(row["date"].strip()),
                        "type": validate_transaction_type(row["type"].strip()),
                        "category": validate_category_name(row["category"].strip()),
                        "amount": parse_amount(row["amount"]),
                        "memo": row.get("memo", ""),
                        "tags": parse_tags(row.get("tags", "")),
                        "source_line": line,
                    }
                except AppError as exc:
                    raise ImportDataError(
                        f"CSV {line}행 부근: {exc.message} imported=0 (전체 미반영)", exc.hint,
                    ) from exc
    except (csv.Error, UnicodeError) as exc:
        line = reader.line_num if reader is not None else 0
        raise ImportDataError(
            f"CSV {line}행 부근을 읽을 수 없습니다: {exc}. imported=0 (전체 미반영)",
            "UTF-8 인코딩과 큰따옴표/쉼표 구성을 확인하세요. 여러 줄 필드는 끝나는 물리 행 기준입니다.",
        ) from exc


def export_rows(stream: TextIO, transactions: Iterator[Transaction]) -> int:
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    count = 0
    with closing(transactions):
        for transaction in transactions:
            writer.writerow({
                "date": transaction.date, "type": transaction.type,
                "category": transaction.category, "amount": transaction.amount,
                "memo": transaction.memo, "tags": ",".join(transaction.tags),
            })
            count += 1
    return count
