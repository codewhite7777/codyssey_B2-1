# B2-1 — 나만의 용돈 기입장

**터미널에서 수입·지출을 기록하고, 파일에 저장한 내역을 조회·검색·수정·삭제하는 Python 프로그램입니다.** 월별 합계와 예산 사용률을 확인하고 CSV로 내역을 주고받습니다. 은행 계좌나 실제 결제에는 연결하지 않습니다.

이 저장소는 AI가 작성한 구현을 실행·검증하고, 학습자가 실제 코드의 흐름과 설계 이유를 이해하는 데 사용합니다. 실행 방법은 이 문서에서, 함수의 기능·처리 순서는 각 함수의 `docstring`에서, 파일 간 연결은 [코드 흐름 해설](docs/ARCHITECTURE.md)에서 확인합니다. AI 작성 여부와 관계없이 검증 기록과 구현의 한계를 구분합니다.

## 1. 실행 전에 알아둘 것

| 항목 | 내용 |
|---|---|
| 필요한 환경 | Python **3.10 이상**. Git으로 받을 때는 Git도 필요합니다. |
| 추가 설치 | 표준 라이브러리만 사용합니다. **`pip install`, API 키, 데이터베이스, 웹 서버가 필요하지 않습니다.** |
| 실행 위치 | `README.md`, `budget_app/`, `tests/`, `tools/`가 함께 있는 **저장소 루트 폴더**입니다. |
| 실행 방식 | 명령 하나를 처리하면 종료합니다. 상시 메뉴가 아니라 매번 `python3 -m budget_app 명령`으로 실행합니다. |
| 입력 방식 | `add`, `category add/remove`는 실행 후 질문에 답합니다. 조회·수정 등은 옵션으로 조건을 전달합니다. |
| 데이터 | 프로그램 종료 후에도 JSONL 파일에 남습니다. 서로 다른 `--data-dir`는 **서로 다른 가계부**입니다. |

아래 명령은 macOS/Linux 터미널의 `python3` 표기를 사용합니다. Windows에서는 설치된 Python 실행 명령에 맞춰 `py -3` 또는 `python`으로 바꿉니다. **Windows/macOS 실제 실행 검증은 아직 수행하지 않았습니다.**

### 처음 저장소를 받는 경우

```bash
git clone https://github.com/codewhite7777/codyssey_B2-1.git
cd codyssey_B2-1
python3 --version
python3 -m budget_app --help
```

Python 버전이 3.10 미만이면 실행 환경을 먼저 변경해야 합니다. ZIP으로 받았다면 압축을 풀고 `budget_app/`가 있는 폴더로 이동합니다. `budget_app/` 폴더 안으로 들어가서 실행하지 않습니다.

### 이미 저장소를 받은 경우

아래 명령은 기존 저장소 폴더에서 실행합니다. `git status --short`에 수정 파일이 표시되면 변경 내용을 먼저 확인하고 보관합니다. 로컬 변경을 버리는 명령은 사용하지 않습니다.

```bash
git status --short
git switch main
git pull --ff-only origin main
python3 -m budget_app --help
```

`-m budget_app`은 Python에게 패키지의 `__main__.py`를 실행하도록 지시합니다. 뒤의 `add`, `list` 등은 가계부 명령입니다. 앱 옵션은 `--help`, `--limit`처럼 두 하이픈을 씁니다. Python 자체의 `-m`과 혼동하지 않습니다. `python3 budget_app/cli.py` 같은 직접 파일 실행은 지원하는 실행 방법이 아닙니다.

## 2. 입력 없이 전체 동작을 먼저 보는 방법

```bash
python3 -m tools.demo
```

이 명령은 별도 CLI 프로세스로 카테고리 등록 → 거래 추가 → 예산·요약 → 검색 → 수정·삭제 → CSV 입출력을 시연합니다. **키보드로 값을 입력할 필요가 없습니다.**

임시 가계부를 만들었다가 정리하므로 개인 `./data`에 거래를 추가하지 않습니다. 실행 기록은 `reports/cli_demo.txt`에 남습니다. 일부 단계의 `[오류]`, `exit=1`, `exit=2`는 사용 중인 카테고리 삭제나 잘못된 CSV를 거부하는 **의도한 검증 결과**입니다. 각 단계의 실제 종료 코드가 예상값과 다르면 시연 도구가 실패합니다.

자동 시연은 기능 확인용입니다. 기록을 직접 남기려면 아래 과정을 사용합니다.

## 3. 직접 기록하기 — 처음부터 끝까지

이 절은 **아직 사용하지 않은 `./data/practice`**를 기준으로 합니다. 모든 명령에 같은 경로를 지정합니다. 이미 이 경로로 연습했다면 기존 내역을 확인하거나 새로운 연습 경로를 정해 모든 명령에 동일하게 사용합니다. 재실행은 초기화가 아닙니다.

### 3-1. 저장 폴더 초기화와 카테고리 등록

```bash
python3 -m budget_app --data-dir ./data/practice category list
```

처음에는 세 빈 저장 파일을 만들고 카테고리가 없다고 안내합니다. 기본 카테고리를 자동 등록하지 않습니다. 다음 명령을 실행하고 `카테고리명:` 질문에 **`salary`**를 입력합니다.

```bash
python3 -m budget_app --data-dir ./data/practice category add
```

같은 명령을 한 번 더 실행해 **`food`**를 등록합니다. 이미 등록한 이름을 다시 추가하면 중복 오류가 납니다. `category list`에서 두 이름을 확인할 수 있습니다.

### 3-2. 수입 한 건 추가

```bash
python3 -m budget_app --data-dir ./data/practice add
```

화면의 질문에 순서대로 아래 값을 입력합니다. 다음 블록은 **셸 명령이 아니라 대화형 입력 예시**입니다.

```text
날짜(YYYY-MM-DD): 2026-10-01
타입(income/expense): income
카테고리: salary
금액(양수 정수): 100000
메모(선택): 용돈
태그(쉼표 구분, 선택): monthly
```

### 3-3. 지출 한 건 추가

동일한 `add` 명령을 다시 실행해 다음 값을 입력합니다.

```text
날짜(YYYY-MM-DD): 2026-10-06
타입(income/expense): expense
카테고리: food
금액(양수 정수): 15000
메모(선택): 점심
태그(쉼표 구분, 선택): meal,lunch
```

지출도 금액은 양수입니다. 돈이 나갔다는 의미는 `expense`로 표현합니다. 잘못된 날짜·타입·카테고리·금액은 원인과 힌트를 보여 주고 해당 필드를 다시 입력받습니다. 메모·태그가 없으면 엔터를 누릅니다. 입력 도중 Ctrl+C로 취소하면 그 거래는 저장하지 않습니다.

저장 성공 시 `TX-`로 시작하는 고유 ID를 출력합니다. ID는 매번 달라집니다. 성공 후 셸 프롬프트로 돌아오는 것은 정상입니다.

### 3-4. 재조회와 예산·월별 요약

```bash
python3 -m budget_app --data-dir ./data/practice list --limit 5
python3 -m budget_app --data-dir ./data/practice budget set --month 2026-10 --amount 50000
python3 -m budget_app --data-dir ./data/practice summary --month 2026-10 --top 3
```

새 연습 가계부에 위 두 건만 입력했다면 다음 수치가 나옵니다.

```text
총 수입: 100,000원
총 지출: 15,000원
잔액: 85,000원
예산: 50,000원 (사용률 30.0%)
```

각 명령은 별도 실행입니다. 앞 명령의 메모리를 이어 쓰는 것이 아니라 같은 경로의 파일을 다시 읽습니다. 날짜는 입력한 거래 날짜이며 현재 날짜로 자동 변경하지 않습니다.

### 3-5. 검색·수정·삭제

```bash
python3 -m budget_app --data-dir ./data/practice search --category food --tag meal
```

출력에서 **지출 거래의 ID**를 복사합니다. 아래의 `목록에서_복사한_ID`를 그 ID로 바꿉니다. 이 문구를 그대로 실행하면 없는 거래 오류가 납니다.

```bash
python3 -m budget_app --data-dir ./data/practice update --id "목록에서_복사한_ID" --amount 55000
python3 -m budget_app --data-dir ./data/practice summary --month 2026-10
```

지출이 55,000원으로 바뀌고 사용률 **110.0%**, **5,000원 초과 경고**가 나옵니다. 원래 ID와 생략한 날짜·카테고리 등은 유지합니다.

```bash
python3 -m budget_app --data-dir ./data/practice delete --id "목록에서_복사한_ID"
python3 -m budget_app --data-dir ./data/practice list
```

지출만 사라지고 수입은 남습니다. 지출 삭제 전에는 `food` 카테고리 삭제가 막히고, 삭제 후에는 `category remove` 실행 시 `food`를 입력해 지울 수 있습니다. 없는 ID의 수정·삭제는 실패로 처리합니다.

**실제 개인 가계부**에는 `--data-dir`를 생략해 기본 `./data`를 사용하거나 별도 경로를 정합니다. 연습 경로와 실제 경로를 섞지 않습니다.

## 4. 전체 명령 참조

아래에서 `앱`은 `python3 -m budget_app --data-dir ./data/practice`를 줄여 쓴 **설명용 표기**입니다. 셸 명령 이름이 아닙니다. 모든 명령과 하위 명령에서 `--help`를 사용할 수 있습니다.

| 기능 | 명령 형태 | 입력·동작 |
|---|---|---|
| 추가 | `앱 add` | 날짜·타입·카테고리·금액·메모·태그 대화형 입력 |
| 목록 | `앱 list --limit 20` | 날짜 최신순, 기본 20건 |
| 검색 | `앱 search --from 2026-10-01 --to 2026-10-31 --category food --type expense --q 점심 --tag meal` | 지정한 모든 조건을 AND로 결합 |
| 요약 | `앱 summary --month 2026-10 --top 3` | 수입·지출·잔액·카테고리별 지출 TOP N, 기본 TOP 3 |
| 예산 | `앱 budget set --month 2026-10 --amount 50000` | 해당 월의 예산 추가·변경 |
| 예산 조회 | `앱 budget show --month 2026-10` | 없으면 미설정 안내 |
| 카테고리 | `앱 category add`, `앱 category list`, `앱 category remove` | 등록·조회·삭제, 사용하는 거래가 있으면 삭제 거부 |
| 수정 | `앱 update --id 실제ID --amount 20000` | **옵션 방식으로 고정**, 수정 필드 하나 이상 필요 |
| 삭제 | `앱 delete --id 실제ID` | 지정한 거래 삭제 |
| 가져오기 | `앱 import --from examples/sample_import.csv` | CSV 전체 검증 후 일괄 등록 |
| 내보내기 | `앱 export --out ./data/export.csv --month 2026-10` | 조건에 맞는 거래를 CSV로 저장 |

검색의 날짜 경계는 포함합니다. `search`는 시작일만 또는 종료일만 지정할 수 있습니다. 카테고리·타입·태그는 정확히 비교하고, 메모 `--q`는 대소문자를 구분하지 않는 부분 문자열 검색입니다. `search --limit`을 생략하면 모든 일치 결과를 출력합니다. 앱 옵션 축약(`--lim`)이나 단일 하이픈(`-limit`, `-h`)은 허용하지 않습니다.

수정 가능 필드는 `--date`, `--type`, `--category`, `--amount`, `--memo`, `--tags`입니다. **생략한 옵션은 기존 값 유지**, `--memo ""`, `--tags ""`는 **비우기**입니다. 날짜를 바꾸면 파일 내 정렬 위치도 조정합니다.

내보내기는 `--month YYYY-MM` 단독 또는 **`--from YYYY-MM-DD --to YYYY-MM-DD` 쌍** 중 하나를 필수로 받습니다. 조건 누락·혼용·역전된 기간은 오류입니다. 출력 폴더는 미리 있어야 하며, 기존 출력 파일은 성공 시 교체합니다. 결과가 없으면 헤더만 생성합니다.

## 5. CSV 가져오기·내보내기

### 스키마

CSV는 UTF-8 텍스트이며 헤더가 필수입니다. 입력은 UTF-8 BOM도 허용하고 출력은 BOM 없는 UTF-8입니다. 출력 열 순서는 다음 여섯 개로 고정합니다.

```csv
date,type,category,amount,memo,tags
2026-10-06,expense,food,15000,"점심, 커피","meal,lunch"
```

| 열 | 필수 | 값 |
|---|---|---|
| `date` | Y | 실제 존재하는 YYYY-MM-DD |
| `type` | Y | income / expense |
| `category` | Y | 미리 등록한 카테고리 이름 |
| `amount` | Y | 쉼표·통화 기호 없는 양수 정수 |
| `memo` | N | 문자열, 기본 빈 문자열 |
| `tags` | N | 쉼표로 구분한 태그 문자열, 기본 빈 문자열 |

입력 열 순서는 달라도 되며 선택 열은 생략할 수 있습니다. 헤더에 열이 있으면 빈 값도 구분 쉼표로 표현해야 합니다. 필수 열 누락·중복 열·알 수 없는 열·행의 열 개수 불일치는 오류입니다. 완전히 빈 물리 행은 무시합니다. 쉼표나 개행이 있는 필드를 큰따옴표로 묶는 처리는 표준 `csv` 모듈에 맡깁니다. **CSV 전체 행에 `split(',')`를 적용하지 않습니다.**

### 제공 CSV로 확인하기

직접 입력한 가계부와 섞이지 않도록 **새 `./data/csv-practice`**를 사용합니다. 다음 명령을 세 번 실행해 `salary`, `food`, `transport`를 각각 등록합니다.

```bash
python3 -m budget_app --data-dir ./data/csv-practice category add
```

그다음 실행합니다.

```bash
python3 -m budget_app --data-dir ./data/csv-practice import --from examples/sample_import.csv
python3 -m budget_app --data-dir ./data/csv-practice summary --month 2026-10
python3 -m budget_app --data-dir ./data/csv-practice export --out ./data/csv-export.csv --month 2026-10
```

새 가계부라면 `imported=3, skipped=0`, 수입 100,000원·지출 17,000원·잔액 83,000원, 내보내기 3건을 확인할 수 있습니다.

```bash
python3 -m budget_app --data-dir ./data/csv-practice import --from examples/invalid_import.csv
```

금액 0인 행 때문에 `imported=0 (전체 미반영)` 오류가 납니다. 기존 거래 파일은 그대로입니다. 일부 행만 저장하는 정책이 아닙니다. 오류 위치는 CSV 레코드가 끝나는 물리 행 기준입니다. 처음 접근한 빈 저장소에서는 검증 실패 전 초기 파일 세 개가 생성될 수 있지만 거래는 반영하지 않습니다.

**같은 CSV를 재가져오면 내용도 다시 추가됩니다.** 가져올 때 새 ID를 만들며 내용 중복은 제거하지 않습니다. CSV에는 ID·카테고리 목록·예산이 모두 담기지 않으므로 원본 가계부의 완전한 백업이 아닙니다. 신뢰하지 않는 CSV를 스프레드시트로 열 때는 메모의 수식 자동 해석에 주의합니다.

## 6. 저장 위치와 데이터 구조

```text
저장소 루트/
├── budget_app/          프로그램 소스
├── tests/               자동 테스트
├── tools/               시연·검증 도구
├── examples/            정상·오류 CSV 예제
├── docs/                구조·평가·검토 설명
├── reports/             테스트·시연 기록
└── data/                실행 시 생성, Git 추적 제외
    ├── transactions.jsonl
    ├── categories.jsonl
    ├── budgets.jsonl
    └── practice/        --data-dir ./data/practice를 쓴 경우의 별도 세 파일
```

위 트리의 기본 경로 세 파일은 기본 가계부를 사용할 때 생성됩니다. 연습 경로만 사용했다면 세 파일은 그 하위 폴더에만 있습니다.

기본 `./data`는 **현재 작업 폴더 기준**입니다. 이 README의 명령은 항상 저장소 루트에서 실행합니다. 데이터가 사라진 것처럼 보이면 파일 삭제보다 먼저 작업 폴더와 `--data-dir`를 확인합니다. `reports/`는 거래 데이터가 아닙니다.

JSONL은 한 물리 줄에 JSON 객체 하나를 기록하는 형식입니다. 파일은 프로그램이 생성하고 변경합니다. 다음은 **데이터 모양 설명**이며 직접 파일에 붙여 넣으라는 지시가 아닙니다.

```text
transactions.jsonl:
{"id":"TX-예시ID","type":"expense","date":"2026-10-06","amount":15000,"category":"food","memo":"점심","tags":["meal","lunch"]}

categories.jsonl:
{"name":"food"}

budgets.jsonl:
{"month":"2026-10","amount":50000}
```

거래의 필수 필드는 `id/type/date/amount/category`입니다. `memo`와 `tags`는 선택이며 생략하면 각각 `""`, `[]`로 해석합니다. 금액·예산은 양수 정수이고 `bool`, 0, 음수, 소수를 거부합니다. ID 유일성과 등록된 카테고리는 저장 상태와 대조합니다. tags는 입력·CSV에서는 쉼표 문자열, Python 모델에서는 튜플, JSONL에서는 배열입니다.

처음 데이터에 접근할 때 폴더와 세 파일을 만듭니다. `--help`는 만들지 않습니다. 기존 파일에 내용이 있는데 일부 파일이 없으면 유실 가능성으로 중단합니다. 저장 파일의 빈 줄·손상 JSON·잘못된 값은 자동으로 건너뛰거나 삭제하지 않습니다.

원본 백업은 앱 작업이 없을 때 **JSONL 세 파일을 함께 복사**합니다. 내부 저장 파일·잠금 파일 또는 그 하드링크를 CSV 경로로 지정할 수 없고, CSV 파일 경로 자체가 심볼릭 링크인 경우도 거부합니다. 임의의 외부 편집기 수정까지 방지하는 기능은 아닙니다.

## 7. 코드 전체 흐름과 읽는 순서

```text
python3 -m budget_app add
  → __main__.py: main() 호출
  → decorators.py: 오류를 처리하는 wrapped 안에서 실제 main 실행
  → cli.py: 명령 해석, 사용자 입력, 문자열 변환
  → service.py: 등록 카테고리·ID 등 업무 규칙 검사
  → models.py / validators.py: 거래 구조와 값 검증
  → storage.py: 임시 파일 작성 후 원본 교체
  → cli.py: 저장 ID 출력
  → __main__.py: 반환 코드를 프로세스 종료 코드로 전달
```

이는 주요 호출 경로입니다. 모든 명령이 똑같은 함수들을 순서대로 호출하는 것은 아닙니다. 목록·검색은 파일을 한 건씩 읽는 경로를, 요약은 집계 경로를, CSV는 `csv_io.py`를 함께 사용합니다.

| 순서 | 실제 파일 | 읽을 핵심 |
|---|---|---|
| 1 | [__main__.py](budget_app/__main__.py) | 어디서 시작하고 왜 `SystemExit(main())`로 끝나는가 |
| 2 | [cli.py](budget_app/cli.py) | `main`, `build_parser`, `prompt`, `_add`, 출력 함수의 연결 |
| 3 | [models.py](budget_app/models.py), [validators.py](budget_app/validators.py) | 입력 `"15000"`을 정수 `15000`으로 바꾸고 거래를 검증하는 과정 |
| 4 | [service.py](budget_app/service.py) | add/search/update/delete/summary의 업무 규칙과 호출 흐름 |
| 5 | [storage.py](budget_app/storage.py) | JSONL 한 줄 읽기, 잠금, 안전한 재작성 |
| 6 | [csv_io.py](budget_app/csv_io.py) | CSV 변환과 전체 검증 후 반영 |
| 7 | [errors.py](budget_app/errors.py), [decorators.py](budget_app/decorators.py) | 예외를 원인·힌트·종료 코드로 바꾸는 과정 |
| 8 | [tests/](tests/) | 정상·실패 입력이 해당 동작을 어떻게 증명하는가 |

파일은 위에서 아래로 읽되 **함수 정의 순서와 실제 실행 순서는 구분**합니다. `def`를 만났다고 함수 본문을 즉시 실행하지 않습니다. 각 파일 상단에 역할·연결 경로를 적고, 함수 바로 아래에 기능·입출력·처리 순서·주의사항을, 중요한 분기에는 선택 이유를 주석으로 적었습니다.

[코드 흐름 해설](docs/ARCHITECTURE.md)은 한 거래의 입력·저장·재조회와 제너레이터의 지연 실행을 작은 예제로 연결합니다. [명세 대응표](docs/REQUIREMENTS_MATRIX.md)는 제공된 요구사항과 구현을 연결합니다.

## 8. 검증 방법과 결과 확인

전체 단위·통합 테스트:

```bash
python3 -m unittest discover -s tests -v
```

실제 CLI 하위 프로세스 통합 테스트만 실행:

```bash
python3 -m unittest tests.test_cli.CLISubprocessTests -v
```

이 README의 직접 입력·CSV 사용 순서를 검사:

```bash
python3 -m unittest tests.test_readme_workflows -v
```

결과 파일까지 생성하거나 외부 site 패키지 로딩을 끄고 실행:

```bash
python3 -m tools.run_tests
python3 -S -m unittest discover -s tests -v
```

테스트는 임시 저장소를 사용합니다. `tools.run_tests`는 `reports/test_results.json`과 `reports/unit_test_log.txt`를 갱신하므로 Git에서 보고서 수정이 보일 수 있습니다. 일반 사용에 `-S`는 필요하지 않습니다. 테스트 수·실행 환경·실패/오류/건너뜀 수는 **현재 [결과 JSON](reports/test_results.json)**을 확인합니다. 테스트 통과를 코드 전체의 무결함이나 피어 평가 합격 보장으로 해석하지 않습니다.

이번 문서 개선의 검증 범위는 [문서 개선 검토 기록](docs/DOCUMENTATION_REVIEW.md)에 정리했습니다. 이전 날짜의 검토·성능 보고서는 당시의 기록이며 최신 실행 결과가 아닙니다. Python 3.10 AST 검사는 해당 문법을 해석한 것이지 Python 3.10 인터프리터 실행이나 정적 타입 검사와 같지 않습니다.

## 9. 실행 중 막히는 지점

| 증상 | 확인·해결 방법 |
|---|---|
| `No module named budget_app` | 저장소 루트인지, `budget_app/`가 실제로 있는지 확인합니다. |
| 상대 import 오류 | `python3 budget_app/cli.py` 대신 루트에서 `python3 -m budget_app ...`를 실행합니다. |
| 명령을 안 주면 사용법 오류 | `--help`, `list`, `add` 같은 명령/옵션을 함께 지정합니다. |
| 카테고리가 없어 add가 종료 | 같은 `--data-dir`로 `category add`를 먼저 실행합니다. |
| 프로그램이 바로 종료 | 명령 하나가 끝나면 종료하는 방식입니다. 다음 명령을 새로 입력합니다. |
| 이전 기록이 안 보임 | 작업 폴더와 `--data-dir`, 조회 월·조건·limit을 먼저 확인합니다. |
| CSV 미등록 카테고리 오류 | CSV에 등장하는 이름을 같은 저장소에 먼저 등록합니다. |
| CSV `imported=0` | 첫 오류의 행과 원인을 수정합니다. 기존 거래를 지우거나 부분 성공으로 추측하지 않습니다. |
| 잠금 충돌 | 다른 가계부 작업 종료 후 재시도합니다. 강제 종료였다면 실행 중인 가계부 프로세스가 없는지 확인한 뒤 해당 폴더의 `.budget_app.lock`만 제거합니다. |
| 저장 파일 일부 없음·손상 | 자동 초기화하거나 빈 파일을 덮어쓰지 말고 세 파일의 백업을 확인합니다. |
| 내보내기 경로 오류 | 상위 폴더 존재, 쓰기 권한, 여유 공간, 내부 저장 파일과 다른 경로인지 확인합니다. |

오류는 보통 stderr에 원인과 해결 힌트를 출력합니다. 정상 결과는 stdout입니다. 닫힌 출력 파이프는 출력 자체를 할 수 없어 코드 1로 종료하는 별도 처리입니다.

| 종료 코드 | 의미 |
|---:|---|
| 0 | 성공, 또는 데이터 없음·예산 미설정의 정상 조회 |
| 1 | 없는 거래, 중복/사용 중 카테고리, 잠금·저장·출력 오류 등 |
| 2 | 사용법·입력값·CSV 검증 오류 |
| 130 | EOF 또는 Ctrl+C 입력 취소 |

대화형 오류를 고쳐 정상 저장하면 최종 코드는 0입니다. 종료 직후 macOS/Linux에서는 `echo $?`, PowerShell에서는 `$LASTEXITCODE`로 확인합니다. 다른 명령을 먼저 실행하면 그 명령의 코드로 바뀝니다. 코드를 AI에 수정 요청할 때는 실행 명령·실행 위치·입력·오류·코드를 함께 전달하되 개인 거래 내용은 제거합니다.

## 10. 설계 선택과 한계

조회는 이미 `(date, id)` 내림차순인 거래 파일을 한 건씩 읽습니다. 같은 날짜의 ID 순서는 등록 시각순이 아닙니다. limit 이후 읽지 않은 행의 손상은 그 조회로 발견하지 못할 수 있습니다. 카테고리 목록은 메모리에 올립니다.

추가·수정·삭제는 전체 거래 검사·파일 재작성이 필요하고 ID 집합은 거래 수에 비례한 메모리를 씁니다. CSV 가져오기는 모든 신규 거래를 검증·정렬하므로 전체가 상수 메모리가 아닙니다. 이 비용을 줄이는 월별 분할·색인은 개선 가능성이지 구현된 기능이 아닙니다.

잠금은 협력하는 앱 작업끼리 충돌을 막고, 임시 파일과 `os.replace`는 완성되지 않은 중간 파일로 원본을 덮어쓰지 않도록 합니다. 여러 파일 동시 커밋·정전 내구성·외부 편집기 변경·자동 잠금 복구까지 보장하지 않습니다. 저장 완료 후 화면 출력이 실패하면 이미 저장된 결과를 자동 롤백하지 않습니다.

선택 보너스인 자동 backup 명령·반복 거래 생성·정교한 표 너비 정렬은 구현하지 않았습니다. GitHub Actions 자동 실행도 이번 작업에 추가하지 않았습니다. 필수 명세·선택 정책·사용자의 문서 품질 요구를 구분하고, 제공되지 않은 배점이나 합격선을 만들지 않습니다.

### 관련 공식 문서

- [Python의 -m 실행](https://docs.python.org/3.10/using/cmdline.html#cmdoption-m), [__main__](https://docs.python.org/3.10/library/__main__.html)
- [dataclasses](https://docs.python.org/3.10/library/dataclasses.html), [typing](https://docs.python.org/3.10/library/typing.html)
- [contextlib](https://docs.python.org/3.10/library/contextlib.html), [csv](https://docs.python.org/3.10/library/csv.html), [JSON Lines](https://jsonlines.org/)
- [PEP 257 — docstring 작성 규칙](https://peps.python.org/pep-0257/)
