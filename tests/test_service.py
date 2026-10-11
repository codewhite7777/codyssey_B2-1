import inspect
from contextlib import closing
from dataclasses import asdict
from unittest.mock import patch

from budget_app.errors import ConflictError, NotFoundError, StorageError, ValidationError
from budget_app.models import SearchFilter, Transaction, transaction_key
from budget_app.service import BudgetService, export_filter, month_filter
from budget_app.storage import LOCK_NAME, write_record
from tests.common import ServiceCase


class TransactionServiceTests(ServiceCase):
    def test_add_persists_across_new_service(self):
        """거래를 추가한 뒤 새 서비스 객체로 읽어 ID와 전체 데이터의 영구 저장을 확인한다."""
        added = self.add()
        self.assertTrue(added.id.startswith("TX-"))
        self.assertEqual(list(BudgetService(self.data).list_transactions()), [added])

    def test_unique_ids(self):
        """같은 내용의 거래를 여러 번 추가하고 생성된 ID가 모두 다른지 확인한다."""
        added = [self.add() for _ in range(15)]
        self.assertEqual(len({t.id for t in added}), 15)

    def test_add_requires_registered_category(self):
        """미등록 카테고리 추가를 거부하고 세 저장 파일이 바뀌지 않는지 비교한다."""
        before = self.snapshot()
        with self.assertRaises(ValidationError):
            self.add(category="unknown")
        self.assertEqual(self.snapshot(), before)

    def test_add_invalid_values_do_not_change_files(self):
        """잘못된 날짜·금액·타입·태그를 각각 추가해 거부와 원본 보존을 확인한다."""
        before = self.snapshot()
        for changes in (dict(date="2026-02-30"), dict(amount=0), dict(amount=-1),
                        dict(amount=True), dict(type="payment"), dict(tags=["meal"])):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.add(**changes)
            self.assertEqual(self.snapshot(), before)

    def test_list_orders_by_date_and_id(self):
        """순서를 섞어 추가한 거래를 날짜·ID 내림차순 기준 결과와 비교한다."""
        values = [self.add(date=value) for value in ("2026-10-01", "2025-01-01", "2026-12-31", "2026-10-01")]
        self.assertEqual(list(self.service.list_transactions()), sorted(values, key=transaction_key, reverse=True))

    def test_list_default_and_explicit_limit(self):
        """25건을 추가해 기본 20건과 명시한 3건 제한을 각각 확인한다."""
        for day in range(1, 26):
            self.add(date=f"2026-10-{day:02}")
        self.assertEqual(len(list(self.service.list_transactions())), 20)
        self.assertEqual(len(list(self.service.list_transactions(3))), 3)

    def test_invalid_limit(self):
        """0·음수·bool·소수 개수 제한을 넣어 모두 오류가 나는지 확인한다."""
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                list(self.service.list_transactions(limit))

    def test_update_preserves_id_and_other_fields(self):
        """금액만 수정하고 ID·메모·저장 후 결과가 유지되는지 비교한다."""
        transaction = self.add()
        updated = self.service.update(transaction.id, amount=1234)
        self.assertEqual(updated.id, transaction.id)
        self.assertEqual(updated.memo, transaction.memo)
        self.assertEqual(updated.amount, 1234)
        self.assertEqual(list(self.service.list_transactions()), [updated])

    def test_update_date_repositions_in_sorted_file(self):
        """한 거래의 날짜를 최신과 가장 오래된 날짜로 바꾸어 저장 위치가 함께 이동하는지 확인한다."""
        old = self.add(date="2026-01-01")
        middle = self.add(date="2026-06-01")
        newer = self.service.update(old.id, date="2026-12-01")
        self.assertEqual(list(self.service.list_transactions()), [newer, middle])
        oldest = self.service.update(newer.id, date="2025-12-01")
        self.assertEqual(list(self.service.list_transactions()), [middle, oldest])

    def test_update_all_mutable_fields_and_clear_optional(self):
        """수정 가능한 필드를 함께 바꾸고 빈 메모·태그로 기존 값을 지울 수 있는지 확인한다."""
        original = self.add()
        updated = self.service.update(original.id, date="2025-01-01", type="income", category="salary",
                                      amount=99, memo="", tags=())
        self.assertEqual((updated.type, updated.category, updated.memo, updated.tags), ("income", "salary", "", ()))

    def test_update_missing_id(self):
        """없는 ID 수정은 NotFoundError이고 저장 파일도 그대로인지 확인한다."""
        before = self.snapshot()
        with self.assertRaises(NotFoundError):
            self.service.update("missing", amount=10)
        self.assertEqual(before, self.snapshot())

    def test_update_rejects_empty_unknown_changes(self):
        """수정 필드 생략과 ID 자체 변경을 요청해 둘 다 거부되는지 확인한다."""
        original = self.add()
        for changes in ({}, {"id": "overwrite"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.service.update(original.id, **changes)

    def test_update_invalid_category_or_value_preserves_original(self):
        """미등록 카테고리·0원·잘못된 날짜 수정이 거부되며 원본이 유지되는지 비교한다."""
        original = self.add()
        before = self.snapshot()
        for changes in ({"category": "unknown"}, {"amount": 0}, {"date": "invalid"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.service.update(original.id, **changes)
            self.assertEqual(before, self.snapshot())

    def test_delete_existing(self):
        """두 거래 중 하나만 삭제하고 나머지 거래가 그대로 남는지 확인한다."""
        first = self.add(date="2026-10-01")
        second = self.add(date="2026-10-02")
        self.service.delete(first.id)
        self.assertEqual(list(self.service.list_transactions()), [second])

    def test_delete_last_transaction(self):
        """마지막 거래를 삭제해 빈 파일과 빈 조회 결과가 남는지 확인한다."""
        transaction = self.add()
        self.service.delete(transaction.id)
        self.assertEqual((self.data / "transactions.jsonl").read_bytes(), b"")
        self.assertEqual(list(self.service.list_transactions()), [])

    def test_delete_missing_id_no_changes(self):
        """없는 ID 삭제가 오류로 끝나고 세 파일이 변경되지 않는지 비교한다."""
        before = self.snapshot()
        with self.assertRaises(NotFoundError):
            self.service.delete("missing")
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_id_with_different_dates_blocks_write(self):
        """날짜가 다른 중복 ID 파일을 직접 구성해 다음 쓰기에서 중복을 발견하고 원본을 지키는지 확인한다."""
        first = Transaction("duplicate", "expense", "2026-10-06", 1, "food")
        second = Transaction("duplicate", "expense", "2026-10-05", 2, "food")
        with (self.data / "transactions.jsonl").open("w", encoding="utf-8") as stream:
            for value in (first, second):
                write_record(stream, asdict(value))
        before = self.snapshot()
        with self.assertRaises(StorageError):
            self.add()
        self.assertEqual(self.snapshot(), before)

    def test_forced_id_collision_is_retried(self):
        """UUID 결과를 고정해 충돌 재시도를 유발하고 실패한 추가가 원본을 바꾸지 않는지 확인한다."""
        class Fixed:
            hex = "same"
        with patch("budget_app.service.uuid.uuid4", return_value=Fixed()):
            self.add()
            before = self.snapshot()
            with self.assertRaises(ConflictError):
                self.add()
        self.assertEqual(self.snapshot(), before)

    def test_generators_are_lazy(self):
        """목록·검색이 제너레이터이며 소비 전에는 저장소 세션에 접근하지 않는지 확인한다."""
        self.assertTrue(inspect.isgenerator(self.service.list_transactions()))
        self.assertTrue(inspect.isgenerator(self.service.search()))
        with patch.object(self.service.store, "session", side_effect=AssertionError("not yet")):
            generator = self.service.search()
            generator.close()

    def test_limit_does_not_read_an_extra_record(self):
        """첫 거래 다음에 읽기 실패를 배치해 limit=1이 추가 행을 소비하지 않는지 확인한다."""
        first = self.add()
        def source(categories):
            """거래 하나를 전달한 뒤 오류를 내어 제한 이후의 불필요한 읽기를 탐지한다."""
            yield first
            raise AssertionError("limit 이후 거래를 읽었습니다")
        with patch.object(self.service, "_checked_transactions", side_effect=source):
            self.assertEqual(list(self.service.list_transactions(1)), [first])

    def test_early_close_releases_lock(self):
        """검색을 한 건만 소비하고 close하여 잠금 파일이 제거되는지 확인한다."""
        self.add()
        generator = self.service.search()
        next(generator)
        self.assertTrue((self.data / LOCK_NAME).exists())
        generator.close()
        self.assertFalse((self.data / LOCK_NAME).exists())


class SearchTests(ServiceCase):
    def setUp(self):
        """서로 다른 날짜·분류·타입·메모·태그의 세 거래를 공통 검색 대상으로 준비한다."""
        super().setUp()
        self.first = self.add(date="2026-10-01", memo="Lunch MEAL", tags=("meal", "work"))
        self.second = self.add(date="2026-10-02", category="transport", memo="버스", tags=("commute",))
        self.third = self.add(date="2026-11-01", type="income", category="salary", memo="급여", tags=())

    def results(self, **fields):
        """전달받은 검색 필드로 조건을 만들어 일치 거래를 비교용 목록으로 반환한다."""
        return list(self.service.search(SearchFilter(**fields)))

    def test_search_inclusive_range(self):
        """시작일·종료일에 정확히 해당하는 거래도 검색 결과에 포함되는지 확인한다."""
        self.assertEqual(self.results(start="2026-10-01", end="2026-10-02"), [self.second, self.first])

    def test_search_open_range(self):
        """시작일만 또는 종료일만 지정해 열린 기간 검색이 동작하는지 확인한다."""
        self.assertEqual(self.results(start="2026-11-01"), [self.third])
        self.assertEqual(self.results(end="2026-10-01"), [self.first])

    def test_search_category(self):
        """카테고리가 정확히 일치하는 거래만 반환되는지 확인한다."""
        self.assertEqual(self.results(category="transport"), [self.second])

    def test_search_type(self):
        """income 조건으로 수입 거래만 반환되는지 확인한다."""
        self.assertEqual(self.results(type="income"), [self.third])

    def test_search_casefold_memo(self):
        """메모 검색어의 대소문자를 달리하여 부분 문자열 비교가 대소문자를 무시하는지 확인한다."""
        self.assertEqual(self.results(query="lunch meal"), [self.first])

    def test_search_exact_tag(self):
        """정확한 태그는 찾되 일부 문자열과 대소문자가 다른 태그는 찾지 않는지 확인한다."""
        self.assertEqual(self.results(tag="meal"), [self.first])
        self.assertEqual(self.results(tag="mea"), [])
        self.assertEqual(self.results(tag="Meal"), [])

    def test_search_conditions_are_and(self):
        """여러 조건을 동시에 지정해 전부 일치할 때만 거래가 반환되는지 확인한다."""
        self.assertEqual(self.results(category="food", type="expense", query="lunch", tag="work",
                                      start="2026-10-01", end="2026-10-01"), [self.first])
        self.assertEqual(self.results(category="food", type="income"), [])

    def test_unknown_category_is_error(self):
        """등록하지 않은 카테고리 검색을 빈 결과 대신 입력 오류로 처리하는지 확인한다."""
        with self.assertRaises(ValidationError):
            self.results(category="unknown")

    def test_bad_filters(self):
        """역전된 기간·잘못된 날짜·타입·태그를 조건 생성 단계에서 거부하는지 확인한다."""
        for fields in ({"start": "2026-10-02", "end": "2026-10-01"}, {"start": "2026-13-01"},
                       {"type": "other"}, {"tag": "a,b"}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                SearchFilter(**fields)


class CategoryAndBudgetTests(ServiceCase):
    def test_category_add_and_persistence(self):
        """한글 카테고리 등록 후 새 서비스로 읽어 데이터 유지를 확인한다."""
        self.service.add_category("카페")
        self.assertIn("카페", BudgetService(self.data).list_categories())

    def test_category_duplicate_error(self):
        """이미 등록된 카테고리를 다시 추가하면 충돌 오류가 나는지 확인한다."""
        with self.assertRaises(ConflictError):
            self.service.add_category("food")

    def test_category_remove_unused(self):
        """사용하지 않는 카테고리를 삭제하고 목록에서 사라졌는지 확인한다."""
        self.service.remove_category("rent")
        self.assertNotIn("rent", self.service.list_categories())

    def test_category_remove_used_is_blocked(self):
        """사용 중인 카테고리 삭제를 거부하고 모든 저장 파일이 유지되는지 확인한다."""
        self.add()
        before = self.snapshot()
        with self.assertRaises(ConflictError):
            self.service.remove_category("food")
        self.assertEqual(self.snapshot(), before)

    def test_category_remove_missing(self):
        """없는 카테고리 삭제가 검증 오류로 처리되는지 확인한다."""
        with self.assertRaises(ValidationError):
            self.service.remove_category("missing")

    def test_category_after_delete_is_removable(self):
        """해당 거래를 지운 뒤에는 카테고리 삭제가 허용되는지 확인한다."""
        transaction = self.add()
        self.service.delete(transaction.id)
        self.service.remove_category("food")
        self.assertNotIn("food", self.service.list_categories())

    def test_budget_set_get_replace_persistence(self):
        """두 월 예산을 저장하고 하나만 변경한 뒤 새 서비스에서 각각의 금액을 확인한다."""
        self.service.set_budget("2026-10", 500000)
        self.service.set_budget("2026-11", 700000)
        self.service.set_budget("2026-10", 600000)
        reloaded = BudgetService(self.data)
        self.assertEqual(reloaded.get_budget("2026-10").amount, 600000)
        self.assertEqual(reloaded.get_budget("2026-11").amount, 700000)
        self.assertIsNone(reloaded.get_budget("2026-12"))

    def test_budget_invalid(self):
        """잘못된 월·0·음수·bool 예산을 거부하는지 확인한다."""
        for month, amount in (("2026-13", 1), ("2026-10", 0), ("2026-10", -1), ("2026-10", True)):
            with self.subTest(month=month, amount=amount), self.assertRaises(ValidationError):
                self.service.set_budget(month, amount)

    def test_summary_exact_totals_and_ranking(self):
        """기준 거래와 다른 달 거래를 섞어 월 합계·지출 순위·예산 43.0%를 비교한다."""
        self.add(type="income", category="salary", amount=3000000)
        self.add(category="rent", amount=150000)
        self.add(category="food", amount=45000)
        self.add(category="transport", amount=20000)
        self.add(date="2026-09-30", amount=9999999)
        self.service.set_budget("2026-10", 500000)
        summary = self.service.summary("2026-10")
        self.assertEqual((summary.income, summary.expense, summary.balance), (3000000, 215000, 2785000))
        self.assertEqual(summary.top_expenses, (("rent", 150000), ("food", 45000), ("transport", 20000)))
        self.assertEqual(summary.usage_percent, "43.0")
        self.assertFalse(summary.exceeded)

    def test_summary_equal_budget_not_exceeded(self):
        """지출이 예산과 같으면 사용률은 100.0%이고 초과는 아닌지 확인한다."""
        self.add(amount=100)
        self.service.set_budget("2026-10", 100)
        result = self.service.summary("2026-10")
        self.assertEqual(result.usage_percent, "100.0")
        self.assertFalse(result.exceeded)

    def test_summary_over_budget(self):
        """예산보다 1원 큰 지출도 초과 상태로 판정하는지 확인한다."""
        self.add(amount=101)
        self.service.set_budget("2026-10", 100)
        self.assertTrue(self.service.summary("2026-10").exceeded)

    def test_summary_empty_month_preserves_budget(self):
        """거래 없는 달도 설정 예산·사용률 0.0%·빈 순위를 반환하는지 확인한다."""
        self.service.set_budget("2026-12", 100)
        result = self.service.summary("2026-12")
        self.assertEqual((result.count, result.balance, result.usage_percent), (0, 0, "0.0"))
        self.assertEqual(result.top_expenses, ())

    def test_summary_missing_budget_and_tie_ranking(self):
        """미설정 예산은 None이며 지출 동률은 카테고리 이름순으로 정렬되는지 확인한다."""
        self.add(category="transport", amount=10)
        self.add(category="food", amount=10)
        result = self.service.summary("2026-10", 1)
        self.assertIsNone(result.budget)
        self.assertIsNone(result.usage_percent)
        self.assertEqual(result.top_expenses, (("food", 10),))

    def test_summary_huge_integer_not_float(self):
        """큰 정수 금액·예산에서도 float 변환 없이 100.0%를 표시하는지 확인한다."""
        self.add(amount=10**320)
        self.service.set_budget("2026-10", 10**320)
        self.assertEqual(self.service.summary("2026-10").usage_percent, "100.0")

    def test_month_boundaries_and_leap_year(self):
        """윤년·평년과 표현 가능한 연도 경계에서 월의 시작·끝 날짜를 비교한다."""
        self.assertEqual(month_filter("2024-02").end, "2024-02-29")
        self.assertEqual(month_filter("2025-02").end, "2025-02-28")
        self.assertEqual(month_filter("9999-12").end, "9999-12-31")
        self.assertEqual(month_filter("0001-01").start, "0001-01-01")

    def test_invalid_summary_top(self):
        """지출 순위 개수 0이 거부되는지 확인한다."""
        with self.assertRaises(ValidationError):
            self.service.summary("2026-10", 0)
