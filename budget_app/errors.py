"""계층 간에 원인과 해결 힌트를 전달한다. 화면 출력은 CLI 경계의 책임이다."""


class AppError(Exception):
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
