"""파일 입출력: 줄 단위 읽기, 스키마 검사, 단일 파일 원자적 교체, 접근 잠금."""

import json
import os
import tempfile
from collections.abc import Generator, Iterator, Mapping
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
    """JSON 객체의 키·값 쌍을 사전으로 만들되 중복 키를 발견하면 ValueError를 낸다.

    json.loads의 object_pairs_hook으로 사용하여 같은 키가 조용히 덮어써지는 것을 막는다.
    """
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"중복 JSON 필드: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    """JSON 표준에 없는 NaN·Infinity 등의 숫자 상수를 발견하면 ValueError를 낸다.

    json.loads의 parse_constant 콜백으로 연결하여 저장 손상을 숨기지 않는다.
    """
    raise ValueError(f"허용되지 않는 JSON 숫자: {value}")


@contextmanager
def atomic_text(path: Path) -> Iterator[TextIO]:
    """같은 폴더의 임시 출력 파일을 제공하고 쓰기가 성공하면 원본 경로로 교체한다.

    yield 뒤에 flush·fsync·닫기·os.replace를 순서대로 실행한다.
    교체 전 실패하면 원본을 유지하고 finally에서 남은 임시 파일을 정리한다.
    출력 폴더가 있어야 하며 단일 파일 교체이지 다중 파일 커밋·정전 내구성 보장은 아니다.
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
    """레코드 하나를 UTF-8 텍스트 스트림에 JSON 한 줄과 줄바꿈으로 기록한다.

    값 안의 개행은 JSON 이스케이프로 저장하고 비표준 숫자는 거부한다.
    스트림을 닫거나 교체하지 않으며 그 책임은 atomic_text에 있다.
    """
    stream.write(json.dumps(dict(record), ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")


def iter_jsonl(path: Path) -> Generator[tuple[int, dict[str, object]], None, None]:
    """파일을 한 줄씩 읽고 행 번호와 검증된 JSON 객체를 전달한다.

    빈 줄·깨진 JSON·중복 키·잘못된 인코딩은 StorageError로 알린다.
    read/readlines로 전체를 올리지 않고 순회 종료나 close 시 파일을 닫는다.
    """
    line_number = 0
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    record = json.loads(
                        line, object_pairs_hook=_unique_object,
                        parse_constant=_reject_constant,
                    )
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
    """필수 필드가 모두 있고 허용하지 않은 필드가 없는지 검사한다.

    값의 자료형·범위는 여기서 검사하지 않고 뒤의 모델 검증에 맡긴다.
    """
    allowed = required | (optional or set())
    if not required <= record.keys() or not record.keys() <= allowed:
        raise ValidationError("저장 레코드의 필드 구성이 올바르지 않습니다.", "README의 JSONL 스키마를 확인하세요.")


def transaction_from_record(record: dict[str, object]) -> Transaction:
    """JSON 사전의 스키마를 확인하고 tags 배열을 튜플로 바꾸어 거래 객체를 반환한다.

    선택 필드가 없으면 빈 메모·태그를 사용한다. cast는 타입 설명일 뿐 값 변환이나
    검증이 아니므로 최종 필드 규칙은 Transaction 생성 시 다시 검사한다.
    """
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
        """거래 파일 경로만 보관한다. 파일 생성·잠금은 DataStore에서 처리한다."""
        self.path = path

    def iter_transactions(self) -> Generator[Transaction, None, None]:
        """거래 파일의 레코드를 모델로 바꾸며 날짜·ID 내림차순을 검사해 하나씩 전달한다.

        직전 정렬 키보다 크거나 같으면 순서 오류/동일 키 중복으로 거부한다.
        다른 날짜에 같은 ID가 있는지의 전역 검사는 서비스의 _inspect가 담당한다.
        """
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
        """정렬된 거래 스트림을 검사하며 임시 파일에 쓰고 완성되면 원본을 교체한다.

        정렬 순서가 깨지면 StorageError로 중단한다. 호출자가 잠금과 전역 ID 검사를
        먼저 수행해야 하며, 이 함수는 거래 전체를 메모리에 수집하지 않는다.
        """
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
        """카테고리 파일 경로를 보관한다. 생성자 자체에서는 파일에 접근하지 않는다."""
        self.path = path

    def load(self) -> set[str]:
        """카테고리 레코드를 검증하여 이름 집합으로 반환한다.

        이름 중복·스키마 오류를 행 번호와 함께 StorageError로 알린다. 목록은 메모리에 읽는다.
        """
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
        """카테고리 이름을 오름차순으로 검증·기록하고 완성된 임시 파일로 교체한다.

        호출자가 잠금을 소유해야 하며 거래에서 사용 중인지는 서비스가 미리 검사한다.
        """
        with atomic_text(self.path) as stream:
            for name in sorted(categories):
                write_record(stream, {"name": validate_category_name(name)})


class BudgetStore:
    def __init__(self, path: Path) -> None:
        """예산 파일 경로를 보관한다. 실제 읽기·쓰기는 load/save에서 수행한다."""
        self.path = path

    def load(self) -> dict[str, MonthlyBudget]:
        """예산 레코드를 검증하고 월을 키로 하는 MonthlyBudget 사전을 반환한다.

        같은 월이 두 번 나오거나 값이 잘못되면 행 번호를 붙인 StorageError로 중단한다.
        """
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
        """월 순서로 예산 객체를 JSON 레코드로 기록하고 예산 파일을 교체한다.

        유효한 모델과 월 키가 들어 있는 사전을 잠금 안에서 전달하는 서비스가 호출한다.
        """
        with atomic_text(self.path) as stream:
            for month in sorted(budgets):
                write_record(stream, asdict(budgets[month]))


class DataStore:
    def __init__(self, directory: str | Path) -> None:
        """저장 폴더를 절대 경로로 정리하고 거래·카테고리·예산 저장소를 구성한다.

        경로 계산만 하므로 help를 출력할 때는 데이터 파일이 생성되지 않는다.
        """
        self.directory = Path(directory).expanduser().resolve()
        self.transactions = TransactionRepository(self.directory / DATA_NAMES[0])
        self.categories = CategoryStore(self.directory / DATA_NAMES[1])
        self.budgets = BudgetStore(self.directory / DATA_NAMES[2])

    @contextmanager
    def session(self) -> Iterator[None]:
        """배타적 잠금을 획득하고 저장 파일을 초기화한 동안에만 파일 작업을 허용한다.

        O_EXCL로 잠금 파일을 중복 생성하지 못하게 하며 읽기 작업도 같은 잠금을 사용한다.
        yield가 끝나거나 예외가 나면 잠금을 지운다. 사용자 입력 대기에는 사용하지 않는다.
        강제 종료로 남은 잠금은 실행 중 프로세스가 없는지 확인한 사용자가 제거해야 한다.
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
        """잠금 상태에서 저장 경로를 검사하고 최초 실행에 필요한 세 파일을 만든다.

        기존 내용이 있는데 일부 파일이 없으면 유실로 보고 자동 초기화하지 않는다.
        디렉터리나 심볼릭 링크도 거부하며, 아직 전부 빈 초기화 상태라면 누락 파일을 만든다.
        """
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
        """CSV 경로를 실제 경로로 정리하고 내부 저장 파일을 가리키지 않는지 검사한다.

        심볼릭 링크와 내부 JSONL·잠금 파일의 동일 경로/하드링크를 거부한다.
        통과한 Path를 반환하며 파일의 존재·읽기 권한은 실제 입출력 때 확인한다.
        """
        raw = Path(path).expanduser()
        if raw.is_symlink():
            raise ValidationError("가져오기/내보내기 경로에 심볼릭 링크를 사용할 수 없습니다.", "일반 CSV 파일의 실제 경로를 지정하세요.")
        result = raw.resolve()
        for protected in [self.directory / name for name in (*DATA_NAMES, LOCK_NAME)]:
            if result == protected or (
                result.exists()
                and protected.exists()
                and os.path.samefile(result, protected)
            ):
                raise ValidationError(
                    "내부 저장 파일을 CSV 경로로 지정할 수 없습니다.",
                    "transactions/categories/budgets 및 잠금 파일과 다른 경로를 사용하세요.",
                )
        return result
