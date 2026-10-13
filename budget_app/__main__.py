"""터미널 명령을 가계부에 연결하고 최종 종료 코드를 운영체제에 전달한다.

읽기 순서: 이 파일 → cli.main → 해당 BudgetService 메서드 → storage의 파일 작업.
실행 방법: 저장소 루트에서 `python3 -m budget_app --help` 또는 `... add`.
`python3 budget_app/__main__.py`처럼 파일을 직접 실행하지 않는다.
-m은 패키지 안에서 실행하므로 아래 상대 import의 점(.)이 budget_app을 가리킨다.
명령 하나를 처리하면 종료한다. 계속 실행되는 메뉴나 웹 서버가 아니다.
"""

# 함수 정의를 가져온다. 실제 명령을 처리하는 호출은 아래 main()이다.
from .cli import main

if __name__ == "__main__":
    # main의 정상 반환값은 0이다. 오류는 데코레이터가 1/2/130 등으로 바꾼다.
    # 정수를 반환하는 것만으로는 프로세스 상태가 바뀌지 않으므로 SystemExit에 전달한다.
    raise SystemExit(main())
