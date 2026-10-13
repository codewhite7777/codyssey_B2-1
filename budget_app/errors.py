"""계층 사이에서 원인·해결 힌트·종료 코드를 전달하는 애플리케이션 오류들.

검증/서비스/저장소는 오류를 raise하고, CLI 경계의 데코레이터가 사용자에게 출력한다.
ValidationError 계열은 입력·사용법 오류(2), 다른 AppError 계열은 작업 실패(1)다.
예: 없는 거래 → NotFoundError → show_error → main의 반환값 1 → SystemExit(1).
파일 접근 자체에서 발생하는 OSError는 데코레이터가 따로 처리할 수도 있다.
"""


class AppError(Exception):
    """원인과 해결 힌트가 있는 오류의 공통 부모. 직접 print나 프로세스 종료를 하지 않는다."""

    exit_code = 1

    def __init__(self, message: str, hint: str) -> None:
        """오류 원인과 해결 힌트를 저장하여 CLI 계층에 전달한다.

        Exception의 메시지도 초기화하되 직접 출력하지 않는다.
        하위 클래스의 exit_code를 데코레이터가 실제 종료 결과로 사용한다.
        """
        super().__init__(message)
        self.message = message
        self.hint = hint


class ValidationError(AppError):
    """입력값 또는 조건을 고쳐야 하는 오류. 대화형 입력에서는 재입력에 사용할 수 있다."""

    exit_code = 2


class UsageError(ValidationError):
    """명령 사용법 오류."""


class NotFoundError(AppError):
    """지정한 저장 데이터가 없음."""


class ConflictError(AppError):
    """중복, 사용 중인 카테고리, 다른 프로세스의 접근."""


class StorageError(AppError):
    """저장 파일 손상 또는 파일 시스템 오류."""


class ImportDataError(ValidationError):
    """CSV 전체 가져오기를 취소해야 하는 입력 오류."""
