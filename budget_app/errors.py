"""사용자에게 보여줄 오류 = 원인(message) + 해결 힌트(hint)."""

import sys


class AppError(Exception):
    """예상한 오류. 스택트레이스 대신 [오류]/[힌트] 두 줄로 출력된다."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


def show_error(error: AppError) -> None:
    """오류를 [오류] + [힌트] 형식으로 출력한다."""
    print(f"[오류] {error}", file=sys.stderr)
    if error.hint:
        print(f"[힌트] {error.hint}", file=sys.stderr)
