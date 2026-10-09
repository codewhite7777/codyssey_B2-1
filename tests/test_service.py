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
        added = self.add()
        self.assertTrue(added.id.startswith("TX-"))
        self.assertEqual(list(BudgetService(self.data).list_transactions()), [added])

    def test_unique_ids(self):
        added = [self.add() for _ in range(15)]
        self.assertEqual(len({t.id for t in added}), 15)

    def test_add_requires_registered_category(self):
        before = self.snapshot()
        with self.assertRaises(ValidationError):
            self.add(category="unknown")
        self.assertEqual(self.snapshot(), before)

    def test_add_invalid_values_do_not_change_files(self):
        before = self.snapshot()
        for changes in (dict(date="2026-02-30"), dict(amount=0), dict(amount=-1),
                        dict(amount=True), dict(type="payment"), dict(tags=["meal"])):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.add(**changes)
            self.assertEqual(self.snapshot(), before)

    def test_list_orders_by_date_and_id(self):
        values = [self.add(date=value) for value in ("2026-10-01", "2025-01-01", "2026-12-31", "2026-10-01")]
        self.assertEqual(list(self.service.list_transactions()), sorted(values, key=transaction_key, reverse=True))

    def test_list_default_and_explicit_limit(self):
        for day in range(1, 26):
            self.add(date=f"2026-10-{day:02}")
        self.assertEqual(len(list(self.service.list_transactions())), 20)
        self.assertEqual(len(list(self.service.list_transactions(3))), 3)

    def test_invalid_limit(self):
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                list(self.service.list_transactions(limit))

    def test_update_preserves_id_and_other_fields(self):
        transaction = self.add()
        updated = self.service.update(transaction.id, amount=1234)
        self.assertEqual(updated.id, transaction.id)
        self.assertEqual(updated.memo, transaction.memo)
        self.assertEqual(updated.amount, 1234)
        self.assertEqual(list(self.service.list_transactions()), [updated])

    def test_update_date_repositions_in_sorted_file(self):
        old = self.add(date="2026-01-01")
        middle = self.add(date="2026-06-01")
        newer = self.service.update(old.id, date="2026-12-01")
        self.assertEqual(list(self.service.list_transactions()), [newer, middle])
        oldest = self.service.update(newer.id, date="2025-12-01")
        self.assertEqual(list(self.service.list_transactions()), [middle, oldest])

    def test_update_all_mutable_fields_and_clear_optional(self):
        original = self.add()
        updated = self.service.update(original.id, date="2025-01-01", type="income", category="salary",
                                      amount=99, memo="", tags=())
        self.assertEqual((updated.type, updated.category, updated.memo, updated.tags), ("income", "salary", "", ()))

    def test_update_missing_id(self):
        before = self.snapshot()
        with self.assertRaises(NotFoundError):
            self.service.update("missing", amount=10)
        self.assertEqual(before, self.snapshot())

    def test_update_rejects_empty_unknown_changes(self):
        original = self.add()
        for changes in ({}, {"id": "overwrite"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.service.update(original.id, **changes)

    def test_update_invalid_category_or_value_preserves_original(self):
        original = self.add()
        before = self.snapshot()
        for changes in ({"category": "unknown"}, {"amount": 0}, {"date": "invalid"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.service.update(original.id, **changes)
            self.assertEqual(before, self.snapshot())

    def test_delete_existing(self):
        first = self.add(date="2026-10-01")
        second = self.add(date="2026-10-02")
        self.service.delete(first.id)
        self.assertEqual(list(self.service.list_transactions()), [second])

    def test_delete_last_transaction(self):
        transaction = self.add()
        self.service.delete(transaction.id)
        self.assertEqual((self.data / "transactions.jsonl").read_bytes(), b"")
        self.assertEqual(list(self.service.list_transactions()), [])

    def test_delete_missing_id_no_changes(self):
        before = self.snapshot()
        with self.assertRaises(NotFoundError):
            self.service.delete("missing")
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_id_with_different_dates_blocks_write(self):
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
        class Fixed:
            hex = "same"
        with patch("budget_app.service.uuid.uuid4", return_value=Fixed()):
            self.add()
            before = self.snapshot()
            with self.assertRaises(ConflictError):
                self.add()
        self.assertEqual(self.snapshot(), before)

    def test_generators_are_lazy(self):
        self.assertTrue(inspect.isgenerator(self.service.list_transactions()))
        self.assertTrue(inspect.isgenerator(self.service.search()))
        with patch.object(self.service.store, "session", side_effect=AssertionError("not yet")):
            generator = self.service.search()
            generator.close()

    def test_limit_does_not_read_an_extra_record(self):
        first = self.add()
        def source(categories):
            yield first
            raise AssertionError("limit 이후 거래를 읽었습니다")
        with patch.object(self.service, "_checked_transactions", side_effect=source):
            self.assertEqual(list(self.service.list_transactions(1)), [first])

    def test_early_close_releases_lock(self):
        self.add()
        generator = self.service.search()
        next(generator)
        self.assertTrue((self.data / LOCK_NAME).exists())
        generator.close()
        self.assertFalse((self.data / LOCK_NAME).exists())


class SearchTests(ServiceCase):
    def setUp(self):
        super().setUp()
        self.first = self.add(date="2026-10-01", memo="Lunch MEAL", tags=("meal", "work"))
        self.second = self.add(date="2026-10-02", category="transport", memo="버스", tags=("commute",))
        self.third = self.add(date="2026-11-01", type="income", category="salary", memo="급여", tags=())

    def results(self, **fields):
        return list(self.service.search(SearchFilter(**fields)))

    def test_search_inclusive_range(self):
        self.assertEqual(self.results(start="2026-10-01", end="2026-10-02"), [self.second, self.first])

    def test_search_open_range(self):
        self.assertEqual(self.results(start="2026-11-01"), [self.third])
        self.assertEqual(self.results(end="2026-10-01"), [self.first])

    def test_search_category(self):
        self.assertEqual(self.results(category="transport"), [self.second])

    def test_search_type(self):
        self.assertEqual(self.results(type="income"), [self.third])

    def test_search_casefold_memo(self):
        self.assertEqual(self.results(query="lunch meal"), [self.first])

    def test_search_exact_tag(self):
        self.assertEqual(self.results(tag="meal"), [self.first])
        self.assertEqual(self.results(tag="mea"), [])
        self.assertEqual(self.results(tag="Meal"), [])

    def test_search_conditions_are_and(self):
        self.assertEqual(self.results(category="food", type="expense", query="lunch", tag="work",
                                      start="2026-10-01", end="2026-10-01"), [self.first])
        self.assertEqual(self.results(category="food", type="income"), [])

    def test_unknown_category_is_error(self):
        with self.assertRaises(ValidationError):
            self.results(category="unknown")

    def test_bad_filters(self):
        for fields in ({"start": "2026-10-02", "end": "2026-10-01"}, {"start": "2026-13-01"},
                       {"type": "other"}, {"tag": "a,b"}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                SearchFilter(**fields)


class CategoryAndBudgetTests(ServiceCase):
    def test_category_add_and_persistence(self):
        self.service.add_category("카페")
        self.assertIn("카페", BudgetService(self.data).list_categories())

    def test_category_duplicate_error(self):
        with self.assertRaises(ConflictError):
            self.service.add_category("food")

    def test_category_remove_unused(self):
        self.service.remove_category("rent")
        self.assertNotIn("rent", self.service.list_categories())

    def test_category_remove_used_is_blocked(self):
        self.add()
        before = self.snapshot()
        with self.assertRaises(ConflictError):
            self.service.remove_category("food")
        self.assertEqual(self.snapshot(), before)

    def test_category_remove_missing(self):
        with self.assertRaises(ValidationError):
            self.service.remove_category("missing")

    def test_category_after_delete_is_removable(self):
        transaction = self.add()
        self.service.delete(transaction.id)
        self.service.remove_category("food")
        self.assertNotIn("food", self.service.list_categories())

    def test_budget_set_get_replace_persistence(self):
        self.service.set_budget("2026-10", 500000)
        self.service.set_budget("2026-11", 700000)
        self.service.set_budget("2026-10", 600000)
        reloaded = BudgetService(self.data)
        self.assertEqual(reloaded.get_budget("2026-10").amount, 600000)
        self.assertEqual(reloaded.get_budget("2026-11").amount, 700000)
        self.assertIsNone(reloaded.get_budget("2026-12"))

    def test_budget_invalid(self):
        for month, amount in (("2026-13", 1), ("2026-10", 0), ("2026-10", -1), ("2026-10", True)):
            with self.subTest(month=month, amount=amount), self.assertRaises(ValidationError):
                self.service.set_budget(month, amount)

    def test_summary_exact_totals_and_ranking(self):
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
        self.add(amount=100)
        self.service.set_budget("2026-10", 100)
        result = self.service.summary("2026-10")
        self.assertEqual(result.usage_percent, "100.0")
        self.assertFalse(result.exceeded)

    def test_summary_over_budget(self):
        self.add(amount=101)
        self.service.set_budget("2026-10", 100)
        self.assertTrue(self.service.summary("2026-10").exceeded)

    def test_summary_empty_month_preserves_budget(self):
        self.service.set_budget("2026-12", 100)
        result = self.service.summary("2026-12")
        self.assertEqual((result.count, result.balance, result.usage_percent), (0, 0, "0.0"))
        self.assertEqual(result.top_expenses, ())

    def test_summary_missing_budget_and_tie_ranking(self):
        self.add(category="transport", amount=10)
        self.add(category="food", amount=10)
        result = self.service.summary("2026-10", 1)
        self.assertIsNone(result.budget)
        self.assertIsNone(result.usage_percent)
        self.assertEqual(result.top_expenses, (("food", 10),))

    def test_summary_huge_integer_not_float(self):
        self.add(amount=10**320)
        self.service.set_budget("2026-10", 10**320)
        self.assertEqual(self.service.summary("2026-10").usage_percent, "100.0")

    def test_month_boundaries_and_leap_year(self):
        self.assertEqual(month_filter("2024-02").end, "2024-02-29")
        self.assertEqual(month_filter("2025-02").end, "2025-02-28")
        self.assertEqual(month_filter("9999-12").end, "9999-12-31")
        self.assertEqual(month_filter("0001-01").start, "0001-01-01")

    def test_invalid_summary_top(self):
        with self.assertRaises(ValidationError):
            self.service.summary("2026-10", 0)
