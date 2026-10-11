import unittest
from dataclasses import FrozenInstanceError, replace

from budget_app.errors import AppError, ValidationError
from budget_app.models import MonthlyBudget, Transaction


class ModelTests(unittest.TestCase):
    def make_transaction(self) -> Transaction:
        """정상 필드와 선택 필드 기본값을 가진 고정 거래를 만들어 각 모델 테스트에 제공한다."""
        return Transaction(
            id="TX-TEST-001",
            type="expense",
            date="2026-10-06",
            amount=15000,
            category="food",
        )

    def test_transaction_fields_and_defaults(self) -> None:
        """거래를 생성해 금액과 생략한 메모·태그의 기본값을 비교한다."""
        transaction = self.make_transaction()
        self.assertEqual(transaction.amount, 15000)
        self.assertEqual(transaction.memo, "")
        self.assertEqual(transaction.tags, ())

    def test_transaction_equality(self) -> None:
        """같은 필드로 생성한 거래 두 개가 dataclass 값 비교에서 같은지 확인한다."""
        self.assertEqual(self.make_transaction(), self.make_transaction())

    def test_transaction_is_frozen(self) -> None:
        """생성된 거래의 금액을 직접 바꾸면 FrozenInstanceError가 발생하는지 확인한다."""
        transaction = self.make_transaction()
        with self.assertRaises(FrozenInstanceError):
            transaction.amount = 0  # type: ignore[misc]

    def test_replace_creates_validated_copy(self) -> None:
        """replace로 금액만 바꾼 사본을 만들고 원본·ID·객체 독립성을 비교한다."""
        original = self.make_transaction()
        revised = replace(original, amount=20000)
        self.assertEqual(original.amount, 15000)
        self.assertEqual(revised.amount, 20000)
        self.assertEqual(revised.id, original.id)
        self.assertIsNot(revised, original)

    def test_replace_rejects_invalid_amount_and_keeps_original(self) -> None:
        """0원 수정이 거부되는지와 실패 후 원래 금액이 유지되는지를 함께 확인한다."""
        original = self.make_transaction()
        with self.assertRaises(ValidationError):
            replace(original, amount=0)
        self.assertEqual(original.amount, 15000)

    def test_direct_creation_validates_amount(self) -> None:
        """음수 금액으로 모델을 직접 생성해도 입력 검증을 우회할 수 없는지 확인한다."""
        with self.assertRaises(ValidationError):
            Transaction(id="TX-TEST-002", type="expense", date="2026-10-06", amount=-1, category="food")

    def test_model_validates_each_field(self) -> None:
        """각 필드에 잘못된 값을 하나씩 넣고 모든 생성 경로에서 검증 오류가 나는지 확인한다."""
        invalid_fields = (
            {"id": ""}, {"type": "transfer"}, {"date": "2026-02-30"},
            {"amount": True}, {"category": ""}, {"memo": None}, {"tags": ["meal"]},
        )
        for changes in invalid_fields:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                replace(self.make_transaction(), **changes)

    def test_category_registration_is_not_a_model_responsibility(self) -> None:
        """미등록 이름도 형식이 맞으면 모델은 생성됨을 확인하여 등록 검사의 책임을 구분한다."""
        transaction = replace(self.make_transaction(), category="not-yet-registered")
        self.assertEqual(transaction.category, "not-yet-registered")

    def test_model_alone_does_not_enforce_repository_id_uniqueness(self) -> None:
        """모델 두 개에 같은 ID를 사용할 수 있음을 확인해 저장소 수준 중복 검사와 구분한다."""
        self.assertEqual(self.make_transaction().id, self.make_transaction().id)

    def test_valid_budget(self) -> None:
        """정상 월과 양수 금액의 예산 모델을 만들고 필드 값을 확인한다."""
        budget = MonthlyBudget(month="2026-10", amount=500000)
        self.assertEqual(budget.month, "2026-10")
        self.assertEqual(budget.amount, 500000)

    def test_invalid_budget_month(self) -> None:
        """존재하지 않는 월의 예산 생성이 검증 오류로 거부되는지 확인한다."""
        with self.assertRaises(ValidationError):
            MonthlyBudget(month="2026-13", amount=500000)

    def test_invalid_budget_amount(self) -> None:
        """0·음수·bool 예산을 각각 생성해 모두 거부되는지 확인한다."""
        for amount in (0, -1, True):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                MonthlyBudget(month="2026-10", amount=amount)

    def test_validation_error_is_app_error(self) -> None:
        """ValidationError가 공통 AppError 계층에 포함되어 CLI에서 함께 처리 가능한지 확인한다."""
        self.assertIsInstance(ValidationError("원인", "해결 힌트"), AppError)


if __name__ == "__main__":
    unittest.main()
