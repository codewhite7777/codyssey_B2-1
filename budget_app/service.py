"""서비스 계층: 입력 검증과 가계부 규칙. 화면 출력도, 파일 형식도 모른다."""

import csv
import heapq
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import AppError
from .models import Transaction
from .storage import BudgetStore, CategoryStore, TransactionRepository

DEFAULT_CATEGORIES = ["food", "transport", "rent", "salary", "etc"]
CSV_COLUMNS = ["date", "type", "category", "amount", "memo", "tags"]
REQUIRED_COLUMNS = {"date", "type", "category", "amount"}


# ---------- 입력 검증: 문자열을 받아 올바른 값으로 바꾸거나 AppError ----------

def parse_date(text: str) -> str:
    text = text.strip()
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise ValueError
        datetime.strptime(text, "%Y-%m-%d")         # 2024-13-40 같은 없는 날짜도 걸러낸다
    except ValueError:
        raise AppError(f"날짜 형식이 올바르지 않습니다 ({text}).", "YYYY-MM-DD 형식, 예: 2024-01-15") from None
    return text


def parse_month(text: str) -> str:
    text = text.strip()
    try:
        if not re.fullmatch(r"\d{4}-\d{2}", text):
            raise ValueError
        datetime.strptime(text, "%Y-%m")
    except ValueError:
        raise AppError(f"월 형식이 올바르지 않습니다 ({text}).", "YYYY-MM 형식, 예: 2024-01") from None
    return text


def parse_type(text: str) -> str:
    text = text.strip()
    if text not in ("income", "expense"):
        raise AppError(f"타입은 income 또는 expense 만 가능합니다 ({text}).", "수입은 income, 지출은 expense")
    return text


def parse_amount(text: str) -> int:
    text = text.strip()
    try:
        amount = int(text)
    except ValueError:
        raise AppError(f"금액은 정수여야 합니다 ({text}).", "숫자만 입력하세요. 예: 15000") from None
    if amount <= 0:
        raise AppError(f"금액은 0보다 커야 합니다 ({text}).", "양수만 입력하세요. 예: 15000")
    return amount


def parse_tags(text: str) -> list[str]:
    """'meal, lunch' → ['meal', 'lunch']"""
    return [tag.strip() for tag in text.split(",") if tag.strip()]


def newest_first(tx: Transaction) -> tuple[str, str]:
    """최신순 정렬 기준: 날짜, 같은 날이면 나중에 입력한 id."""
    return (tx.date, tx.id)


@dataclass
class MonthSummary:
    income: int
    expense: int
    top: list[tuple[str, int]]       # [(카테고리, 지출 합계), ...]
    budget: int | None

    @property
    def balance(self) -> int:
        return self.income - self.expense


# ---------- 서비스: 저장소 3개를 조합한 규칙 ----------

class BudgetService:
    def __init__(self, data_dir: Path) -> None:
        self.transactions = TransactionRepository(data_dir)
        self.categories = CategoryStore(data_dir)
        self.budgets = BudgetStore(data_dir)

    # --- 카테고리 ---
    def ensure_default_categories(self) -> bool:
        """카테고리가 비어 있으면 기본 카테고리를 등록한다(안 A). 등록했으면 True."""
        if self.categories.names():
            return False
        self.categories.save(DEFAULT_CATEGORIES)
        return True

    def check_category(self, name: str) -> str:
        name = name.strip()
        names = self.categories.names()
        if name not in names:
            raise AppError(
                f"등록되지 않은 카테고리입니다 ({name}).",
                f"등록된 카테고리: {', '.join(names)} / 새로 쓰려면 category add",
            )
        return name

    def add_category(self, name: str) -> str:
        name = name.strip()
        names = self.categories.names()
        if not name:
            raise AppError("카테고리명이 비어 있습니다.", "예: food")
        if name in names:
            raise AppError(f"이미 있는 카테고리입니다 ({name}).", "category list 로 목록을 확인하세요.")
        self.categories.save(names + [name])
        return name

    def remove_category(self, name: str) -> str:
        name = self.check_category(name)
        used = sum(1 for tx in self.transactions.iter_all() if tx.category == name)
        if used:                                              # 사용 중이면 삭제를 막는다
            raise AppError(
                f"{name} 카테고리를 사용하는 거래가 {used}건 있어 삭제할 수 없습니다.",
                "update --id <id> --category <다른 카테고리> 로 먼저 옮기세요.",
            )
        self.categories.save([n for n in self.categories.names() if n != name])
        return name

    # --- 거래 추가 · 조회 ---
    def add(self, date: str, type_: str, category: str, amount: int,
            memo: str = "", tags: list[str] | None = None) -> Transaction:
        tx = Transaction(
            id=f"TX-{self.transactions.next_number():06d}",
            type=type_, date=date, amount=amount,
            category=self.check_category(category),
            memo=memo, tags=tags or [],
        )
        self.transactions.append([tx])
        return tx

    def latest(self, limit: int) -> list[Transaction]:
        """최신 limit건. 파일을 흘려보내면서 상위 limit건만 기억한다."""
        if limit <= 0:
            raise AppError(f"--limit 은 1 이상이어야 합니다 ({limit}).", "예: --limit 10")
        return heapq.nlargest(limit, self.transactions.iter_all(), key=newest_first)

    def search(self, start: str | None = None, end: str | None = None,
               category: str | None = None, type_: str | None = None,
               keyword: str | None = None, tag: str | None = None) -> list[Transaction]:
        """모든 조건을 만족(AND)하는 거래를 최신순으로."""
        matched: Iterator[Transaction] = (
            tx for tx in self.transactions.iter_all()
            if (start is None or tx.date >= start)
            and (end is None or tx.date <= end)
            and (category is None or tx.category == category)
            and (type_ is None or tx.type == type_)
            and (keyword is None or keyword in tx.memo)
            and (tag is None or tag in tx.tags)
        )
        return sorted(matched, key=newest_first, reverse=True)   # 조건에 맞는 것만 정렬

    # --- 수정 · 삭제 ---
    def update(self, tx_id: str, changes: dict[str, Any]) -> Transaction:
        if not changes:
            raise AppError("바꿀 항목이 없습니다.", "예: update --id TX-000001 --amount 18000")
        old = self.transactions.find(tx_id)
        if old is None:
            raise AppError(f"id={tx_id} 거래를 찾을 수 없습니다.", "list 명령으로 id를 먼저 확인하세요.")
        if "category" in changes:
            changes["category"] = self.check_category(str(changes["category"]))
        new = replace(old, **changes)        # 적은 항목만 바뀐 새 Transaction
        self.transactions.rewrite(tx_id, new)
        return new

    def delete(self, tx_id: str) -> None:
        if not self.transactions.rewrite(tx_id, None):
            raise AppError(f"id={tx_id} 거래를 찾을 수 없습니다.", "list 명령으로 id를 먼저 확인하세요.")

    # --- 예산 · 요약 ---
    def set_budget(self, month: str, amount: int) -> None:
        self.budgets.set(month, amount)

    def summary(self, month: str, top: int) -> MonthSummary | None:
        """그 달 거래를 한 번 훑으면서 합계만 더한다. 거래가 없으면 None."""
        income = expense = count = 0
        by_category: Counter[str] = Counter()
        for tx in self.transactions.iter_all():
            if not tx.date.startswith(month):
                continue
            count += 1
            if tx.type == "income":
                income += tx.amount
            else:
                expense += tx.amount
                by_category[tx.category] += tx.amount
        if count == 0:
            return None
        return MonthSummary(income, expense, by_category.most_common(top), self.budgets.get(month))

    # --- CSV 내보내기 · 가져오기 ---
    def export_csv(self, out: Path, start: str, end: str) -> int:
        """start~end 거래를 CSV로 쓴다(파일 순서대로, 한 건씩). 쓴 건수를 돌려준다."""
        count = 0
        try:
            with out.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                for tx in self.transactions.iter_all():
                    if start <= tx.date <= end:
                        row = {col: getattr(tx, col) for col in CSV_COLUMNS}
                        row["tags"] = ",".join(tx.tags)
                        writer.writerow(row)
                        count += 1
        except OSError as e:
            raise AppError(f"{out} 파일을 쓸 수 없습니다 ({e.strerror}).", "폴더가 있는지, 파일이 열려 있지 않은지 확인하세요.") from None
        return count

    def import_csv(self, src: Path) -> tuple[int, list[str]]:
        """행마다 검사해서 통과한 행만 저장한다(부분 성공). (저장 건수, 실패 리포트)를 돌려준다."""
        try:
            with src.open(encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
                if missing:
                    raise AppError(
                        f"CSV 헤더에 필수 컬럼이 없습니다: {', '.join(sorted(missing))}",
                        "첫 줄을 date,type,category,amount,memo,tags 로 맞추세요.",
                    )
                good: list[Transaction] = []
                errors: list[str] = []
                for row in reader:
                    try:
                        good.append(Transaction(
                            id="",                       # id는 검사가 끝난 뒤 붙인다
                            date=parse_date(row["date"] or ""),
                            type=parse_type(row["type"] or ""),
                            category=self.check_category(row["category"] or ""),
                            amount=parse_amount(row["amount"] or ""),
                            memo=(row.get("memo") or "").strip(),
                            tags=parse_tags(row.get("tags") or ""),
                        ))
                    except AppError as e:
                        errors.append(f"{reader.line_num}행: {e}")
        except FileNotFoundError:
            raise AppError(f"{src} 파일이 없습니다.", "경로와 파일 이름을 확인하세요.") from None
        except UnicodeDecodeError:
            raise AppError(f"{src} 파일이 UTF-8 이 아닙니다.", "엑셀에서 'CSV UTF-8' 형식으로 다시 저장하세요.") from None

        # 검사가 모두 끝난 뒤, 통과한 행만 한꺼번에 추가한다
        number = self.transactions.next_number()
        new_txs = [replace(tx, id=f"TX-{number + i:06d}") for i, tx in enumerate(good)]
        self.transactions.append(new_txs)
        return len(new_txs), errors
