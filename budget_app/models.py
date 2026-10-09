"""파일 포맷과 화면 출력에 의존하지 않는 도메인 데이터 모델."""

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
        validate_month(self.month)
        validate_amount(self.amount)


def transaction_key(transaction: Transaction) -> tuple[str, str]:
    """날짜 최신순; 같은 날짜는 ID 내림차순. 생성 시각 순서를 뜻하지 않는다."""
    return transaction.date, transaction.id


@dataclass(frozen=True)
class SearchFilter:
    start: str | None = None
    end: str | None = None
    category: str | None = None
    type: TransactionType | None = None
    query: str | None = None
    tag: str | None = None

    def __post_init__(self) -> None:
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
        return (
            (self.start is None or transaction.date >= self.start)
            and (self.end is None or transaction.date <= self.end)
            and (self.category is None or transaction.category == self.category)
            and (self.type is None or transaction.type == self.type)
            and (self.query is None or self.query.casefold() in transaction.memo.casefold())
            and (self.tag is None or self.tag in transaction.tags)
        )


@dataclass(frozen=True)
class MonthSummary:
    month: str
    count: int
    income: int
    expense: int
    top_expenses: tuple[tuple[str, int], ...]
    budget: int | None

    @property
    def balance(self) -> int:
        return self.income - self.expense

    @property
    def exceeded(self) -> bool:
        return self.budget is not None and self.expense > self.budget

    @property
    def usage_percent(self) -> str | None:
        if self.budget is None:
            return None
        # 원 단위 정수를 끝까지 유지하고 표시 시에만 0.1% 단위로 반올림한다.
        tenths = (self.expense * 1000 + self.budget // 2) // self.budget
        return f"{tenths // 10}.{tenths % 10}"
