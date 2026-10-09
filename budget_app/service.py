"""업무 규칙: 등록 확인, CRUD, 검색, 집계, 전체 성공/미반영 CSV 가져오기."""

import calendar
import heapq
import uuid
from collections import defaultdict
from collections.abc import Iterator
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from .csv_io import export_rows, iter_csv
from .errors import ConflictError, ImportDataError, NotFoundError, StorageError, ValidationError
from .models import MonthlyBudget, MonthSummary, SearchFilter, Transaction, transaction_key
from .storage import DataStore, atomic_text
from .validators import TransactionType, validate_category_name, validate_label, validate_month

DEFAULT_LIMIT = 20


def positive_integer(value: int, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValidationError(f"{field}는 양수 정수여야 합니다.", f"{field}에 1 이상의 정수를 지정하세요.")
    return value


def month_filter(month: str) -> SearchFilter:
    validate_month(month)
    year, number = map(int, month.split("-"))
    last = calendar.monthrange(year, number)[1]
    return SearchFilter(start=f"{month}-01", end=f"{month}-{last:02d}")


def export_filter(month: str | None, start: str | None, end: str | None) -> SearchFilter:
    if month is not None:
        if start is not None or end is not None:
            raise ValidationError("--month와 기간 조건은 함께 지정할 수 없습니다.", "--month 또는 --from/--to 쌍 중 하나만 사용하세요.")
        return month_filter(month)
    if start is None or end is None:
        raise ValidationError("내보낼 기간이 필요합니다.", "--month YYYY-MM 또는 --from YYYY-MM-DD --to YYYY-MM-DD를 지정하세요.")
    return SearchFilter(start=start, end=end)


class BudgetService:
    def __init__(self, directory: str | Path = "data") -> None:
        self.store = DataStore(directory)

    def list_categories(self) -> list[str]:
        with self.store.session():
            return sorted(self.store.categories.load())

    def add_category(self, name: str) -> None:
        validate_category_name(name)
        with self.store.session():
            categories = self.store.categories.load()
            if name in categories:
                raise ConflictError(f"이미 등록된 카테고리입니다: {name}", "category list로 목록을 확인하세요.")
            categories.add(name)
            self.store.categories.save(categories)

    def remove_category(self, name: str) -> None:
        validate_category_name(name)
        with self.store.session():
            categories = self.store.categories.load()
            self._require_category(name, categories)
            with closing(self._checked_transactions(categories)) as transactions:
                for transaction in transactions:
                    if transaction.category == name:
                        raise ConflictError(f"사용 중인 카테고리는 삭제할 수 없습니다: {name}", "해당 거래의 카테고리를 수정하거나 거래를 삭제한 후 다시 시도하세요.")
            categories.remove(name)
            self.store.categories.save(categories)

    @staticmethod
    def _require_category(name: str, categories: set[str]) -> None:
        if name not in categories:
            raise ValidationError(f"등록되지 않은 카테고리입니다: {name}", "category list로 확인하거나 category add로 먼저 등록하세요.")

    def _checked_transactions(self, categories: set[str]) -> Iterator[Transaction]:
        with closing(self.store.transactions.iter_transactions()) as transactions:
            for transaction in transactions:
                if transaction.category not in categories:
                    raise StorageError(
                        f"거래 {transaction.id}의 카테고리가 저장 목록에 없습니다: {transaction.category}",
                        "카테고리/거래 파일을 함께 복구하거나 해당 카테고리를 다시 등록하세요.",
                    )
                yield transaction

    def _inspect(self, categories: set[str], target: str | None = None) -> tuple[set[str], Transaction | None]:
        """쓰기 직전에 ID 유일성과 참조 무결성을 전체 검사한다. 조회에는 이 집합을 만들지 않는다."""
        ids: set[str] = set()
        found: Transaction | None = None
        with closing(self._checked_transactions(categories)) as transactions:
            for transaction in transactions:
                if transaction.id in ids:
                    raise StorageError(f"중복 거래 ID가 있습니다: {transaction.id}", "수정을 중단했습니다. 백업과 저장 파일을 확인하세요.")
                ids.add(transaction.id)
                if transaction.id == target:
                    found = transaction
        return ids, found

    @staticmethod
    def _new_id(used: set[str]) -> str:
        for _ in range(10):
            candidate = "TX-" + uuid.uuid4().hex
            if candidate not in used:
                used.add(candidate)
                return candidate
        raise ConflictError("고유 ID를 만들지 못했습니다.", "기존 데이터는 변경하지 않았습니다. 다시 실행하세요.")

    def add(self, *, date: str, type: TransactionType, category: str, amount: int,
            memo: str = "", tags: tuple[str, ...] = ()) -> Transaction:
        # 파일을 만들기 전에 값 자체를 검사한다. 실제 고유 ID는 잠금 안에서 생성한다.
        draft = Transaction("pending", type, date, amount, category, memo, tags)
        with self.store.session():
            categories = self.store.categories.load()
            self._require_category(category, categories)
            ids, _ = self._inspect(categories)
            transaction = replace(draft, id=self._new_id(ids))
            self._rewrite(categories, replacement=transaction)
            return transaction

    def _rewrite(self, categories: set[str], *, excluded: str | None = None,
                 replacement: Transaction | None = None) -> None:
        def merged() -> Iterator[Transaction]:
            inserted = replacement is None
            with closing(self._checked_transactions(categories)) as source:
                for current in source:
                    if current.id == excluded:
                        continue
                    if replacement is not None and not inserted and transaction_key(replacement) > transaction_key(current):
                        yield replacement
                        inserted = True
                    yield current
                if replacement is not None and not inserted:
                    yield replacement
        with closing(merged()) as transactions:
            self.store.transactions.replace_all(transactions)

    def update(self, identifier: str, **changes: object) -> Transaction:
        validate_label(identifier, "거래 id")
        allowed = {"date", "type", "category", "amount", "memo", "tags"}
        if not changes or not changes.keys() <= allowed:
            raise ValidationError("수정할 필드가 없거나 지원하지 않는 필드입니다.", "update --id <id> --amount 1000 등 수정 옵션을 하나 이상 지정하세요.")
        with self.store.session():
            categories = self.store.categories.load()
            _, original = self._inspect(categories, identifier)
            if original is None:
                raise NotFoundError(f"없는 데이터입니다: {identifier}", "list 또는 search로 거래 ID를 확인하세요.")
            transaction = replace(original, **changes)
            self._require_category(transaction.category, categories)
            self._rewrite(categories, excluded=identifier, replacement=transaction)
            return transaction

    def delete(self, identifier: str) -> None:
        validate_label(identifier, "거래 id")
        with self.store.session():
            categories = self.store.categories.load()
            _, transaction = self._inspect(categories, identifier)
            if transaction is None:
                raise NotFoundError(f"없는 데이터입니다: {identifier}", "list 또는 search로 거래 ID를 확인하세요.")
            self._rewrite(categories, excluded=identifier)

    def search(self, filters: SearchFilter | None = None, limit: int | None = None) -> Iterator[Transaction]:
        """거래를 모으거나 정렬하지 않고 하나씩 전달한다. 사용자는 조기 종료 시 close해야 한다."""
        filters = filters or SearchFilter()
        if limit is not None:
            positive_integer(limit, "--limit")
        with self.store.session():
            categories = self.store.categories.load()
            if filters.category is not None:
                self._require_category(filters.category, categories)
            matched = 0
            with closing(self._checked_transactions(categories)) as transactions:
                for transaction in transactions:
                    if filters.matches(transaction):
                        yield transaction
                        matched += 1
                        if limit is not None and matched >= limit:
                            return

    def list_transactions(self, limit: int = DEFAULT_LIMIT) -> Iterator[Transaction]:
        yield from self.search(limit=limit)

    def set_budget(self, month: str, amount: int) -> None:
        budget = MonthlyBudget(month, amount)
        with self.store.session():
            budgets = self.store.budgets.load()
            budgets[month] = budget
            self.store.budgets.save(budgets)

    def get_budget(self, month: str) -> MonthlyBudget | None:
        validate_month(month)
        with self.store.session():
            return self.store.budgets.load().get(month)

    def summary(self, month: str, top: int = 3) -> MonthSummary:
        filters = month_filter(month)
        positive_integer(top, "--top")
        with self.store.session():
            categories = self.store.categories.load()
            budget = self.store.budgets.load().get(month)
            income = expense = count = 0
            amounts: dict[str, int] = defaultdict(int)
            with closing(self._checked_transactions(categories)) as transactions:
                for transaction in transactions:
                    if not filters.matches(transaction):
                        continue
                    count += 1
                    if transaction.type == "income":
                        income += transaction.amount
                    else:
                        expense += transaction.amount
                        amounts[transaction.category] += transaction.amount
            ranking = tuple(sorted(amounts.items(), key=lambda pair: (-pair[1], pair[0]))[:top])
            return MonthSummary(month, count, income, expense, ranking, budget.amount if budget else None)

    def import_csv(self, source: str | Path) -> int:
        with self.store.session():
            path = self.store.check_external_path(source)
            categories = self.store.categories.load()
            ids, _ = self._inspect(categories)
            incoming: list[Transaction] = []
            with closing(iter_csv(path)) as rows:
                for row in rows:
                    if row["category"] not in categories:
                        raise ImportDataError(
                            f"CSV {row['source_line']}행 부근: 미등록 카테고리 {row['category']}. imported=0 (전체 미반영)",
                            "category add로 먼저 등록한 뒤 CSV 전체를 다시 가져오세요.",
                        )
                    incoming.append(Transaction(
                        id=self._new_id(ids), type=row["type"], date=row["date"],
                        amount=row["amount"], category=row["category"], memo=row["memo"], tags=row["tags"],
                    ))
            if not incoming:
                return 0
            incoming.sort(key=transaction_key, reverse=True)
            with closing(self._checked_transactions(categories)) as current:
                merged = heapq.merge(current, incoming, key=transaction_key, reverse=True)
                with closing(merged):
                    self.store.transactions.replace_all(merged)
            return len(incoming)

    def export_csv(self, destination: str | Path, *, month: str | None = None,
                   start: str | None = None, end: str | None = None) -> int:
        filters = export_filter(month, start, end)
        with self.store.session():
            path = self.store.check_external_path(destination)
            categories = self.store.categories.load()
            # 필터로 걸러진 구간 밖도 읽으므로 손상 파일을 정상 CSV로 위장하지 않는다.
            def selected() -> Iterator[Transaction]:
                with closing(self._checked_transactions(categories)) as transactions:
                    for transaction in transactions:
                        if filters.matches(transaction):
                            yield transaction
            with atomic_text(path) as stream:
                return export_rows(stream, selected())
