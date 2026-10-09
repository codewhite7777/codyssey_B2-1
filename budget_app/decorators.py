"""CLI 실행 경계에서 예외를 메시지와 종료 코드로 변환하는 공통 데코레이터."""

import sys
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec

from .errors import AppError

P = ParamSpec("P")


def safe_text(value: object) -> str:
    """터미널 제어 문자와 여러 줄 입력이 출력 레이아웃을 바꾸지 않도록 표현한다."""
    result: list[str] = []
    for character in str(value):
        if character == "\n":
            result.append("\\n")
        elif character == "\r":
            result.append("\\r")
        elif character == "\t":
            result.append("\\t")
        elif ord(character) < 32 or 127 <= ord(character) < 160:
            result.append(f"\\x{ord(character):02x}")
        else:
            result.append(character)
    return "".join(result)


def show_error(message: str, hint: str) -> None:
    print(f"[오류] {safe_text(message)}", file=sys.stderr)
    print(f"[힌트] {safe_text(hint)}", file=sys.stderr)


def handle_cli_errors(function: Callable[P, int]) -> Callable[P, int]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            return function(*args, **kwargs)
        except AppError as exc:
            show_error(exc.message, exc.hint)
            return exc.exit_code
        except (EOFError, KeyboardInterrupt):
            show_error("입력이 취소되었습니다.", "입력을 완료하거나 명령을 다시 실행하세요.")
            return 130
        except BrokenPipeError:
            # head 등으로 출력이 끊긴 경우 종료 시 stdout 재flush가 추가 오류를 내지 않게 한다.
            try:
                sys.stdout.close()
            except OSError:
                pass
            return 1
        except (OSError, UnicodeError) as exc:
            show_error(f"파일/출력 처리에 실패했습니다: {exc}", "경로, 읽기/쓰기 권한, 남은 디스크 공간, UTF-8 인코딩을 확인하세요.")
            return 1
        except Exception as exc:
            # 예상 밖 구현 오류도 성공으로 숨기지 않는다. 테스트에서 함수 직접 호출로 원인을 추적한다.
            show_error(f"예상하지 못한 오류가 발생했습니다 ({type(exc).__name__}).", "성공 여부를 단정하지 말고 저장 파일을 확인하세요. 재현 명령과 입력을 개발자에게 전달하세요.")
            return 1
    return wrapped
