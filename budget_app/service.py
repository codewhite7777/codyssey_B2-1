"""업무 규칙: 등록 확인, CRUD, 검색, 집계, 전체 성공/미반영 CSV 가져오기."""

import calendar
import heapq
import uuid
from collections import defaultdict
from collections.abc import Generator
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
    """limit·top 같은 개수 옵션이 양수 정수인지 확인하고 같은 값을 반환한다.

    bool도 거부하며 오류에는 field로 받은 옵션 이름을 포함한다.
    """
    if type(value) is not int or value <= 0:
        raise ValidationError(f"{field}는 양수 정수여야 합니다.", f"{field}에 1 이상의 정수를 지정하세요.")
    return value


def month_filter(month: str) -> SearchFilter:
    """YYYY-MM을 검증한 뒤 그달 첫날과 마지막 날을 포함하는 검색 조건을 반환한다.

    calendar.monthrange로 윤년과 월별 일수를 계산하므로 다음 달 날짜를 만들 필요가 없다.
    """
    validate_month(month)
    year, number = map(int, month.split("-"))
    last = calendar.monthrange(year, number)[1]
    return SearchFilter(start=f"{month}-01", end=f"{month}-{last:02d}")


def export_filter(month: str | None, start: str | None, end: str | None) -> SearchFilter:
    """내보내기의 월 조건 또는 완전한 기간쌍을 검색 조건으로 변환한다.

    월과 기간을 섞거나 시작·종료일 중 하나가 빠지면 ValidationError로 거부한다.
    이는 이 구현에서 선택한 내보내기 정책이며 search는 열린 기간도 지원한다.
    """
    if month is not None:
        if start is not None or end is not None:
            raise ValidationError("--month와 기간 조건은 함께 지정할 수 없습니다.", "--month 또는 --from/--to 쌍 중 하나만 사용하세요.")
        return month_filter(month)
    if start is None or end is None:
        raise ValidationError(
            "내보낼 기간이 필요합니다.",
            "--month YYYY-MM 또는 --from YYYY-MM-DD --to YYYY-MM-DD를 지정하세요.",
        )
    return SearchFilter(start=start, end=end)


class BudgetService:
    def __init__(self, directory: str | Path = "data") -> None:
        """지정한 폴더를 사용하는 DataStore를 준비한다. 실제 초기화·잠금은 작업 시 수행한다."""
        self.store = DataStore(directory)

    def list_categories(self) -> list[str]:
        """잠금 안에서 카테고리를 읽고 이름 오름차순 목록으로 반환한다.

        처음 접근한 폴더는 session에서 초기화하며 등록된 이름이 없으면 빈 목록을 반환한다.
        """
        with self.store.session():
            return sorted(self.store.categories.load())

    def add_category(self, name: str) -> None:
        """이름을 검증하고 중복 여부를 확인한 뒤 카테고리 파일에 저장한다.

        중복이면 ConflictError를 내며 기존 목록을 변경하지 않는다.
        """
        validate_category_name(name)
        with self.store.session():
            categories = self.store.categories.load()
            if name in categories:
                raise ConflictError(f"이미 등록된 카테고리입니다: {name}", "category list로 목록을 확인하세요.")
            categories.add(name)
            self.store.categories.save(categories)

    def remove_category(self, name: str) -> None:
        """등록된 이름인지 확인하고 사용하는 거래가 없을 때만 카테고리를 삭제한다.

        거래를 한 건씩 확인하다 사용 중이면 ConflictError로 중단한다.
        데이터 손상도 건너뛰지 않으며 자동으로 다른 카테고리로 이전하지 않는다.
        """
        validate_category_name(name)
        with self.store.session():
            categories = self.store.categories.load()
            self._require_category(name, categories)
            with closing(self._checked_transactions(categories)) as transactions:
                for transaction in transactions:
                    if transaction.category == name:
                        raise ConflictError(
                            f"사용 중인 카테고리는 삭제할 수 없습니다: {name}",
                            "해당 거래의 카테고리를 수정하거나 거래를 삭제한 후 다시 시도하세요.",
                        )
            categories.remove(name)
            self.store.categories.save(categories)

    @staticmethod
    def _require_category(name: str, categories: set[str]) -> None:
        """카테고리 집합에 이름이 있는지 확인하고 없으면 등록 방법을 포함한 오류를 낸다."""
        if name not in categories:
            raise ValidationError(f"등록되지 않은 카테고리입니다: {name}", "category list로 확인하거나 category add로 먼저 등록하세요.")

    def _checked_transactions(self, categories: set[str]) -> Generator[Transaction, None, None]:
        """저장소의 거래를 순회하며 카테고리 참조가 유효한 거래만 한 건씩 전달한다.

        호출자는 session 잠금 안에서 소비한다. 등록 목록에 없는 카테고리는
        저장 데이터 손상으로 처리하며 조기 종료해도 내부 파일 제너레이터를 닫는다.
        """
        with closing(self.store.transactions.iter_transactions()) as transactions:
            for transaction in transactions:
                if transaction.category not in categories:
                    raise StorageError(
                        f"거래 {transaction.id}의 카테고리가 저장 목록에 없습니다: {transaction.category}",
                        "카테고리/거래 파일을 함께 복구하거나 해당 카테고리를 다시 등록하세요.",
                    )
                yield transaction

    def _inspect(
        self, categories: set[str], target: str | None = None,
    ) -> tuple[set[str], Transaction | None]:
        """거래 파일 변경 전에 전체 ID 중복을 검사하고 ID 집합과 대상 거래를 반환한다.

        categories로 참조 무결성도 검사하고, target이 없거나 못 찾으면 대상은 None이다.
        ID 집합은 거래 수에 비례한 메모리를 사용하므로 list/search에서는 호출하지 않는다.
        """
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
        """기존 ID와 겹치지 않는 UUID 기반 ID를 만들어 used 집합에 추가하고 반환한다.

        충돌 시 최대 10번 재시도하며 모두 실패하면 ConflictError로 저장을 중단한다.
        used도 변경하므로 CSV 한 번에 가져오는 신규 거래끼리의 충돌도 막는다.
        """
        for _ in range(10):
            candidate = "TX-" + uuid.uuid4().hex
            if candidate not in used:
                used.add(candidate)
                return candidate
        raise ConflictError("고유 ID를 만들지 못했습니다.", "기존 데이터는 변경하지 않았습니다. 다시 실행하세요.")

    def add(self, *, date: str, type: TransactionType, category: str, amount: int,
            memo: str = "", tags: tuple[str, ...] = ()) -> Transaction:
        """거래 필드를 검증하고 등록 카테고리·ID 중복을 확인한 뒤 새 거래를 저장한다.

        임시 모델 검증 후 잠금 안에서 실제 ID를 부여하고 _rewrite로 최신순을 유지한다.
        저장에 성공한 Transaction을 반환하며 화면 입력·출력은 하지 않는다.
        """
        # 파일을 만들기 전에 값 자체를 검사한다. 실제 고유 ID는 잠금 안에서 생성한다.
        draft = Transaction(
            id="pending", type=type, date=date, amount=amount,
            category=category, memo=memo, tags=tags,
        )
        with self.store.session():
            categories = self.store.categories.load()
            self._require_category(category, categories)
            ids, _ = self._inspect(categories)
            transaction = replace(draft, id=self._new_id(ids))
            self._rewrite(categories, replacement=transaction)
            return transaction

    def _rewrite(self, categories: set[str], *, excluded: str | None = None,
                 replacement: Transaction | None = None) -> None:
        """삭제 대상은 제외하고 추가·수정 거래는 정렬 위치에 넣어 거래 파일을 교체한다.

        excluded는 제외할 ID, replacement는 삽입할 거래이며 둘 다 선택적이다.
        잠금과 사전 검사를 마친 호출자만 사용한다. 결과는 임시 파일로 쓰므로
        교체 전에 오류가 나면 원본은 유지되고, 전체 거래를 목록으로 모으지 않는다.
        """
        def merged() -> Generator[Transaction, None, None]:
            """기존 거래 순서를 따라가며 제외할 ID를 건너뛰고 새 거래를 한 번만 끼워 넣는다.

            삽입할 거래가 가장 오래되었거나 파일이 비었다면 순회 끝에서 전달한다.
            replacement가 없을 때는 삭제 대상 외의 기존 거래만 전달한다.
            """
            inserted = replacement is None
            with closing(self._checked_transactions(categories)) as source:
                for current in source:
                    if current.id == excluded:
                        continue
                    if (
                        replacement is not None
                        and not inserted
                        and transaction_key(replacement) > transaction_key(current)
                    ):
                        yield replacement
                        inserted = True
                    yield current
                if replacement is not None and not inserted:
                    yield replacement
        with closing(merged()) as transactions:
            self.store.transactions.replace_all(transactions)

    def update(self, identifier: str, **changes: object) -> Transaction:
        """ID로 거래를 찾고 지정된 필드만 변경한 새 객체를 검증·저장해 반환한다.

        수정할 필드가 없거나 허용되지 않은 필드면 거부하고, 없는 ID는 NotFoundError다.
        ID와 생략된 값은 유지하며 날짜 변경 시 _rewrite가 저장 순서를 다시 맞춘다.
        """
        validate_label(identifier, "거래 id")
        allowed = {"date", "type", "category", "amount", "memo", "tags"}
        unknown_fields = changes.keys() - allowed
        if not changes or unknown_fields:
            raise ValidationError(
                "수정할 필드가 없거나 지원하지 않는 필드입니다.",
                "update --id <id> --amount 1000 등 수정 옵션을 하나 이상 지정하세요.",
            )
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
        """ID 존재 여부를 확인한 뒤 그 거래를 제외한 내용으로 파일을 교체한다.

        없는 ID는 NotFoundError로 알리고, 마지막 거래를 지우면 빈 거래 파일을 남긴다.
        """
        validate_label(identifier, "거래 id")
        with self.store.session():
            categories = self.store.categories.load()
            _, transaction = self._inspect(categories, identifier)
            if transaction is None:
                raise NotFoundError(f"없는 데이터입니다: {identifier}", "list 또는 search로 거래 ID를 확인하세요.")
            self._rewrite(categories, excluded=identifier)

    def search(
        self, filters: SearchFilter | None = None, limit: int | None = None,
    ) -> Generator[Transaction, None, None]:
        """지정된 조건을 모두 만족하는 거래를 최신순으로 한 건씩 전달한다.

        filters가 없으면 모든 거래, limit이 없으면 일치하는 전체 결과를 읽는다.
        제너레이터를 실제 소비할 때 잠금·파일 접근이 시작되며 전체 목록/재정렬은 없다.
        조기 중단하는 호출자는 close해야 한다. limit 뒤의 손상은 이 조회에서 검사하지 않는다.
        """
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

    def list_transactions(self, limit: int = DEFAULT_LIMIT) -> Generator[Transaction, None, None]:
        """조건 없는 search에 limit을 전달해 최신 거래를 지정 개수만큼 전달한다.

        yield from으로 검색 제너레이터의 값과 종료·close 처리를 그대로 연결한다.
        """
        yield from self.search(limit=limit)

    def set_budget(self, month: str, amount: int) -> None:
        """월과 금액을 검증한 예산 객체를 만들고 해당 월의 예산을 추가하거나 교체한다.

        다른 월 예산은 유지하며 잠금 안에서 예산 파일만 다시 저장한다.
        """
        budget = MonthlyBudget(month, amount)
        with self.store.session():
            budgets = self.store.budgets.load()
            budgets[month] = budget
            self.store.budgets.save(budgets)

    def get_budget(self, month: str) -> MonthlyBudget | None:
        """월을 검증하고 저장된 예산을 반환한다. 그달 예산이 없으면 None을 반환한다."""
        validate_month(month)
        with self.store.session():
            return self.store.budgets.load().get(month)

    def summary(self, month: str, top: int = 3) -> MonthSummary:
        """해당 월 거래를 한 건씩 읽어 수입·지출·카테고리별 지출과 예산을 집계한다.

        거래 자체는 보관하지 않고 합계만 유지한다. 지출 순위는 금액 내림차순,
        동률이면 이름 오름차순으로 top개를 선택하여 MonthSummary로 반환한다.
        """
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
            # 거래 전체가 아니라 카테고리별 합계만 정렬한다.
            ranked_categories = sorted(amounts.items(), key=lambda pair: (-pair[1], pair[0]))
            ranking = tuple(ranked_categories[:top])
            return MonthSummary(
                month=month, count=count, income=income, expense=expense,
                top_expenses=ranking, budget=budget.amount if budget else None,
            )

    def import_csv(self, source: str | Path) -> int:
        """CSV 전체를 검증하고 신규 ID를 부여한 후 기존 거래와 병합 저장하여 건수를 반환한다.

        모든 신규 거래를 메모리에 모아 정렬하므로 이 기능 전체가 상수 메모리는 아니다.
        한 행이라도 틀리면 교체 전 중단해 거래를 0건 반영한다. 헤더만 있으면 0을 반환한다.
        내용 중복은 제거하지 않으며 같은 파일을 다시 가져오면 신규 거래로 추가된다.
        """
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
            # 여기까지는 검증·준비 단계다. 이후 병합 파일이 완성되어야 실제 반영한다.
            incoming.sort(key=transaction_key, reverse=True)
            with closing(self._checked_transactions(categories)) as current:
                merged = heapq.merge(current, incoming, key=transaction_key, reverse=True)
                with closing(merged):
                    self.store.transactions.replace_all(merged)
            return len(incoming)

    def export_csv(self, destination: str | Path, *, month: str | None = None,
                   start: str | None = None, end: str | None = None) -> int:
        """월 또는 기간에 해당하는 거래를 CSV 임시 파일에 쓰고 성공 시 출력 파일을 교체한다.

        내부 저장 파일을 출력 대상으로 지정하는 것을 막고 저장한 거래 건수를 반환한다.
        기존 출력 파일은 교체 전 실패하면 유지된다. 조건에 맞는 거래가 없으면 헤더만 쓴다.
        """
        filters = export_filter(month, start, end)
        with self.store.session():
            path = self.store.check_external_path(destination)
            categories = self.store.categories.load()
            # 필터로 걸러진 구간 밖도 읽으므로 손상 파일을 정상 CSV로 위장하지 않는다.
            def selected() -> Generator[Transaction, None, None]:
                """전체 거래의 유효성을 확인하면서 내보낼 기간에 속하는 거래만 전달한다.

                범위 밖의 행도 읽어 검사하므로 그곳의 손상도 내보내기 실패로 알린다.
                """
                with closing(self._checked_transactions(categories)) as transactions:
                    for transaction in transactions:
                        if filters.matches(transaction):
                            yield transaction
            with atomic_text(path) as stream:
                return export_rows(stream, selected())
