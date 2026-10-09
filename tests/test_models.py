import unittest
from dataclasses import FrozenInstanceError, replace

from budget_app.errors import AppError, ValidationError
from budget_app.models import MonthlyBudget, Transaction


class ModelTests(unittest.TestCase):
    def make_transaction(self) -> Transaction:
        return Transaction(
            id="TX-TEST-001",
            type="expense",
            date="2026-10-06",
            amount=15000,
            category="food",
        )

    def test_transaction_fields_and_defaults(self) -> None:
        transaction = self.make_transaction()
        self.assertEqual(transaction.amount, 15000)
        self.assertEqual(transaction.memo, "")
        self.assertEqual(transaction.tags, ())

    def test_transaction_equality(self) -> None:
        self.assertEqual(self.make_transaction(), self.make_transaction())

    def test_transaction_is_frozen(self) -> None:
        transaction = self.make_transaction()
        with self.assertRaises(FrozenInstanceError):
            transaction.amount = 0  # type: ignore[misc]

    def test_replace_creates_validated_copy(self) -> None:
        original = self.make_transaction()
        revised = replace(original, amount=20000)
        self.assertEqual(original.amount, 15000)
        self.assertEqual(revised.amount, 20000)
        self.assertEqual(revised.id, original.id)
        self.assertIsNot(revised, original)

    def test_replace_rejects_invalid_amount_and_keeps_original(self) -> None:
        original = self.make_transaction()
        with self.assertRaises(ValidationError):
            replace(original, amount=0)
        self.assertEqual(original.amount, 15000)

    def test_direct_creation_validates_amount(self) -> None:
        with self.assertRaises(ValidationError):
            Transaction(id="TX-TEST-002", type="expense", date="2026-10-06", amount=-1, category="food")

    def test_model_validates_each_field(self) -> None:
        invalid_fields = (
            {"id": ""}, {"type": "transfer"}, {"date": "2026-02-30"},
            {"amount": True}, {"category": ""}, {"memo": None}, {"tags": ["meal"]},
        )
        for changes in invalid_fields:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                replace(self.make_transaction(), **changes)

    def test_category_registration_is_not_a_model_responsibility(self) -> None:
        transaction = replace(self.make_transaction(), category="not-yet-registered")
        self.assertEqual(transaction.category, "not-yet-registered")

    def test_model_alone_does_not_enforce_repository_id_uniqueness(self) -> None:
        self.assertEqual(self.make_transaction().id, self.make_transaction().id)

    def test_valid_budget(self) -> None:
        budget = MonthlyBudget(month="2026-10", amount=500000)
        self.assertEqual(budget.month, "2026-10")
        self.assertEqual(budget.amount, 500000)

    def test_invalid_budget_month(self) -> None:
        with self.assertRaises(ValidationError):
            MonthlyBudget(month="2026-13", amount=500000)

    def test_invalid_budget_amount(self) -> None:
        for amount in (0, -1, True):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                MonthlyBudget(month="2026-10", amount=amount)

    def test_validation_error_is_app_error(self) -> None:
        self.assertIsInstance(ValidationError("원인", "해결 힌트"), AppError)


if __name__ == "__main__":
    unittest.main()
