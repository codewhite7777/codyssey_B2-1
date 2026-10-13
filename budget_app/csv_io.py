"""CSV 교환 형식과 내부 거래 모델을 연결한다. 내부 영구 저장 포맷은 JSONL이다.

가져오기: service.import_csv → iter_csv → 헤더/행 검증 → 변환된 사전 yield.
사전의 source_line은 오류 보고용이고, ID는 서비스가 새로 만든다.
여기서 줄 단위로 읽더라도 서비스는 전체 성공 정책을 위해 신규 거래를 목록에 모은다.

내보내기: service.export_csv → export_rows → DictWriter → CSV 텍스트.
CSV 열 구분 쉼표는 csv 모듈이 해석하고, 해석된 tags 열 내부의 쉼표만 별도로 나눈다.
예: "meal,lunch"는 CSV의 한 열이며 프로그램 안에서는 두 태그가 된다.
"""

import csv
from collections.abc import Generator
from contextlib import closing
from pathlib import Path
from typing import TextIO, TypedDict

from .errors import AppError, ImportDataError
from .models import Transaction
from .validators import (
    TransactionType,
    parse_amount,
    parse_tags,
    validate_category_name,
    validate_date,
    validate_transaction_type,
)

CSV_COLUMNS = ("date", "type", "category", "amount", "memo", "tags")
REQUIRED_COLUMNS = frozenset(CSV_COLUMNS[:4])


class CSVTransactionInput(TypedDict):
    """검증 후 서비스로 넘길 사전의 필드 계약. TypedDict 자체가 런타임 검증을 하지는 않는다."""

    date: str
    type: TransactionType
    category: str
    amount: int
    memo: str
    tags: tuple[str, ...]
    source_line: int


def iter_csv(path: Path) -> Generator[CSVTransactionInput, None, None]:
    """행 값에 오류가 있으면 첫 오류의 위치를 보고하고 즉시 전체 가져오기를 중단한다.

    UTF-8 BOM은 입력에서만 허용. 빈 물리 행은 csv.reader의 관례대로 무시한다.
    실제 반영은 이 제너레이터가 끝난 뒤 서비스에서 한 번 수행한다.
    """
    reader = None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            # utf-8-sig는 입력의 BOM도 허용한다. newline=""로 CSV 모듈이 개행을 직접 다루게 한다.
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
                # 남는 열은 None 키, 빠진 열은 None 값으로 나타난다. 조용히 자르거나 채우지 않는다.
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
                        # CSV 한 행을 split(",")하지 않는다. DictReader로 꺼낸 이 필드만 분리한다.
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


def export_rows(stream: TextIO, transactions: Generator[Transaction, None, None]) -> int:
    """거래를 CSV 헤더의 고정 열 순서로 한 건씩 기록하고 기록 건수를 반환한다.

    메모·태그 안의 쉼표와 개행은 csv 모듈에 맡긴다. 소비한 제너레이터는
    종료·오류 시 닫고, 출력 파일의 실제 교체는 호출자가 관리한다.
    """
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
