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
        self.assertEqual(validate_date("2026-10-06"), "2026-10-06")

    def test_leap_day(self) -> None:
        self.assertEqual(validate_date("2024-02-29"), "2024-02-29")
        with self.assertRaises(ValidationError):
            validate_date("2025-02-29")

    def test_impossible_dates(self) -> None:
        for value in ("2026-02-30", "2026-13-01", "2026-00-01", "0000-01-01"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_date(value)

    def test_date_shape(self) -> None:
        for value in ("2026-1-01", "2026-10-6", "20261006", "26-10-06", " 2026-10-06 ", "２０２６-１０-０６", ""):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_date(value)

    def test_date_wrong_runtime_type(self) -> None:
        with self.assertRaises(ValidationError):
            validate_date(None)  # type: ignore[arg-type] -- deliberately invalid runtime input

    def test_valid_month(self) -> None:
        self.assertEqual(validate_month("2026-10"), "2026-10")

    def test_invalid_months(self) -> None:
        for value in ("2026-00", "2026-13", "2026-1", "0000-01", "2026-10-01", ""):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_month(value)

    def test_positive_amount(self) -> None:
        self.assertEqual(validate_amount(15000), 15000)

    def test_nonpositive_amount(self) -> None:
        for value in (0, -1, -15000):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_amount(value)

    def test_bool_is_not_an_amount(self) -> None:
        for value in (True, False):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_amount(value)

    def test_amount_wrong_runtime_type(self) -> None:
        for value in (1.0, "100", None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_amount(value)  # type: ignore[arg-type]

    def test_parse_amount(self) -> None:
        self.assertEqual(parse_amount(" 15000 "), 15000)
        self.assertEqual(parse_amount("0005"), 5)

    def test_parse_invalid_amount(self) -> None:
        for value in ("", " ", "0", "-100", "+100", "1.5", "1,000", "100원", "abc", "１２３"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parse_amount(value)

    def test_parse_amount_wrong_runtime_type(self) -> None:
        with self.assertRaises(ValidationError):
            parse_amount(100)  # type: ignore[arg-type]

    def test_transaction_types(self) -> None:
        self.assertEqual(validate_transaction_type("income"), "income")
        self.assertEqual(validate_transaction_type("expense"), "expense")

    def test_invalid_transaction_types(self) -> None:
        for value in ("transfer", "INCOME", "Expense", "income ", ""):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_transaction_type(value)

    def test_category_names(self) -> None:
        self.assertEqual(validate_category_name("food"), "food")
        self.assertEqual(validate_category_name("식비"), "식비")
        self.assertEqual(validate_category_name("생활 용품"), "생활 용품")

    def test_invalid_category_names(self) -> None:
        for value in ("", " ", " food", "food ", "food\nbar", "food\tbar", "food\x1b"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_category_name(value)

    def test_memo_can_be_empty_or_contain_delimiters(self) -> None:
        for value in ("", "점심, 커피\n두 번째 줄"):
            with self.subTest(value=value):
                self.assertEqual(validate_memo(value), value)

    def test_memo_must_be_string(self) -> None:
        with self.assertRaises(ValidationError):
            validate_memo(None)  # type: ignore[arg-type]

    def test_parse_empty_tags(self) -> None:
        self.assertEqual(parse_tags(""), ())
        self.assertEqual(parse_tags(" , , "), ())

    def test_parse_tags_trims_and_deduplicates(self) -> None:
        self.assertEqual(parse_tags(" meal, lunch, meal, , "), ("meal", "lunch"))

    def test_tag_case_is_preserved(self) -> None:
        self.assertEqual(parse_tags("Meal,meal"), ("Meal", "meal"))

    def test_tags_must_be_tuple(self) -> None:
        with self.assertRaises(ValidationError):
            validate_tags(["meal"])  # type: ignore[arg-type]

    def test_tags_cannot_contain_comma_or_duplicates(self) -> None:
        for value in (("meal,lunch",), ("meal", "meal"), (" meal",), ("",)):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_tags(value)

    def test_tag_runtime_types(self) -> None:
        with self.assertRaises(ValidationError):
            validate_tags((123,))  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            parse_tags(None)  # type: ignore[arg-type]

    def test_errors_include_cause_and_hint(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            validate_date("2026-13-40")
        self.assertTrue(caught.exception.message)
        self.assertTrue(caught.exception.hint)
        self.assertEqual(str(caught.exception), caught.exception.message)


if __name__ == "__main__":
    unittest.main()
