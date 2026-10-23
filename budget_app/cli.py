"""CLI 계층: 명령·옵션 해석, input() 질문, print() 출력. 규칙과 파일 형식은 모른다."""

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from .decorators import handle_errors
from .errors import AppError, show_error
from .models import Transaction
from .service import BudgetService, parse_amount, parse_date, parse_month, parse_tags, parse_type
from .storage import ensure_data_dir

T = TypeVar("T")


# ---------- 공통 도우미 ----------

def open_service(args: argparse.Namespace) -> BudgetService:
    """저장 폴더를 준비하고 서비스를 만든다. 처음 실행이면 안내를 출력한다."""
    data_dir = Path(args.data_dir)
    created = ensure_data_dir(data_dir)
    if created:
        print(f"[안내] 저장 파일을 만들었습니다: {data_dir}/ ({', '.join(created)})")
    service = BudgetService(data_dir)
    if service.ensure_default_categories():
        print("[안내] 카테고리가 비어 있어 기본 카테고리를 등록했습니다: food, transport, rent, salary, etc")
    return service


def ask(prompt: str, parse: Callable[[str], T]) -> T:
    """올바른 값이 들어올 때까지 같은 질문을 다시 한다."""
    while True:
        try:
            return parse(input(prompt))
        except AppError as e:
            show_error(e)


def format_tx(tx: Transaction) -> str:
    line = f"{tx.id} | {tx.date} | {tx.type:<7} | {tx.category} | {tx.amount} | {tx.memo}"
    if tx.tags:
        line += " | #" + " #".join(tx.tags)
    return line


def print_list(transactions: list[Transaction], empty_message: str) -> None:
    if not transactions:
        print(f"[안내] {empty_message}")
    for tx in transactions:
        print(format_tx(tx))


# ---------- 명령 (모두 @handle_errors 로 감싼다) ----------

@handle_errors
def cmd_add(args: argparse.Namespace) -> None:
    service = open_service(args)
    date = ask("날짜(YYYY-MM-DD): ", parse_date)
    type_ = ask("타입(income/expense): ", parse_type)
    category = ask("카테고리: ", service.check_category)
    amount = ask("금액(양수): ", parse_amount)
    memo = input("메모(선택): ").strip()
    tags = parse_tags(input("태그(쉼표로 구분, 없으면 엔터): "))
    tx = service.add(date, type_, category, amount, memo, tags)
    print(f"[저장 완료] id={tx.id}")


@handle_errors
def cmd_list(args: argparse.Namespace) -> None:
    service = open_service(args)
    print_list(service.latest(args.limit), "저장된 거래가 없습니다. add 로 먼저 추가하세요.")


@handle_errors
def cmd_search(args: argparse.Namespace) -> None:
    service = open_service(args)
    results = service.search(
        start=parse_date(args.start) if args.start else None,
        end=parse_date(args.end) if args.end else None,
        category=args.category,
        type_=parse_type(args.type) if args.type else None,
        keyword=args.q,
        tag=args.tag,
    )
    print_list(results, "조건에 맞는 거래가 없습니다.")


@handle_errors
def cmd_summary(args: argparse.Namespace) -> None:
    service = open_service(args)
    month = parse_month(args.month)
    s = service.summary(month, args.top)
    if s is None:
        print(f"[안내] {month} 데이터 없음")
        return
    print(f"총 수입: {s.income}원")
    print(f"총 지출: {s.expense}원")
    print(f"잔액: {s.balance}원")
    if s.budget is None:
        print("예산: 미설정 (budget set 으로 설정할 수 있습니다)")
    else:
        print(f"예산: {s.budget}원 (사용률 {s.expense / s.budget * 100:.1f}%)")
        if s.expense > s.budget:
            print(f"[경고] 예산을 {s.expense - s.budget}원 초과했습니다!")
    print(f"\n지출 TOP {args.top}")
    if not s.top:
        print("지출 없음")
    for rank, (category, total) in enumerate(s.top, start=1):
        print(f"{rank}) {category} {total}원")


@handle_errors
def cmd_budget_set(args: argparse.Namespace) -> None:
    service = open_service(args)
    month, amount = parse_month(args.month), parse_amount(args.amount)
    service.set_budget(month, amount)
    print(f"[저장 완료] {month} 예산 {amount}원")


@handle_errors
def cmd_category_add(args: argparse.Namespace) -> None:
    service = open_service(args)
    name = service.add_category(input("카테고리명: "))
    print(f"[저장 완료] category={name}")


@handle_errors
def cmd_category_list(args: argparse.Namespace) -> None:
    service = open_service(args)
    for name in service.categories.names():
        print(f"- {name}")


@handle_errors
def cmd_category_remove(args: argparse.Namespace) -> None:
    service = open_service(args)
    name = service.remove_category(input("삭제할 카테고리명: "))
    print(f"[삭제 완료] category={name}")


@handle_errors
def cmd_update(args: argparse.Namespace) -> None:
    service = open_service(args)
    changes: dict[str, Any] = {}            # 적은 옵션만 바꾼다 (옵션 방식으로 고정)
    if args.date is not None:
        changes["date"] = parse_date(args.date)
    if args.type is not None:
        changes["type"] = parse_type(args.type)
    if args.category is not None:
        changes["category"] = args.category
    if args.amount is not None:
        changes["amount"] = parse_amount(args.amount)
    if args.memo is not None:
        changes["memo"] = args.memo
    if args.tags is not None:
        changes["tags"] = parse_tags(args.tags)
    tx = service.update(args.id, changes)
    print(f"[수정 완료] {format_tx(tx)}")


@handle_errors
def cmd_delete(args: argparse.Namespace) -> None:
    service = open_service(args)
    service.delete(args.id)
    print(f"[삭제 완료] id={args.id}")


@handle_errors
def cmd_export(args: argparse.Namespace) -> None:
    service = open_service(args)
    if args.month and (args.start or args.end):
        raise AppError("--month 와 --from/--to 는 함께 쓸 수 없습니다.", "둘 중 하나만 지정하세요.")
    if args.month:
        month = parse_month(args.month)
        start, end = f"{month}-01", f"{month}-31"
    elif args.start and args.end:
        start, end = parse_date(args.start), parse_date(args.end)
    else:
        raise AppError("내보낼 기간이 없습니다.",
                       "--month YYYY-MM 또는 --from YYYY-MM-DD --to YYYY-MM-DD 를 지정하세요.")
    count = service.export_csv(Path(args.out), start, end)
    print(f"[완료] {args.out} ({count} records)")


@handle_errors
def cmd_import(args: argparse.Namespace) -> None:
    service = open_service(args)
    imported, errors = service.import_csv(Path(args.src))
    print(f"[완료] imported={imported}, skipped={len(errors)}")
    for message in errors:
        print(f"  {message}")
    if errors:
        raise AppError(f"{len(errors)}개 행을 건너뛰었습니다.", "위 행만 고쳐서 새 CSV로 다시 import 하세요.")


# ---------- 명령어 정의 (argparse) ----------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m budget_app", description="나만의 용돈 기입장")
    parser.add_argument("--data-dir", default="data", help="저장 폴더 (기본: ./data)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<명령>")

    p = sub.add_parser("add", help="거래 추가 (대화형)")
    p.set_defaults(handler=cmd_add)

    p = sub.add_parser("list", help="최신순 목록")
    p.add_argument("--limit", type=int, default=10, help="보여줄 개수 (기본 10)")
    p.set_defaults(handler=cmd_list)

    p = sub.add_parser("search", help="조건 검색 (최신순)")
    p.add_argument("--from", dest="start", help="시작일 YYYY-MM-DD")
    p.add_argument("--to", dest="end", help="종료일 YYYY-MM-DD")
    p.add_argument("--category", help="카테고리")
    p.add_argument("--type", help="income / expense")
    p.add_argument("--q", help="메모에 포함된 단어")
    p.add_argument("--tag", help="태그")
    p.set_defaults(handler=cmd_search)

    p = sub.add_parser("summary", help="월별 요약")
    p.add_argument("--month", required=True, help="YYYY-MM")
    p.add_argument("--top", type=int, default=3, help="지출 TOP N (기본 3)")
    p.set_defaults(handler=cmd_summary)

    budget = sub.add_parser("budget", help="예산 설정").add_subparsers(dest="action", required=True, metavar="<동작>")
    p = budget.add_parser("set", help="월 예산 저장")
    p.add_argument("--month", required=True, help="YYYY-MM")
    p.add_argument("--amount", required=True, help="금액")
    p.set_defaults(handler=cmd_budget_set)

    category = sub.add_parser("category", help="카테고리 관리").add_subparsers(dest="action", required=True, metavar="<동작>")
    category.add_parser("add", help="추가 (대화형)").set_defaults(handler=cmd_category_add)
    category.add_parser("list", help="목록").set_defaults(handler=cmd_category_list)
    category.add_parser("remove", help="삭제 (대화형, 사용 중이면 거부)").set_defaults(handler=cmd_category_remove)

    p = sub.add_parser("update", help="거래 수정 (적은 옵션만 바뀜)")
    p.add_argument("--id", required=True, help="수정할 거래 id")
    for option in ("date", "type", "category", "amount", "memo", "tags"):
        p.add_argument(f"--{option}", help=f"새 {option}")
    p.set_defaults(handler=cmd_update)

    p = sub.add_parser("delete", help="거래 삭제")
    p.add_argument("--id", required=True, help="삭제할 거래 id")
    p.set_defaults(handler=cmd_delete)

    p = sub.add_parser("import", help="CSV 가져오기")
    p.add_argument("--from", dest="src", required=True, help="가져올 CSV 파일")
    p.set_defaults(handler=cmd_import)

    p = sub.add_parser("export", help="CSV 내보내기 (기간 필수)")
    p.add_argument("--out", required=True, help="만들 CSV 파일")
    p.add_argument("--month", help="YYYY-MM")
    p.add_argument("--from", dest="start", help="시작일 YYYY-MM-DD")
    p.add_argument("--to", dest="end", help="종료일 YYYY-MM-DD")
    p.set_defaults(handler=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)     # 사용법 오류면 argparse가 종료 코드 2로 끝낸다
    result: int = args.handler(args)
    return result
