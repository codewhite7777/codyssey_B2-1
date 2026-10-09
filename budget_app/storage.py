"""파일 입출력: 줄 단위 읽기, 스키마 검사, 단일 파일 원자적 교체, 접근 잠금."""

import json
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import TextIO, cast

from .errors import AppError, ConflictError, StorageError, ValidationError
from .models import MonthlyBudget, Transaction, transaction_key
from .validators import TransactionType, validate_category_name

DATA_NAMES = ("transactions.jsonl", "categories.jsonl", "budgets.jsonl")
LOCK_NAME = ".budget_app.lock"


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"중복 JSON 필드: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"허용되지 않는 JSON 숫자: {value}")


@contextmanager
def atomic_text(path: Path) -> Iterator[TextIO]:
    """실패하면 원본 보존. temp와 원본은 같은 디렉터리/파일시스템에 둔다.

    단일 교체의 원자성이지 여러 파일의 트랜잭션이나 정전 내구성 보장은 아니다.
    """
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        try:
            stream = os.fdopen(fd, "w", encoding="utf-8", newline="")
        except BaseException:
            os.close(fd)
            raise
        with stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_record(stream: TextIO, record: Mapping[str, object]) -> None:
    stream.write(json.dumps(dict(record), ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")


def iter_jsonl(path: Path) -> Iterator[tuple[int, dict[str, object]]]:
    """read()/readlines() 없이 한 줄씩 검증해서 전달한다."""
    line_number = 0
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    record = json.loads(line, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
                    if not isinstance(record, dict):
                        raise ValueError("JSON 객체가 아닙니다.")
                except (ValueError, TypeError) as exc:
                    raise StorageError(
                        f"{path.name}:{line_number} 저장 데이터가 손상되었습니다: {exc}",
                        "해당 행과 백업을 확인하세요. 손상된 행은 자동으로 건너뛰거나 삭제하지 않습니다.",
                    ) from exc
                yield line_number, record
    except UnicodeError as exc:
        raise StorageError(f"{path.name}의 UTF-8 인코딩이 잘못되었습니다.", "원본을 백업한 뒤 UTF-8 형식의 정상 파일로 복구하세요.") from exc


def _schema(record: dict[str, object], required: set[str], optional: set[str] | None = None) -> None:
    allowed = required | (optional or set())
    if not required <= record.keys() or not record.keys() <= allowed:
        raise ValidationError("저장 레코드의 필드 구성이 올바르지 않습니다.", "README의 JSONL 스키마를 확인하세요.")


def transaction_from_record(record: dict[str, object]) -> Transaction:
    _schema(record, {"id", "type", "date", "amount", "category"}, {"memo", "tags"})
    tags = record.get("tags", [])
    if not isinstance(tags, list):
        raise ValidationError("저장된 tags는 JSON 배열이어야 합니다.", '예: "tags": ["meal"]')
    # JSON은 외부 입력이다. 타입 힌트와 별개로 Transaction이 런타임 검증한다.
    return Transaction(
        id=cast(str, record["id"]), type=cast(TransactionType, record["type"]),
        date=cast(str, record["date"]), amount=cast(int, record["amount"]),
        category=cast(str, record["category"]), memo=cast(str, record.get("memo", "")),
        tags=tuple(cast(list[str], tags)),
    )


class TransactionRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def iter_transactions(self) -> Iterator[Transaction]:
        previous: tuple[str, str] | None = None
        with closing(iter_jsonl(self.path)) as records:
            for line_number, record in records:
                try:
                    transaction = transaction_from_record(record)
                    key = transaction_key(transaction)
                    if previous is not None and key >= previous:
                        raise ValidationError("거래 정렬 순서가 잘못되었거나 중복 거래가 있습니다.", "날짜/ID 내림차순 저장 규칙과 백업을 확인하세요.")
                    previous = key
                except AppError as exc:
                    raise StorageError(f"{self.path.name}:{line_number} {exc.message}", exc.hint) from exc
                yield transaction

    def replace_all(self, transactions: Iterator[Transaction]) -> None:
        previous: tuple[str, str] | None = None
        with atomic_text(self.path) as stream:
            for transaction in transactions:
                key = transaction_key(transaction)
                if previous is not None and key >= previous:
                    raise StorageError("교체할 거래의 정렬 순서가 잘못되었습니다.", "원본은 변경하지 않았습니다. 입력과 구현을 확인하세요.")
                previous = key
                write_record(stream, asdict(transaction))


class CategoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> set[str]:
        categories: set[str] = set()
        with closing(iter_jsonl(self.path)) as records:
            for line, record in records:
                try:
                    _schema(record, {"name"})
                    name = validate_category_name(cast(str, record["name"]))
                    if name in categories:
                        raise ValidationError("중복된 카테고리가 저장되어 있습니다.", "카테고리 파일과 백업을 확인하세요.")
                    categories.add(name)
                except AppError as exc:
                    raise StorageError(f"{self.path.name}:{line} {exc.message}", exc.hint) from exc
        return categories

    def save(self, categories: set[str]) -> None:
        with atomic_text(self.path) as stream:
            for name in sorted(categories):
                write_record(stream, {"name": validate_category_name(name)})


class BudgetStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, MonthlyBudget]:
        budgets: dict[str, MonthlyBudget] = {}
        with closing(iter_jsonl(self.path)) as records:
            for line, record in records:
                try:
                    _schema(record, {"month", "amount"})
                    budget = MonthlyBudget(cast(str, record["month"]), cast(int, record["amount"]))
                    if budget.month in budgets:
                        raise ValidationError("같은 월의 예산이 중복 저장되어 있습니다.", "예산 파일과 백업을 확인하세요.")
                    budgets[budget.month] = budget
                except AppError as exc:
                    raise StorageError(f"{self.path.name}:{line} {exc.message}", exc.hint) from exc
        return budgets

    def save(self, budgets: dict[str, MonthlyBudget]) -> None:
        with atomic_text(self.path) as stream:
            for month in sorted(budgets):
                write_record(stream, asdict(budgets[month]))


class DataStore:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).expanduser().resolve()
        self.transactions = TransactionRepository(self.directory / DATA_NAMES[0])
        self.categories = CategoryStore(self.directory / DATA_NAMES[1])
        self.budgets = BudgetStore(self.directory / DATA_NAMES[2])

    @contextmanager
    def session(self) -> Iterator[None]:
        """읽기도 잠금: 일관된 카테고리/거래 스냅샷과 Windows 교체를 고려한다.

        입력 대기 중에는 잠그지 않는다. 명령의 실제 파일 작업 동안만 획득한다.
        강제 종료 후 남은 잠금은 자동 삭제하지 않는다(PID 재사용/오판 방지).
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        lock = self.directory / LOCK_NAME
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise ConflictError(
                "다른 가계부 작업이 진행 중이거나 이전 잠금 파일이 남아 있습니다.",
                f"실행 중인 작업을 종료한 뒤 재시도하세요. 강제 종료였다면 실행 중 프로세스가 없는지 확인한 후 {lock}만 제거하세요.",
            ) from exc
        try:
            try:
                os.write(fd, f"pid={os.getpid()}\n".encode("ascii"))
            finally:
                os.close(fd)
            self._initialize_locked()
            yield
        finally:
            lock.unlink(missing_ok=True)

    def _initialize_locked(self) -> None:
        paths = [self.directory / name for name in DATA_NAMES]
        for path in paths:
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise StorageError(f"저장 경로가 일반 파일이 아닙니다: {path}", "저장 파일 이름과 경로를 확인하세요. 심볼릭 링크는 사용하지 않습니다.")
        missing = [path for path in paths if not path.exists()]
        if missing and any(path.exists() and path.stat().st_size for path in paths):
            raise StorageError(
                "기존 데이터의 일부 저장 파일이 없습니다: " + ", ".join(path.name for path in missing),
                "데이터 유실로 간주하여 초기화하지 않습니다. 백업에서 3개 파일을 함께 복구하세요.",
            )
        for path in missing:
            with atomic_text(path):
                pass

    def check_external_path(self, path: str | Path) -> Path:
        raw = Path(path).expanduser()
        if raw.is_symlink():
            raise ValidationError("가져오기/내보내기 경로에 심볼릭 링크를 사용할 수 없습니다.", "일반 CSV 파일의 실제 경로를 지정하세요.")
        result = raw.resolve()
        for protected in [self.directory / name for name in (*DATA_NAMES, LOCK_NAME)]:
            if result == protected or (result.exists() and protected.exists() and os.path.samefile(result, protected)):
                raise ValidationError("내부 저장 파일을 CSV 경로로 지정할 수 없습니다.", "transactions/categories/budgets 및 잠금 파일과 다른 경로를 사용하세요.")
        return result
