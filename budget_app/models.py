"""거래·월 예산·검색 조건·요약 결과의 데이터 구조와 값 자체의 규칙.

입력 문자열 변환은 validators, 카테고리 등록/ID 중복 확인은 service,
JSONL 변환은 storage가 담당한다. 이 파일은 input/print/파일 작업을 하지 않는다.

Transaction 생성 → dataclass가 필드 초기화 → __post_init__에서 검증.
수정은 원본 필드를 바꾸는 대신 dataclasses.replace로 새 객체를 만들어 재검증한다.
예: amount=15000은 금액이고 type="expense"가 지출을 뜻하므로 음수를 저장하지 않는다.
frozen=True는 객체 재할당 제한이지, 디스크 파일의 원자적 저장 기능이 아니다.
"""

from dataclasses import dataclass

from .errors import ValidationError

from .validators import (
    TransactionType,
    validate_amount,
    validate_category_name,
    validate_date,
    validate_label,
    validate_memo,
    validate_month,
    validate_tags,
    validate_transaction_type,
)


@dataclass(frozen=True)
class Transaction:
    """한 건의 거래. 객체 생성 경로에 관계없이 값 자체의 규칙을 확인한다.

    id의 저장소 내 유일성과 카테고리 등록 여부는 서비스/저장소에서 확인한다.
    frozen=True는 일반적인 필드 재할당을 막지만 파일 저장 원자성과는 다르다.
    """

    id: str
    type: TransactionType
    date: str
    amount: int
    category: str
    memo: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """거래 객체가 만들어질 때 모든 필드의 값 자체를 검증한다.

        잘못된 값은 ValidationError로 거부한다. 카테고리 등록 여부와 ID 중복은
        파일 조회가 필요하므로 여기서 검사하지 않고 서비스에 맡긴다.
        """
        validate_label(self.id, "거래 id")
        validate_transaction_type(self.type)
        validate_date(self.date)
        validate_amount(self.amount)
        validate_category_name(self.category)
        validate_memo(self.memo)
        validate_tags(self.tags)


@dataclass(frozen=True)
class MonthlyBudget:
    """하나의 월에 대응하는 양수 정수 예산."""

    month: str
    amount: int

    def __post_init__(self) -> None:
        """월 형식과 예산의 양수 정수 조건을 검사해 잘못된 예산 객체 생성을 막는다."""
        validate_month(self.month)
        validate_amount(self.amount)


def transaction_key(transaction: Transaction) -> tuple[str, str]:
    """거래의 정렬 기준인 (날짜, ID)를 반환한다.

    호출 측이 내림차순으로 사용한다. 같은 날짜의 ID 순서는 등록 시각순이 아니다.
    """
    # 검증된 고정 폭 YYYY-MM-DD 문자열은 문자열 비교와 날짜 순서가 일치한다.
    return transaction.date, transaction.id


@dataclass(frozen=True)
class SearchFilter:
    """검색 조건 묶음. None은 조건 생략이며 matches가 한 거래의 일치 여부를 판정한다."""

    start: str | None = None
    end: str | None = None
    category: str | None = None
    type: TransactionType | None = None
    query: str | None = None
    tag: str | None = None

    def __post_init__(self) -> None:
        """지정된 검색 조건만 검증하고 시작일이 종료일보다 늦으면 거부한다.

        None은 해당 조건을 적용하지 않는다는 뜻이다. 카테고리의 등록 여부는
        조건 객체가 아니라 실제 검색을 실행하는 서비스가 확인한다.
        """
        if self.start is not None:
            validate_date(self.start)
        if self.end is not None:
            validate_date(self.end)
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValidationError("시작일이 종료일보다 늦습니다.", "--from 날짜를 --to 날짜 이전 또는 같은 날로 지정하세요.")
        if self.category is not None:
            validate_category_name(self.category)
        if self.type is not None:
            validate_transaction_type(self.type)
        if self.query is not None:
            validate_memo(self.query)
        if self.tag is not None:
            validate_tags((self.tag,))

    def matches(self, transaction: Transaction) -> bool:
        """거래가 지정된 모든 검색 조건을 만족하는지 True 또는 False로 반환한다.

        기간은 양 끝을 포함하고, 메모는 대소문자 없는 부분 문자열로 비교한다.
        카테고리·타입·태그는 정확히 비교하며 하나라도 다르면 즉시 False를 반환한다.
        """
        # 예: --category food --type expense는 둘 다 맞아야 한다(AND).
        # 기간의 경계 날짜 자체는 제외하지 않도록 <와 >로 범위 밖만 거른다.
        if self.start is not None and transaction.date < self.start:
            return False
        if self.end is not None and transaction.date > self.end:
            return False
        if self.category is not None and transaction.category != self.category:
            return False
        if self.type is not None and transaction.type != self.type:
            return False
        if self.query is not None and self.query.casefold() not in transaction.memo.casefold():
            return False
        if self.tag is not None and self.tag not in transaction.tags:
            return False
        return True


@dataclass(frozen=True)
class MonthSummary:
    """서비스가 계산한 결과 묶음. count는 거래 수, top_expenses는 (분류, 합계)의 튜플이다.

    이 객체를 만드는 summary가 값과 예산을 검증·계산한다. 자체 입력 폼이 아니며,
    balance 등의 property는 저장된 합계로 계산할 뿐 파일을 다시 읽지 않는다.
    """

    month: str
    count: int
    income: int
    expense: int
    top_expenses: tuple[tuple[str, int], ...]
    budget: int | None

    @property
    def balance(self) -> int:
        """기록된 총수입에서 총지출을 빼 월 잔액을 반환한다. 실제 계좌 조회는 하지 않는다."""
        return self.income - self.expense

    @property
    def exceeded(self) -> bool:
        """예산이 설정되어 있고 지출이 그 예산보다 큰 경우에만 True를 반환한다."""
        return self.budget is not None and self.expense > self.budget

    @property
    def usage_percent(self) -> str | None:
        """예산 사용률을 소수 첫째 자리 문자열로 반환하며 미설정이면 None을 반환한다.

        지출/예산을 0.1% 단위 정수로 반올림한 뒤 문자열로 조합한다.
        float로 바꾸지 않아 큰 금액의 변환 오류를 피하며 초과 판정은 exceeded가 따로 한다.
        """
        if self.budget is None:
            return None
        # 원 단위 정수를 끝까지 유지하고 표시 시에만 0.1% 단위로 반올림한다.
        # 15000/50000 → 300(0.1% 단위) → "30.0". 화면 반올림과 실제 초과 판정은 분리한다.
        tenths = (self.expense * 1000 + self.budget // 2) // self.budget
        return f"{tenths // 10}.{tenths % 10}"
