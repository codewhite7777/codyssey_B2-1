"""저장소 계층: JSONL 파일 3개를 읽고 쓴다. 가계부 규칙은 모른다."""

import json
import os
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from .errors import AppError
from .models import Transaction

TRANSACTIONS_FILE = "transactions.jsonl"
CATEGORIES_FILE = "categories.jsonl"
BUDGETS_FILE = "budgets.jsonl"


def ensure_data_dir(data_dir: Path) -> list[str]:
    """저장 폴더와 파일 3개가 없으면 빈 파일로 만든다. 새로 만든 파일 이름을 돌려준다."""
    data_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for name in (TRANSACTIONS_FILE, CATEGORIES_FILE, BUDGETS_FILE):
        path = data_dir / name
        if not path.exists():
            path.touch()
            created.append(name)
    return created


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """JSONL 파일을 한 줄씩 읽어 딕셔너리를 하나씩 내보낸다(yield)."""
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                raise AppError(
                    f"{path.name} 의 {line_no}번째 줄이 손상되었습니다.",
                    "파일을 열어 그 줄을 고치거나 지운 뒤 다시 실행하세요.",
                ) from None


def to_line(record: dict[str, Any]) -> str:
    """딕셔너리를 JSONL 한 줄로 바꾼다. (한글은 그대로 저장)"""
    return json.dumps(record, ensure_ascii=False) + "\n"


def atomic_write(path: Path, records: Iterable[dict[str, Any]]) -> None:
    """임시 파일에 전부 쓴 뒤 os.replace로 원본과 한 번에 바꿔 끼운다."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")   # 같은 폴더에 만든다
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            for record in records:
                out.write(to_line(record))
        os.replace(tmp, path)          # 이 순간에만 원본이 바뀐다
    finally:
        if os.path.exists(tmp):        # 중간에 실패했다면 임시 파일만 지운다
            os.remove(tmp)


class TransactionRepository:
    """transactions.jsonl 담당: 읽기(스트리밍) · 추가 · 안전한 재작성."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / TRANSACTIONS_FILE

    def iter_all(self) -> Iterator[Transaction]:
        """거래를 파일 순서대로 한 건씩 내보낸다. 전체를 메모리에 올리지 않는다."""
        for record in read_jsonl(self.path):
            try:
                yield Transaction.from_dict(record)
            except TypeError:
                raise AppError(
                    f"{self.path.name} 에 형식이 맞지 않는 거래가 있습니다: {record}",
                    "필드 이름(id, type, date, amount, category, memo, tags)을 확인하세요.",
                ) from None

    def find(self, tx_id: str) -> Transaction | None:
        """id가 같은 거래를 찾는다. 없으면 None."""
        for tx in self.iter_all():
            if tx.id == tx_id:
                return tx
        return None

    def next_number(self) -> int:
        """다음 id 번호 = 지금까지 가장 큰 번호 + 1."""
        last = 0
        for tx in self.iter_all():
            last = max(last, int(tx.id.split("-")[1]))
        return last + 1

    def append(self, transactions: list[Transaction]) -> None:
        """파일 맨 끝에 거래를 추가한다. 기존 줄은 건드리지 않는다."""
        with self.path.open("a", encoding="utf-8") as f:
            for tx in transactions:
                f.write(to_line(tx.to_dict()))

    def rewrite(self, tx_id: str, new: Transaction | None) -> bool:
        """tx_id 거래를 new로 바꾸거나(update), new가 None이면 뺀다(delete)."""
        if self.find(tx_id) is None:
            return False                       # 없는 id: 파일을 건드리지 않는다

        def updated() -> Iterator[dict[str, Any]]:
            for tx in self.iter_all():         # 원본은 한 줄씩 읽기만 한다
                if tx.id != tx_id:
                    yield tx.to_dict()
                elif new is not None:
                    yield new.to_dict()        # update: 바뀐 거래로 교체
                # delete: 아무것도 내보내지 않으면 그 줄이 빠진다

        atomic_write(self.path, updated())
        return True


class CategoryStore:
    """categories.jsonl 담당: 카테고리 이름 목록."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / CATEGORIES_FILE

    def names(self) -> list[str]:
        return [record["name"] for record in read_jsonl(self.path)]

    def save(self, names: list[str]) -> None:
        atomic_write(self.path, ({"name": name} for name in sorted(names)))


class BudgetStore:
    """budgets.jsonl 담당: 월별 예산 (한 달에 1개)."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / BUDGETS_FILE

    def all(self) -> dict[str, int]:
        return {record["month"]: record["amount"] for record in read_jsonl(self.path)}

    def get(self, month: str) -> int | None:
        return self.all().get(month)

    def set(self, month: str, amount: int) -> None:
        budgets = self.all()
        budgets[month] = amount                # 같은 달이면 덮어쓴다
        atomic_write(self.path, ({"month": m, "amount": a} for m, a in sorted(budgets.items())))
