"""값 자체의 규칙을 검증한다. 파일을 읽거나 input()/print()하지 않는다."""

import re
from datetime import date as Date
from typing import Literal

from .errors import ValidationError

TransactionType = Literal["income", "expense"]


def validate_date(value: str) -> str:
    """정확한 YYYY-MM-DD 모양과 실제로 존재하는 날짜를 모두 검사한다."""
    hint = "실제로 존재하는 날짜를 YYYY-MM-DD 형식으로 입력하세요. 예: 2026-10-06"
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValidationError("날짜 형식이 올바르지 않습니다.", hint)
    try:
        Date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError("존재하지 않는 날짜입니다.", hint) from exc
    return value


def validate_month(value: str) -> str:
    """예산/요약에 사용할 YYYY-MM을 검사한다."""
    hint = "월을 YYYY-MM 형식으로 입력하세요. 예: 2026-10"
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}", value) is None:
        raise ValidationError("월 형식이 올바르지 않습니다.", hint)
    try:
        Date.fromisoformat(f"{value}-01")
    except ValueError as exc:
        raise ValidationError("존재하지 않는 연도 또는 월입니다.", hint) from exc
    return value


def validate_amount(value: int) -> int:
    """금액은 양수 정수다. bool은 int의 하위 타입이므로 명시적으로 거부한다."""
    if type(value) is not int or value <= 0:
        raise ValidationError("금액은 0보다 큰 정수여야 합니다.", "예: 15000. 0, 음수, 소수는 사용할 수 없습니다.")
    return value


def parse_amount(raw: str) -> int:
    """CLI/CSV에서 받은 문자열을 검증된 정수로 변환한다."""
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
    """타입 힌트와 별개로, 실제 값이 허용된 두 문자열인지 검사한다."""
    if value == "income":
        return "income"
    if value == "expense":
        return "expense"
    raise ValidationError("허용되지 않은 거래 타입입니다.", "income 또는 expense를 입력하세요.")


def validate_label(value: str, field_name: str) -> str:
    """id/카테고리/태그의 공통 문자열 규칙. 정규화 대신 잘못된 값을 거부한다."""
    hint = f"{field_name}에 앞뒤 공백과 제어 문자가 없는, 비어 있지 않은 문자열을 사용하세요."
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValidationError(f"{field_name}이(가) 올바르지 않습니다.", hint)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValidationError(f"{field_name}에 제어 문자가 있습니다.", hint)
    return value


def validate_category_name(value: str) -> str:
    """이름 형식만 검사한다. 등록 여부는 나중에 서비스가 저장소와 대조한다."""
    return validate_label(value, "카테고리")


def validate_memo(value: str) -> str:
    """빈 문자열을 허용한다. 쉼표/줄바꿈은 직렬화 계층에서 올바르게 인코딩한다."""
    if not isinstance(value, str):
        raise ValidationError("메모는 문자열이어야 합니다.", "메모가 없다면 빈 문자열을 사용하세요.")
    return value


def validate_tags(value: tuple[str, ...]) -> tuple[str, ...]:
    """수정 불가능한 튜플을 사용하며, 쉼표가 들어간 개별 태그는 금지한다."""
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
