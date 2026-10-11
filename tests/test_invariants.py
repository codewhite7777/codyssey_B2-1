"""재현 가능한 무작위 입력을 단순 메모리 모델과 비교한다. 외부 테스트 라이브러리 불필요."""

import random
from dataclasses import replace

from budget_app.models import SearchFilter, transaction_key
from tests.common import ServiceCase


class StateMachineTests(ServiceCase):
    def scenario(self, seed):
        """고정 시드로 150회 추가·수정·삭제를 수행하며 매번 메모리 기준 모델과 저장·검색·합계를 비교한다."""
        randomizer = random.Random(seed)
        expected = {}
        for step in range(150):
            operation = randomizer.choice(("add", "add", "update", "delete")) if expected else "add"
            if operation == "add":
                transaction = self.add(date=f"2026-{randomizer.choice((9, 10, 11)):02}-{randomizer.randint(1, 28):02}",
                                       amount=randomizer.randint(1, 100000), category=randomizer.choice(("food", "transport")),
                                       memo=f"seed {seed} step {step}")
                self.assertNotIn(transaction.id, expected)
                expected[transaction.id] = transaction
            elif operation == "update":
                identifier = randomizer.choice(tuple(expected))
                changes = dict(date=f"2026-10-{randomizer.randint(1, 28):02}", amount=randomizer.randint(1, 100000))
                updated = self.service.update(identifier, **changes)
                expected[identifier] = replace(expected[identifier], **changes)
                self.assertEqual(updated, expected[identifier])
            else:
                identifier = randomizer.choice(tuple(expected))
                self.service.delete(identifier)
                del expected[identifier]
            with self.subTest(seed=seed, step=step, operation=operation):
                actual = list(self.service.search())
                self.assertEqual(actual, sorted(expected.values(), key=transaction_key, reverse=True))
                criteria = SearchFilter(start="2026-10-01", end="2026-10-31", category="food")
                self.assertEqual(list(self.service.search(criteria)), [value for value in actual if criteria.matches(value)])
                summary = self.service.summary("2026-10")
                self.assertEqual(summary.expense, sum(value.amount for value in expected.values() if value.date.startswith("2026-10")))

    def test_seed_42(self):
        """시드 42의 150단계 거래 변경 결과를 기준 모델과 대조한다."""
        self.scenario(42)

    def test_seed_20261009(self):
        """시드 20261009의 150단계 거래 변경 결과를 기준 모델과 대조한다."""
        self.scenario(20261009)

    def test_seed_98765(self):
        """시드 98765의 150단계 거래 변경 결과를 기준 모델과 대조한다."""
        self.scenario(98765)
