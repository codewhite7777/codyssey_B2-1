"""설명 주석과 단순화한 로직의 회귀 검사. 과제의 추가 채점 기준은 아니다."""

import ast
import inspect
import io
import unittest
from contextlib import redirect_stdout
from itertools import product
from pathlib import Path

from budget_app.cli import build_parser, print_transactions
from budget_app.csv_io import export_rows
from budget_app.models import MonthSummary, SearchFilter, Transaction
from budget_app.validators import parse_tags

ROOT = Path(__file__).resolve().parents[1]


class ReadabilityRegressionTests(unittest.TestCase):
    """문서의 존재와 변경 전후 유지해야 하는 입력·출력 계약을 검사한다."""

    def test_every_function_has_a_docstring(self):
        """앱·테스트·도구의 모든 def를 AST로 찾아 내부 함수까지 설명문이 있는지 확인한다."""
        missing = []
        for directory in ("budget_app", "tests", "tools"):
            for path in (ROOT / directory).glob("*.py"):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not ast.get_docstring(node):
                            missing.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}")
        self.assertEqual(missing, [])

    def test_update_parser_omitted_fields_are_absent(self):
        """금액만 수정할 때 생략한 필드를 Namespace에 만들지 않는지 확인한다."""
        parsed = vars(build_parser().parse_args(["update", "--id", "id", "--amount", "1"]))
        self.assertEqual(parsed["amount"], 1)
        for field in ("date", "type", "category", "memo", "tags"):
            self.assertNotIn(field, parsed)

    def test_update_parser_empty_values_are_preserved(self):
        """빈 메모·태그 옵션은 생략과 구분되어 실제 빈 문자열로 전달되는지 확인한다."""
        parsed = build_parser().parse_args(["update", "--id", "id", "--memo", "", "--tags", ""])
        self.assertEqual((parsed.memo, parsed.tags), ("", ""))

    def test_update_parser_all_fields_keep_their_names(self):
        """명시적으로 등록한 여섯 수정 옵션이 올바른 필드와 자료형으로 해석되는지 비교한다."""
        parsed = build_parser().parse_args([
            "update", "--id", "id", "--date", "2026-10-12", "--type", "income",
            "--category", "salary", "--amount", "3500", "--memo", "용돈", "--tags", "a,b",
        ])
        self.assertEqual(
            (parsed.date, parsed.type, parsed.category, parsed.amount, parsed.memo, parsed.tags),
            ("2026-10-12", "income", "salary", 3500, "용돈", "a,b"),
        )

    def test_search_guards_match_reference_for_combined_filters(self):
        """540개 유효 검색 조건 조합을 독립적인 AND 기준식과 비교해 조기 반환 변경을 검증한다."""
        transaction = Transaction(
            id="id", type="expense", date="2026-10-12", amount=100,
            category="food", memo="Lunch 식사", tags=("meal", "work"),
        )
        for start, end, category, kind, query, tag in product(
            (None, "2026-10-01", "2026-10-13"), (None, "2026-10-12"),
            (None, "food", "salary"), (None, "expense", "income"),
            (None, "LUNCH", "missing"), (None, "meal", "mea", "Meal"),
        ):
            if start is not None and end is not None and start > end:
                continue
            filters = SearchFilter(start, end, category, kind, query, tag)
            expected = all((
                start is None or transaction.date >= start,
                end is None or transaction.date <= end,
                category is None or transaction.category == category,
                kind is None or transaction.type == kind,
                query is None or query.casefold() in transaction.memo.casefold(),
                tag is None or tag in transaction.tags,
            ))
            with self.subTest(filters=filters):
                self.assertEqual(filters.matches(transaction), expected)

    def test_tag_loop_preserves_first_seen_order(self):
        """한글·중복·대소문자·빈 조각을 섞어 태그 정리 순서가 유지되는지 확인한다."""
        self.assertEqual(parse_tags(" 식비,Meal,, 식비,meal, Meal ,교통 "), ("식비", "Meal", "meal", "교통"))

    def test_percentage_rounding_does_not_decide_exceeded(self):
        """사용률이 반올림되어 100.0%여도 실제 지출이 더 크면 초과로 표시되는지 확인한다."""
        summary = MonthSummary("2026-10", 1, 0, 10001, (), 10000)
        self.assertEqual(summary.usage_percent, "100.0")
        self.assertTrue(summary.exceeded)

    def test_percentage_half_up(self):
        """사용률 0.05%를 0.1%로 반올림하는 기존 정수 계산 규칙을 확인한다."""
        summary = MonthSummary("2026-10", 1, 0, 1, (), 2000)
        self.assertEqual(summary.usage_percent, "0.1")

    def test_closing_contract_uses_generator_annotation(self):
        """close를 호출하는 화면·CSV 함수가 일반 Iterator보다 구체적인 Generator 계약인지 확인한다."""
        from collections.abc import Generator
        from typing import get_origin, get_type_hints

        for function in (print_transactions, export_rows):
            annotation = get_type_hints(function)["transactions"]
            self.assertIs(get_origin(annotation), Generator)

    def test_docstrings_do_not_change_empty_output(self):
        """문서 추가 후에도 빈 결과 제너레이터를 소비해 데이터 없음 안내를 출력하는지 확인한다."""
        transactions = (value for value in ())
        self.assertTrue(inspect.isgenerator(transactions))
        stream = io.StringIO()
        with redirect_stdout(stream):
            print_transactions(transactions)
        self.assertIn("데이터 없음", stream.getvalue())
