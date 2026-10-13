"""입력의 형식 변환과 값 검증을 여러 명령에서 공통으로 사용하는 계층.

parse_*는 문자열을 필요한 자료형으로 바꾸고, validate_*는 유효한 값을 그대로 반환한다.
예: parse_amount(" 15000 ") → 15000 → validate_amount(15000).
실패하면 ValidationError(원인, 해결 힌트)를 올린다. 여기서 직접 출력하거나 재입력받지 않는다.
같은 오류를 add의 prompt는 재입력으로, CSV import는 전체 미반영으로 처리한다.
타입 힌트는 이 계약을 설명할 뿐, 실행 중 검증을 자동으로 수행하지 않는다.
"""

import re
from datetime import date as Date
from typing import Literal

from .errors import ValidationError

# Literal은 허용할 문자열을 타입 도구에 알려 준다. 실제 입력 검사 함수도 아래에 필요하다.
TransactionType = Literal["income", "expense"]


def validate_date(value: str) -> str:
    """YYYY-MM-DD 문자열의 모양과 실제 날짜를 검사하고 원래 문자열을 반환한다.

    정규식으로 2026-1-6처럼 자릿수가 다른 입력을 거부한 뒤,
    Date.fromisoformat으로 2026-02-30처럼 존재하지 않는 날짜도 거부한다.
    문자열 아닌 값이나 잘못된 날짜는 ValidationError다. 공백 정리는 호출자의 책임이다.
    """
    hint = "실제로 존재하는 날짜를 YYYY-MM-DD 형식으로 입력하세요. 예: 2026-10-06"
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValidationError("날짜 형식이 올바르지 않습니다.", hint)
    try:
        Date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError("존재하지 않는 날짜입니다.", hint) from exc
    return value


def validate_month(value: str) -> str:
    """YYYY-MM을 검사하고 그대로 반환한다. 모양 검사 뒤 1일을 붙여 실제 연월을 검사한다.

    예: 2026-10은 허용하고 2026-13은 ValidationError로 거부한다.
    """
    hint = "월을 YYYY-MM 형식으로 입력하세요. 예: 2026-10"
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}", value) is None:
        raise ValidationError("월 형식이 올바르지 않습니다.", hint)
    try:
        Date.fromisoformat(f"{value}-01")
    except ValueError as exc:
        raise ValidationError("존재하지 않는 연도 또는 월입니다.", hint) from exc
    return value


def validate_amount(value: int) -> int:
    """입력이 양수 int일 때만 그대로 반환하고 나머지는 ValidationError로 거부한다.

    bool은 int의 하위 타입이므로 isinstance가 아니라 type(value) is int로 구분한다.
    int라는 타입 힌트만으로는 0·음수를 거부할 수 없어 값 범위도 검사한다.
    """
    if type(value) is not int or value <= 0:
        raise ValidationError("금액은 0보다 큰 정수여야 합니다.", "예: 15000. 0, 음수, 소수는 사용할 수 없습니다.")
    return value


def parse_amount(raw: str) -> int:
    """CLI/CSV 금액 문자열을 공백 정리 → 숫자 확인 → int 변환 → 양수 검증 순으로 처리한다.

    "15000"은 15000을 반환하지만 "15,000", "1.5", "-1", "0"은 거부한다.
    변환 오류도 ValidationError로 바꾸므로 호출자가 원인과 힌트를 일관되게 다룰 수 있다.
    """
    hint = "통화 기호나 쉼표 없이 양수 정수를 입력하세요. 예: 15000"
    if not isinstance(raw, str):
        raise ValidationError("금액 입력은 문자열이어야 합니다.", hint)
    normalized = raw.strip()
    if re.fullmatch(r"[0-9]+", normalized) is None:
        raise ValidationError("금액을 정수로 읽을 수 없습니다.", hint)
    try:
        amount = int(normalized)
    except ValueError as exc:
        raise ValidationError("금액을 정수로 변환할 수 없습니다.", hint) from exc
    return validate_amount(amount)


def validate_transaction_type(value: str) -> TransactionType:
    """income 또는 expense와 정확히 일치하는 문자열만 반환하고 나머지는 거부한다.

    대소문자나 공백을 자동 교정하지 않는다. CLI/CSV 호출자가 앞뒤 공백을 먼저 정리한다.
    """
    if value == "income":
        return "income"
    if value == "expense":
        return "expense"
    raise ValidationError("허용되지 않은 거래 타입입니다.", "income 또는 expense를 입력하세요.")


def validate_label(value: str, field_name: str) -> str:
    """비어 있지 않고 앞뒤 공백·C0 제어 문자·DEL이 없는 문자열인지 검사한다.

    id/카테고리/개별 태그에 공통 적용한다. 값을 교정하지 않고 그대로 반환하거나
    field_name을 넣은 ValidationError를 낸다. 실제 등록 여부는 검사하지 않는다.
    """
    hint = f"{field_name}에 앞뒤 공백과 제어 문자가 없는, 비어 있지 않은 문자열을 사용하세요."
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValidationError(f"{field_name}이(가) 올바르지 않습니다.", hint)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValidationError(f"{field_name}에 제어 문자가 있습니다.", hint)
    return value


def validate_category_name(value: str) -> str:
    """validate_label에 카테고리라는 항목 이름을 전달해 이름 형식만 검사한다.

    "food"가 실제 등록되어 있는지는 파일이 필요한 검사이므로 서비스가 따로 확인한다.
    """
    return validate_label(value, "카테고리")


def validate_memo(value: str) -> str:
    """문자열이면 빈 값·쉼표·개행도 바꾸지 않고 반환하고 문자열이 아니면 거부한다.

    저장 시 이스케이프/따옴표 처리는 JSON/CSV 계층, 화면 제어 문자 처리는 safe_text의 책임이다.
    """
    if not isinstance(value, str):
        raise ValidationError("메모는 문자열이어야 합니다.", "메모가 없다면 빈 문자열을 사용하세요.")
    return value


def validate_tags(value: tuple[str, ...]) -> tuple[str, ...]:
    """태그가 유효한 문자열의 중복 없는 튜플인지 검사해 같은 튜플을 반환한다.

    개별 태그의 쉼표는 CSV 태그 구분과 충돌하므로 금지한다. ("meal", "work")는
    허용하지만 ["meal"]은 모델용 타입이 아니므로 거부한다. 문자열은 parse_tags로 바꾼다.
    """
    if not isinstance(value, tuple):
        raise ValidationError("태그는 문자열 튜플이어야 합니다.", "쉼표 구분 입력은 parse_tags()로 변환하세요.")
    seen: set[str] = set()
    for tag in value:
        validate_label(tag, "태그")
        if "," in tag:
            raise ValidationError("개별 태그에 쉼표를 넣을 수 없습니다.", "쉼표는 태그 사이를 구분하는 데 사용하세요.")
        if tag in seen:
            raise ValidationError("중복 태그가 있습니다.", "같은 태그는 한 번만 지정하세요.")
        seen.add(tag)
    return value


def parse_tags(raw: str) -> tuple[str, ...]:
    """쉼표 구분 문자열을 정리해 입력 순서를 유지한 중복 없는 태그 튜플로 반환한다.

    각 조각의 앞뒤 공백을 제거하고 빈 항목·이미 본 항목을 건너뛴다.
    완성된 튜플은 validate_tags로 다시 검사하며 대소문자는 합치지 않는다.
    """
    if not isinstance(raw, str):
        raise ValidationError("태그 입력은 문자열이어야 합니다.", "예: meal,lunch. 태그가 없으면 엔터를 누르세요.")
    seen: set[str] = set()
    tags: list[str] = []
    for part in raw.split(","):
        tag = part.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return validate_tags(tuple(tags))
