"""공통 관심사(오류 처리 · 종료 코드)를 명령 함수 밖으로 빼낸 데코레이터."""

import functools
import sys
from collections.abc import Callable
from typing import Any

from .errors import AppError, show_error


def handle_errors(func: Callable[..., None]) -> Callable[..., int]:
    """명령 함수를 감싸서: 성공하면 0, 오류면 [오류]+[힌트]를 출력하고 1을 돌려준다."""

    @functools.wraps(func)                    # 감싼 뒤에도 원래 함수 이름·설명 유지
    def wrapper(*args: Any, **kwargs: Any) -> int:
        try:
            func(*args, **kwargs)
            return 0
        except AppError as e:                 # 예상한 오류: 원인 + 힌트
            show_error(e)
            return 1
        except (EOFError, KeyboardInterrupt):  # 입력 도중 Ctrl+D / Ctrl+C
            print("\n[중단] 입력을 취소했습니다. 아무것도 저장하지 않았습니다.", file=sys.stderr)
            return 1
        except Exception as e:                # 예상 못한 오류도 스택트레이스 대신 안내
            show_error(AppError(f"예상하지 못한 문제가 발생했습니다 ({type(e).__name__}).",
                                "입력값과 data 폴더의 파일을 확인하세요."))
            return 1

    return wrapper
