import unittest

from budget_app.errors import ValidationError
from budget_app.validators import (
    parse_amount,
    parse_tags,
    validate_amount,
    validate_category_name,
    validate_date,
    validate_memo,
    validate_month,
    validate_tags,
    validate_transaction_type,
)


class ValidatorTests(unittest.TestCase):
    def test_valid_date(self) -> None:
        """정상 날짜를 검증하면 같은 YYYY-MM-DD 문자열이 반환되는지 확인한다."""
        self.assertEqual(validate_date("2026-10-06"), "2026-10-06")

    def test_leap_day(self) -> None:
        """윤년의 2월 29일은 허용하고 평년의 같은 날짜는 거부하는지 확인한다."""
        self.assertEqual(validate_date("2024-02-29"), "2024-02-29")
        with self.assertRaises(ValidationError):
            validate_date("2025-02-29")

    def test_impossible_dates(self) -> None:
        """잘못된 월·일과 0년 등 실제로 존재하지 않는 날짜를 모두 거부하는지 확인한다."""
        for value in ("2026-02-30", "2026-13-01", "2026-00-01", "0000-01-01"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_date(value)

    def test_date_shape(self) -> None:
        """0 채움 누락·공백·전각 숫자 등 요구한 날짜 모양이 아닌 입력을 거부하는지 확인한다."""
        for value in ("2026-1-01", "2026-10-6", "20261006", "26-10-06", " 2026-10-06 ", "２０２６-１０-０６", ""):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_date(value)

    def test_date_wrong_runtime_type(self) -> None:
        """문자열 대신 None을 전달해 타입 힌트와 별개로 실제 값도 검사하는지 확인한다."""
        with self.assertRaises(ValidationError):
            validate_date(None)  # type: ignore[arg-type] -- deliberately invalid runtime input

    def test_valid_month(self) -> None:
        """정상 YYYY-MM을 검사하면 같은 문자열이 반환되는지 확인한다."""
        self.assertEqual(validate_month("2026-10"), "2026-10")

    def test_invalid_months(self) -> None:
        """잘못된 월 범위·길이·연도·추가 날짜를 넣어 모두 거부되는지 확인한다."""
        for value in ("2026-00", "2026-13", "2026-1", "0000-01", "2026-10-01", ""):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_month(value)

    def test_positive_amount(self) -> None:
        """양수 정수 금액을 검사하면 같은 숫자가 반환되는지 확인한다."""
        self.assertEqual(validate_amount(15000), 15000)

    def test_nonpositive_amount(self) -> None:
        """0과 음수 금액을 순회해 모두 검증 오류가 발생하는지 확인한다."""
        for value in (0, -1, -15000):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_amount(value)

    def test_bool_is_not_an_amount(self) -> None:
        """int의 하위 타입인 bool도 금액으로는 거부되는지 True와 False로 확인한다."""
        for value in (True, False):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_amount(value)

    def test_amount_wrong_runtime_type(self) -> None:
        """소수·문자열·None 금액을 거부하여 정수 계약을 실제로 검사하는지 확인한다."""
        for value in (1.0, "100", None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_amount(value)  # type: ignore[arg-type]

    def test_parse_amount(self) -> None:
        """공백과 앞자리 0이 있는 금액 문자열을 올바른 정수로 바꾸는지 확인한다."""
        self.assertEqual(parse_amount(" 15000 "), 15000)
        self.assertEqual(parse_amount("0005"), 5)

    def test_parse_invalid_amount(self) -> None:
        """0·부호·소수·통화 기호·쉼표·전각 숫자 등 잘못된 금액 입력을 거부하는지 확인한다."""
        for value in ("", " ", "0", "-100", "+100", "1.5", "1,000", "100원", "abc", "１２３"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parse_amount(value)

    def test_parse_amount_wrong_runtime_type(self) -> None:
        """문자열 파서에 정수를 직접 넣어도 명확한 검증 오류가 나는지 확인한다."""
        with self.assertRaises(ValidationError):
            parse_amount(100)  # type: ignore[arg-type]

    def test_transaction_types(self) -> None:
        """income과 expense 두 값이 허용되고 그대로 반환되는지 확인한다."""
        self.assertEqual(validate_transaction_type("income"), "income")
        self.assertEqual(validate_transaction_type("expense"), "expense")

    def test_invalid_transaction_types(self) -> None:
        """다른 타입 이름·대소문자·공백을 넣어 허용 목록 외 값을 거부하는지 확인한다."""
        for value in ("transfer", "INCOME", "Expense", "income ", ""):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_transaction_type(value)

    def test_category_names(self) -> None:
        """영문·한글·내부 공백이 있는 정상 카테고리 이름을 허용하는지 확인한다."""
        self.assertEqual(validate_category_name("food"), "food")
        self.assertEqual(validate_category_name("식비"), "식비")
        self.assertEqual(validate_category_name("생활 용품"), "생활 용품")

    def test_invalid_category_names(self) -> None:
        """빈 이름·앞뒤 공백·개행·제어 문자가 있는 이름을 거부하는지 확인한다."""
        for value in ("", " ", " food", "food ", "food\nbar", "food\tbar", "food\x1b"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_category_name(value)

    def test_memo_can_be_empty_or_contain_delimiters(self) -> None:
        """빈 메모와 쉼표·개행이 포함된 메모가 변형 없이 허용되는지 확인한다."""
        for value in ("", "점심, 커피\n두 번째 줄"):
            with self.subTest(value=value):
                self.assertEqual(validate_memo(value), value)

    def test_memo_must_be_string(self) -> None:
        """메모가 문자열이 아니면 검증 오류가 발생하는지 확인한다."""
        with self.assertRaises(ValidationError):
            validate_memo(None)  # type: ignore[arg-type]

    def test_parse_empty_tags(self) -> None:
        """빈 입력과 빈 쉼표 항목만 있는 입력을 모두 빈 태그 튜플로 바꾸는지 확인한다."""
        self.assertEqual(parse_tags(""), ())
        self.assertEqual(parse_tags(" , , "), ())

    def test_parse_tags_trims_and_deduplicates(self) -> None:
        """공백·빈 항목·중복 태그를 정리하되 최초 입력 순서는 유지하는지 비교한다."""
        self.assertEqual(parse_tags(" meal, lunch, meal, , "), ("meal", "lunch"))

    def test_tag_case_is_preserved(self) -> None:
        """Meal과 meal을 서로 다른 태그로 유지하는지 확인한다."""
        self.assertEqual(parse_tags("Meal,meal"), ("Meal", "meal"))

    def test_tags_must_be_tuple(self) -> None:
        """모델용 태그 검증에 리스트를 전달하면 거부되는지 확인한다."""
        with self.assertRaises(ValidationError):
            validate_tags(["meal"])  # type: ignore[arg-type]

    def test_tags_cannot_contain_comma_or_duplicates(self) -> None:
        """개별 태그의 쉼표·중복·앞뒤 공백·빈 값을 각각 거부하는지 확인한다."""
        for value in (("meal,lunch",), ("meal", "meal"), (" meal",), ("",)):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_tags(value)

    def test_tag_runtime_types(self) -> None:
        """태그 원소와 파서 입력의 잘못된 자료형을 명확한 오류로 거부하는지 확인한다."""
        with self.assertRaises(ValidationError):
            validate_tags((123,))  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            parse_tags(None)  # type: ignore[arg-type]

    def test_errors_include_cause_and_hint(self) -> None:
        """잘못된 날짜에서 발생한 오류에 원인·힌트와 Exception 메시지가 있는지 비교한다."""
        with self.assertRaises(ValidationError) as caught:
            validate_date("2026-13-40")
        self.assertTrue(caught.exception.message)
        self.assertTrue(caught.exception.hint)
        self.assertEqual(str(caught.exception), caught.exception.message)


if __name__ == "__main__":
    unittest.main()
