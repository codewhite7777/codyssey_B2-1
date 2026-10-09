"""python -m budget_app의 진입점. 함수 결과를 실제 프로세스 종료 코드로 전달한다."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
