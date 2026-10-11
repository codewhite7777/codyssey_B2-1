"""명령 해석과 대화형 입력/출력만 담당한다. 업무 규칙은 BudgetService에 있다."""

import argparse
import sys
from collections.abc import Callable, Generator, Sequence
from contextlib import closing
from pathlib import Path
from typing import TypeVar

from .decorators import handle_cli_errors, safe_text, show_error
from .errors import UsageError, ValidationError
from .models import MonthSummary, SearchFilter, Transaction
from .service import BudgetService, DEFAULT_LIMIT
from .validators import (
    parse_amount, parse_tags, validate_category_name, validate_date,
    validate_transaction_type,
)

T = TypeVar("T")


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: object, **kwargs: object) -> None:
        """각 명령에 공통 옵션과 엄격한 옵션 표기 규칙을 등록한다.

        argparse의 자동 축약과 -h를 끄고 --help, --data-dir를 추가한다.
        자식 명령의 경로 기본값을 SUPPRESS로 두어 부모에서 받은 경로를 지키게 한다.
        """
        # 축약 옵션을 허용하지 않아 과제의 -- 표기를 일관되게 유지한다.
        kwargs["allow_abbrev"] = False
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)
        self.add_argument("--help", action="help", help="사용 방법 표시")
        self.add_argument("--data-dir", type=Path, default=argparse.SUPPRESS,
                          metavar="PATH", help="저장 폴더 (기본: ./data)")

    def error(self, message: str) -> None:
        """명령 해석 오류를 원인과 도움말 힌트가 있는 UsageError로 바꾼다.

        여기서 프로세스를 종료하지 않고 main의 오류 데코레이터가 종료 코드 2를 반환하게 한다.
        """
        raise UsageError(message, f"{self.prog} --help로 사용 방법을 확인하세요. 옵션은 -- 형식입니다.")


def _positive(raw: str) -> int:
    """옵션의 숫자 문자열을 양수 정수로 바꾸고 argparse용 오류로 연결한다.

    실제 금액 규칙은 parse_amount를 재사용하며, 실패하면 옵션 해석 단계에서 거부한다.
    """
    try:
        return parse_amount(raw)
    except ValidationError as exc:
        raise argparse.ArgumentTypeError("1 이상의 정수가 필요합니다.") from exc


def build_parser() -> ArgumentParser:
    """명령 이름·옵션·기본값을 등록한 파서를 반환한다.

    사용자 입력이나 파일 접근은 하지 않는다. update의 생략된 옵션은 SUPPRESS로
    결과에서 제외하여 기존 거래 값을 None 등으로 덮어쓰지 않게 한다.
    """
    parser = ArgumentParser(prog="python -m budget_app", description="파일 기반 용돈 기입장")
    parser.set_defaults(data_dir=Path("data"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add", help="대화형 거래 추가")
    listing = commands.add_parser("list", help="최신순 거래 목록")
    listing.add_argument("--limit", type=_positive, default=DEFAULT_LIMIT, help="출력 건수 (기본: 20)")
    search = commands.add_parser("search", help="조건을 모두 만족하는 거래 검색")
    search.add_argument("--from", dest="start", help="시작일 (포함, YYYY-MM-DD)")
    search.add_argument("--to", dest="end", help="종료일 (포함, YYYY-MM-DD)")
    search.add_argument("--category", help="등록된 카테고리, 정확히 일치")
    search.add_argument("--type", choices=("income", "expense"))
    search.add_argument("--q", dest="query", help="메모 부분 문자열, 대소문자 구분 없음")
    search.add_argument("--tag", help="태그 정확히 일치, 대소문자 구분")
    search.add_argument("--limit", type=_positive, help="생략 시 일치하는 전체 결과")
    summary = commands.add_parser("summary", help="월별 요약과 지출 TOP N")
    summary.add_argument("--month", required=True, help="YYYY-MM")
    summary.add_argument("--top", type=_positive, default=3, help="순위 수 (기본: 3)")
    budget = commands.add_parser("budget", help="월 예산 설정/조회")
    budgets = budget.add_subparsers(dest="action", required=True)
    setting = budgets.add_parser("set", help="월 예산 저장 또는 변경")
    setting.add_argument("--month", required=True)
    setting.add_argument("--amount", required=True, type=_positive)
    showing = budgets.add_parser("show", help="월 예산 조회")
    showing.add_argument("--month", required=True)
    category = commands.add_parser("category", help="카테고리 관리")
    categories = category.add_subparsers(dest="action", required=True)
    categories.add_parser("add", help="대화형 카테고리 등록")
    categories.add_parser("list", help="카테고리 목록")
    categories.add_parser("remove", help="대화형 삭제; 사용 중이면 거부")
    update = commands.add_parser("update", help="옵션 기반 거래 수정 (빈 memo/tags로 비우기 가능)")
    update.add_argument("--id", required=True, dest="identifier")
    # 고정된 여섯 필드는 동적 설정 사전 대신 바로 읽을 수 있게 선언한다.
    update.add_argument("--date", default=argparse.SUPPRESS, help="거래 날짜 (YYYY-MM-DD)")
    update.add_argument(
        "--type", choices=("income", "expense"), default=argparse.SUPPRESS,
        help="수입 income / 지출 expense",
    )
    update.add_argument("--category", default=argparse.SUPPRESS, help="등록된 카테고리")
    update.add_argument(
        "--amount", type=_positive, default=argparse.SUPPRESS, help="양수 정수 금액",
    )
    update.add_argument("--memo", default=argparse.SUPPRESS, help="빈 문자열로 메모 비우기 가능")
    update.add_argument("--tags", default=argparse.SUPPRESS, help="쉼표 구분; 빈 문자열로 비우기 가능")
    delete = commands.add_parser("delete", help="거래 ID로 삭제")
    delete.add_argument("--id", required=True, dest="identifier")
    importing = commands.add_parser("import", help="CSV 전체 검증 후 일괄 반영")
    importing.add_argument("--from", required=True, dest="source", type=Path)
    exporting = commands.add_parser("export", help="기간을 지정해 CSV 내보내기")
    exporting.add_argument("--out", required=True, type=Path)
    exporting.add_argument("--month", help="YYYY-MM; --from/--to와 동시 사용 불가")
    exporting.add_argument("--from", dest="start", help="시작일; --to와 함께 지정")
    exporting.add_argument("--to", dest="end", help="종료일; --from과 함께 지정")
    return parser


def prompt(label: str, parse: Callable[[str], T]) -> T:
    """필드 하나를 입력받아 변환·검증에 성공한 값을 반환한다.

    parse가 ValidationError를 내면 원인과 힌트를 출력하고 같은 필드를 재입력받는다.
    EOF나 Ctrl+C는 잡지 않아 main에서 취소 종료 코드로 처리하게 한다.
    """
    while True:
        raw = input(label)
        try:
            return parse(raw)
        except ValidationError as exc:
            show_error(exc.message, exc.hint)


def print_transactions(transactions: Generator[Transaction, None, None]) -> None:
    """거래를 한 건씩 출력하고 최종 조회 건수 또는 데이터 없음 안내를 표시한다.

    첫 거래에서만 표 머리글을 쓰며, 거래를 목록으로 모으지 않는다.
    출력 실패나 순회 종료 시 제너레이터를 닫아 열린 파일과 잠금도 정리한다.
    """
    count = 0
    with closing(transactions):
        for transaction in transactions:
            if count == 0:
                print("ID | 날짜 | 타입 | 카테고리 | 금액(원) | 메모 | 태그")
            print(" | ".join((
                safe_text(transaction.id), transaction.date, transaction.type,
                safe_text(transaction.category), f"{transaction.amount:,}",
                safe_text(transaction.memo), safe_text(",".join(transaction.tags)),
            )))
            count += 1
    print(f"[조회 완료] {count}건" if count else "[데이터 없음] 조건에 맞는 거래가 없습니다.")


def print_summary(summary: MonthSummary, top: int) -> None:
    """계산이 끝난 월별 결과를 수입·지출·예산·순위 순서로 출력한다.

    파일을 다시 읽거나 합계를 재계산하지 않는다. 데이터가 없는 달도 알리고,
    초과 여부가 참일 때만 경고를 출력한다. top은 화면에 표시할 순위 수다.
    """
    print(f"[{summary.month} 월별 요약]")
    if summary.count == 0:
        print("[데이터 없음] 해당 월에 기록된 거래가 없습니다.")
    print(f"총 수입: {summary.income:,}원")
    print(f"총 지출: {summary.expense:,}원")
    print(f"잔액: {summary.balance:,}원")
    if summary.budget is not None:
        print(f"예산: {summary.budget:,}원 (사용률 {summary.usage_percent}%)")
        if summary.exceeded:
            print(f"[경고] 예산을 {summary.expense - summary.budget:,}원 초과했습니다.")
    else:
        print("예산: 미설정")
    print(f"지출 TOP {top}")
    if not summary.top_expenses:
        print("(지출 없음)")
    for rank, (category, amount) in enumerate(summary.top_expenses, 1):
        print(f"{rank}) {safe_text(category)} {amount:,}원")


def _add(service: BudgetService) -> None:
    """등록된 카테고리를 보여 주고 거래 필드를 대화형으로 입력받아 저장한다.

    빈 카테고리 목록이면 등록을 안내하며, 각 필드는 prompt로 재입력 검증한다.
    입력 대기 중에는 파일을 잠그지 않고, 저장 직전 서비스에서 등록 여부를 재검사한다.
    """
    categories = set(service.list_categories())
    if not categories:
        raise ValidationError("등록된 카테고리가 없습니다.", "category add로 카테고리를 먼저 등록한 뒤 add를 실행하세요.")
    print("등록된 카테고리: " + ", ".join(safe_text(name) for name in sorted(categories)))
    date = prompt("날짜(YYYY-MM-DD): ", lambda value: validate_date(value.strip()))
    kind = prompt("타입(income/expense): ", lambda value: validate_transaction_type(value.strip()))

    def parse_category(raw: str) -> str:
        """입력한 이름의 공백을 정리하고 화면에 안내한 카테고리에 포함되는지 검사한다.

        미등록 이름은 ValidationError로 거부하여 prompt의 재입력 흐름으로 돌린다.
        """
        name = validate_category_name(raw.strip())
        if name not in categories:
            raise ValidationError(f"등록되지 않은 카테고리입니다: {name}", "위에 표시된 카테고리 중 하나를 입력하세요.")
        return name

    category = prompt("카테고리: ", parse_category)
    amount = prompt("금액(양수 정수): ", parse_amount)
    memo = input("메모(선택): ")
    tags = prompt("태그(쉼표 구분, 선택): ", parse_tags)
    transaction = service.add(date=date, type=kind, category=category, amount=amount, memo=memo, tags=tags)
    print(f"[저장 완료] id={transaction.id}")


@handle_cli_errors
def main(argv: Sequence[str] | None = None) -> int:
    """명령을 해석하여 해당 서비스 기능을 실행하고 성공 시 종료 코드 0을 반환한다.

    명령별 입력 변환과 출력만 담당하고 파일·업무 규칙은 서비스에 위임한다.
    실제 제너레이터 순회와 stdout 동기화까지 데코레이터 안에서 실행하므로
    늦게 발생한 읽기·출력 오류도 원인·힌트 및 비정상 종료 코드로 변환된다.
    """
    args = build_parser().parse_args(argv)
    service = BudgetService(args.data_dir)
    if args.command == "add":
        _add(service)
    elif args.command == "list":
        print_transactions(service.list_transactions(args.limit))
    elif args.command == "search":
        filters = SearchFilter(
            start=args.start, end=args.end, category=args.category,
            type=args.type, query=args.query, tag=args.tag,
        )
        print_transactions(service.search(filters, args.limit))
    elif args.command == "summary":
        print_summary(service.summary(args.month, args.top), args.top)
    elif args.command == "budget":
        if args.action == "set":
            service.set_budget(args.month, args.amount)
            print(f"[저장 완료] {args.month} 예산 {args.amount:,}원")
        else:
            budget = service.get_budget(args.month)
            print(f"{args.month} 예산: {budget.amount:,}원" if budget else f"[미설정] {args.month} 예산이 없습니다.")
    elif args.command == "category":
        if args.action == "list":
            names = service.list_categories()
            for name in names:
                print("- " + safe_text(name))
            if not names:
                print("[데이터 없음] category add로 카테고리를 등록하세요.")
        else:
            name = prompt("카테고리명: ", lambda value: validate_category_name(value.strip()))
            if args.action == "add":
                service.add_category(name)
                print(f"[저장 완료] category={safe_text(name)}")
            else:
                service.remove_category(name)
                print(f"[삭제 완료] category={safe_text(name)}")
    elif args.command == "update":
        changes = {key: value for key, value in vars(args).items()
                   if key in {"date", "type", "category", "amount", "memo", "tags"}}
        if "tags" in changes:
            changes["tags"] = parse_tags(changes["tags"])
        updated = service.update(args.identifier, **changes)
        print(f"[수정 완료] id={updated.id}")
    elif args.command == "delete":
        service.delete(args.identifier)
        print(f"[삭제 완료] id={safe_text(args.identifier)}")
    elif args.command == "import":
        count = service.import_csv(args.source)
        print(f"[완료] imported={count}, skipped=0")
    elif args.command == "export":
        count = service.export_csv(args.out, month=args.month, start=args.start, end=args.end)
        print(f"[완료] {safe_text(args.out)} ({count} records)")
    sys.stdout.flush()
    return 0
