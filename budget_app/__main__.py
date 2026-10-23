"""python -m budget_app 으로 실행할 때의 입구. 명령의 결과(0/1)를 종료 코드로 넘긴다."""

import sys

from .cli import main

sys.exit(main())
