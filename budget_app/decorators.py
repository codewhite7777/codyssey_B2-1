"""명령 실행 전체의 오류 처리와 출력 안전성을 공통으로 제공한다.

cli.main에 @handle_cli_errors를 붙이면 원래 main을 wrapped가 감싸게 된다.
wrapped → main의 입력·서비스 호출·제너레이터 순회·출력 → 정상 0 또는 오류 코드.
여기서 반환한 코드는 __main__.py의 SystemExit를 거쳐 실제 프로세스 종료 코드가 된다.

재입력이 가능한 ValidationError는 cli.prompt가 먼저 처리한다.
이 경계까지 올라온 오류는 명령을 종료한다. 데이터 변경을 되돌리는 롤백 함수는 아니다.
"""

import sys
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec

from .errors import AppError

# 감싸기 전 함수의 인자 모양을 보존하는 타입 표기다. 오류 처리와 입력 검증은 별도의 코드다.
P = ParamSpec("P")


def safe_text(value: object) -> str:
    """데이터를 문자열로 바꾸고 터미널 제어 문자를 눈에 보이는 표기로 치환한다.

    줄바꿈·탭 등으로 출력 행이 깨지지 않게 하며, 저장된 원문 자체는 바꾸지 않는다.
    """
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
    """원인과 해결 힌트를 안전한 문자열로 바꾸어 stderr에 두 줄로 출력한다.

    데이터 조회 결과인 stdout과 오류 안내를 분리한다. 프로세스 종료는 하지 않는다.
    """
    print(f"[오류] {safe_text(message)}", file=sys.stderr)
    print(f"[힌트] {safe_text(hint)}", file=sys.stderr)


def handle_cli_errors(function: Callable[P, int]) -> Callable[P, int]:
    """CLI 함수의 예외를 사용자 안내와 정수 종료 코드로 변환하는 함수를 반환한다.

    wraps로 원래 함수의 이름·문서·타입 힌트를 보존한다.
    실제 명령 실행 전체에 적용해야 제너레이터 순회 중 오류까지 처리할 수 있다.
    """
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> int:
        """원래 함수를 실행하고 오류 종류에 맞는 안내와 종료 코드를 반환한다.

        업무 오류·입력 취소·출력 파이프 종료·파일 오류를 구분한다.
        예상 밖 오류도 성공으로 숨기지 않는다. 이미 저장된 결과를 자동으로 되돌리지는 않는다.
        """
        try:
            return function(*args, **kwargs)
        # 알려진 업무 오류는 오류 객체가 가진 원인·힌트·종료 코드를 그대로 사용한다.
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
            show_error(
                f"예상하지 못한 오류가 발생했습니다 ({type(exc).__name__}).",
                "성공 여부를 단정하지 말고 저장 파일을 확인하세요. "
                "재현 명령과 입력을 개발자에게 전달하세요.",
            )
            return 1
    return wrapped
