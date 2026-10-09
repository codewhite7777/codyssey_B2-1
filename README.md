# B2-1 — 나만의 용돈 기입장

Python으로 수입·지출을 기록하고 조회·검색·수정·삭제·월별 요약을 수행하는 콘솔 프로그램입니다. 내부 저장은 **JSONL 3개 파일**, 가져오기·내보내기는 **CSV**를 사용합니다. Python 표준 라이브러리만 사용하며 `pip install`은 필요하지 않습니다.

> **2026-10-09 원격 반영 상태: 소스 업로드 미완료.**
> 이 README는 대화에서 제공한 전체 구현본을 기준으로 작성했습니다. 해당 구현본의 테스트 175개는 Linux / Python 3.13.5에서 재실행해 통과했지만, GitHub 소스 업로드 요청은 도구의 보안 상태 확인 단계에서 차단됐습니다. README 등록만으로 소스 반영이나 과제 제출 완료를 뜻하지 않습니다. 아래 명령은 `budget_app/`, `tests/`, `tools/`가 있는 전체 구현본 폴더에서 실행해야 합니다. GitHub에서 다시 받은 전체 소스의 검증은 아직 하지 못했습니다.

## 1. 실행과 테스트

Python 3.10 이상이 필요합니다. 전체 구현본의 README가 있는 폴더에서 실행합니다. 압축본 폴더명은 `B2-1_budget_app`, 저장소명은 `codyssey_B2-1`입니다.

```bash
python3 --version
python3 -m budget_app --help
python3 -m budget_app category add
```

카테고리명에 `food`를 입력합니다. 같은 방법으로 `salary`, `transport` 등을 등록합니다. 기본 카테고리는 자동 생성하지 않으며, 등록된 카테고리가 없으면 `add`가 등록 방법을 안내하고 종료합니다.

```bash
python3 -m budget_app add
```

```text
날짜(YYYY-MM-DD): 2026-10-06
타입(income/expense): expense
카테고리: food
금액(양수 정수): 15000
메모(선택): 점심
태그(쉼표 구분, 선택): meal,lunch
```

저장 후 `TX-`로 시작하는 고유 ID를 출력합니다. 아래 명령의 `<id>`는 그 실제 ID로 바꾸며, 꺾쇠를 그대로 입력하지 않습니다. Windows에서는 설치 환경에 따라 `python3` 대신 `py -3` 또는 `python`을 사용합니다.

```bash
python3 -m unittest discover -s tests -v
python3 -S -m unittest discover -s tests -v
python3 -m tools.run_tests
python3 -m tools.demo
```

테스트와 시연은 임시 저장소를 사용하므로 개인 `./data`를 수정하지 않습니다. `tools.run_tests`는 `reports/test_results.json`과 `reports/unit_test_log.txt`를, `tools.demo`는 `reports/cli_demo.txt`를 생성합니다. `-S` 검증은 외부 site 패키지를 로딩하지 않은 실행이며, 일반 사용에 필수인 옵션은 아닙니다.

## 2. 명령어

모든 명령과 하위 명령은 `--help`를 지원합니다. 옵션은 `--`로 통일하며 `-h`, `-limit`, `--lim` 같은 축약은 허용하지 않습니다.

| 기능 | 명령 예 | 동작 |
|---|---|---|
| 거래 추가 | `python3 -m budget_app add` | 필드를 대화형 입력하고 ID 출력 |
| 목록 | `python3 -m budget_app list --limit 20` | 최신순, 기본 20건 |
| 검색 | `python3 -m budget_app search --category food --type expense --q 점심 --tag meal` | 모든 조건을 AND로 결합 |
| 기간 검색 | `python3 -m budget_app search --from 2026-10-01 --to 2026-10-31` | 두 경계 모두 포함 |
| 월별 요약 | `python3 -m budget_app summary --month 2026-10 --top 3` | 수입·지출·잔액·카테고리별 지출 TOP N |
| 예산 설정 | `python3 -m budget_app budget set --month 2026-10 --amount 50000` | 같은 월은 금액 변경 |
| 예산 조회 | `python3 -m budget_app budget show --month 2026-10` | 미설정이면 안내 |
| 카테고리 등록 | `python3 -m budget_app category add` | 이름을 대화형 입력 |
| 카테고리 목록 | `python3 -m budget_app category list` | 이름 오름차순 |
| 카테고리 삭제 | `python3 -m budget_app category remove` | 사용 중인 카테고리는 삭제 차단 |
| 거래 수정 | `python3 -m budget_app update --id <id> --amount 20000` | 옵션 방식으로 고정 |
| 거래 삭제 | `python3 -m budget_app delete --id <id>` | 없는 ID는 오류 |
| CSV 가져오기 | `python3 -m budget_app import --from examples/sample_import.csv` | 전체 검증 후 일괄 반영 |
| 월 CSV 내보내기 | `python3 -m budget_app export --out export.csv --month 2026-10` | UTF-8, 헤더 포함 |
| 기간 CSV 내보내기 | `python3 -m budget_app export --out export.csv --from 2026-10-01 --to 2026-10-31` | 시작일·종료일 쌍 필수 |

검색은 한쪽 날짜만 지정하는 열린 기간도 지원합니다. 카테고리·타입·태그는 정확히 일치해야 하며, 메모는 대소문자를 구분하지 않는 부분 문자열 검색입니다. 검색의 `--limit`은 선택이고 생략하면 일치하는 모든 결과를 출력합니다.

내보내기는 `--month` 또는 완전한 `--from`/`--to` 쌍 중 정확히 한 방식만 허용합니다. 조건이 없거나 두 방식을 섞으면 오류입니다. 결과가 0건이면 헤더만 생성합니다. 출력 폴더는 미리 있어야 하며, 기존 CSV는 성공 시 교체됩니다.

### 수정 정책

수정 필드는 `--date`, `--type`, `--category`, `--amount`, `--memo`, `--tags`이며 하나 이상 지정해야 합니다. 생략한 필드는 유지하고 ID 자체는 바꾸지 않습니다. 날짜를 바꾸면 정렬 위치도 다시 맞춥니다.

```bash
python3 -m budget_app update --id <id> --date 2026-10-07 --amount 18000 --tags meal,work
python3 -m budget_app update --id <id> --memo "" --tags ""
```

두 번째 명령은 메모와 태그를 비웁니다.

## 3. 저장 위치와 JSONL 스키마

기본 경로는 현재 작업 폴더 기준 `./data`입니다. `--data-dir`로 변경할 수 있습니다.

```bash
python3 -m budget_app --data-dir ./my_data list
python3 -m budget_app category list --data-dir ./my_data
```

```text
data/
├── transactions.jsonl
├── categories.jsonl
└── budgets.jsonl
```

최초 데이터 접근 시 폴더와 세 파일을 생성합니다. `--help`는 데이터를 만들지 않습니다. 기존 데이터가 비어 있지 않은데 일부 저장 파일이 없어졌다면 유실 가능성으로 보고 중단합니다. 기존 데이터가 없는 초기화 도중 누락된 빈 파일만 자동 생성합니다.

각 파일은 UTF-8이고 물리적 한 줄에 JSON 객체 하나를 저장합니다. 빈 줄, 중복 JSON 키, 예상 밖 필드, 잘못된 데이터는 손상으로 처리합니다.

거래 예:

```json
{"id":"TX-0123456789abcdef0123456789abcdef","type":"expense","date":"2026-10-06","amount":15000,"category":"food","memo":"점심","tags":["meal","lunch"]}
```

| 거래 필드 | 규칙 |
|---|---|
| `id` | 유일한 문자열, UUID 기반 생성 후 기존 ID와 충돌 검사 |
| `type` | `income` 또는 `expense` |
| `date` | 실제 존재하는 `YYYY-MM-DD` |
| `amount` | 양수 정수, 0·음수·소수·bool 불가 |
| `category` | 등록된 카테고리 |
| `memo` | 선택 문자열, 기본 빈 문자열 |
| `tags` | 선택 문자열 배열, 기본 빈 배열 |

카테고리 예:

```json
{"name":"food"}
{"name":"salary"}
```

예산 예:

```json
{"month":"2026-10","amount":50000}
```

예산도 양수 정수이며 같은 월은 하나만 저장합니다. 잔액은 기록된 수입-지출로, 실제 계좌 잔액과 연결하지 않습니다. 예산 사용률은 지출/예산×100이고 소수 첫째 자리까지 표시합니다. 지출이 예산보다 클 때만 초과 경고를 출력합니다.

## 4. CSV 스키마와 실패 정책

입력은 UTF-8이며 BOM도 허용합니다. 출력은 BOM 없는 UTF-8입니다. 헤더는 필수이고 출력 열 순서는 아래 여섯 개로 고정합니다.

```csv
date,type,category,amount,memo,tags
2026-10-01,income,salary,100000,용돈,monthly
2026-10-06,expense,food,15000,"점심, 커피","meal,lunch"
```

| 열 | 필수 | 내용 |
|---|---|---|
| date | Y | YYYY-MM-DD |
| type | Y | income / expense |
| category | Y | 사전에 등록한 카테고리 |
| amount | Y | 쉼표·통화 기호 없는 양수 정수 |
| memo | N | 문자열 |
| tags | N | 쉼표로 구분한 태그 문자열 |

입력 열 순서는 달라도 됩니다. 선택 열을 생략하면 빈 값으로 처리합니다. 필수 열 누락·중복 열·알 수 없는 열·행 열 개수 불일치는 오류입니다. 선택 열이 헤더에 있으면 빈 값도 구분 쉼표로 표현해야 합니다. 완전히 빈 물리 행은 무시합니다.

CSV의 쉼표·따옴표·여러 줄 메모 처리는 표준 `csv` 모듈에 맡깁니다. 읽어 낸 `tags` 값만 별도로 쉼표 분리합니다. 태그의 앞뒤 공백·빈 항목을 없애고, 순서를 유지하며 중복을 제거합니다.

**가져오기는 전체 성공 또는 전체 미반영입니다.** 모든 행을 검증한 뒤 신규 거래를 정렬해 한 번 병합 저장합니다. 한 행이라도 잘못되면 거래 파일에 0건 반영하고 첫 오류의 위치·원인·힌트를 출력합니다. 오류 위치는 레코드가 끝나는 물리 행 기준입니다.

CSV에 ID는 포함하지 않으며 가져올 때 새 ID를 부여합니다. 같은 CSV를 두 번 가져오면 거래 내용도 두 번 등록됩니다. 자동 중복 제거가 아니며 ID를 보존하는 백업도 아닙니다. 원본 백업은 앱 작업이 없을 때 JSONL 3개 파일을 함께 복사해야 합니다.

내부 저장 파일·잠금 파일 또는 해당 파일의 하드링크를 CSV 경로로 지정할 수 없습니다. CSV 경로의 심볼릭 링크도 거부합니다. 메모는 원문을 유지하므로 신뢰하지 않는 CSV를 스프레드시트에서 열 때는 수식 자동 해석에 주의해야 합니다.

## 5. 스트리밍과 데이터 안전성

거래 파일을 `(date, id)` 내림차순으로 유지합니다. 최신순은 거래 날짜순이며 같은 날짜의 ID 정렬은 등록 시각순이 아닙니다.

`list`와 `search`는 파일을 한 줄씩 읽는 제너레이터를 순회합니다. 거래 전체를 `list()`나 `sorted()`로 모으지 않습니다. `list --limit 20`은 최대 20건만 소비합니다. 카테고리 집합은 별도로 메모리에 읽습니다.

추가·수정·삭제는 전체 거래 검사와 파일 재작성이 필요합니다. `add/update/delete/import`는 거래 파일 변경 전에 ID 중복과 카테고리 참조를 검사합니다. 쓰기의 ID 집합은 O(n), 신규 m건의 CSV 가져오기는 O(n+m) 메모리를 사용합니다. 예산·카테고리 저장까지 모든 작업이 전체 거래 ID 검사를 하는 것은 아닙니다.

저장은 같은 폴더의 임시 파일 → 쓰기 → flush → fsync → 닫기 → `os.replace` 순서입니다. 교체 전 검증·쓰기·동기화·교체 실패에서는 원본을 보존합니다. 한 파일 교체의 원자성과 여러 파일의 동시 커밋·정전 내구성은 별개입니다.

파일 작업에는 `.budget_app.lock` 배타 잠금을 사용합니다. 동시 읽기도 대기 없이 거부될 수 있으며, 사용자 입력 대기 중에는 잠금을 유지하지 않습니다. 강제 종료 후 잠금이 남으면 실행 중인 다른 가계부 프로세스가 없는지 확인한 후 잠금 파일만 제거해야 합니다. JSONL 파일을 지우면 안 됩니다.

조회는 실제 소비한 행을 검사하므로 limit 뒤의 손상까지 확인하지 않습니다. 조회 시 모든 ID를 기억하는 전역 중복 검사는 하지 않습니다. 외부 편집기 변경·자동 복구·네트워크 파일시스템·전원 차단 내구성은 보장하지 않습니다.

## 6. 오류와 종료 코드

| 코드 | 의미 |
|---:|---|
| 0 | 성공, 데이터 없음 또는 예산 미설정의 정상 조회 |
| 1 | 없는 거래, 중복/사용 중 카테고리, 파일 손상·잠금·입출력 실패 |
| 2 | 명령 사용법·입력 검증·CSV 오류 |
| 130 | EOF 또는 Ctrl+C로 입력 취소 |

오류는 stderr에 `[오류] 원인`과 `[힌트] 해결 방법`을 출력합니다. 실제 CLI 오류에 Python 스택트레이스를 출력하지 않습니다. 대화형 입력 오류를 고쳐 정상 저장했다면 최종 종료 코드는 0입니다.

```bash
python3 -m budget_app delete --id missing
echo $?
```

## 7. 구조와 코드 읽기 순서

```text
budget_app/
├── __main__.py      # 진입점과 프로세스 종료 코드
├── cli.py           # 명령 해석, 대화형 입력, 출력
├── service.py       # 업무 규칙, CRUD, 검색, 요약
├── models.py        # 거래·예산·검색 조건·요약 모델
├── validators.py    # 입력 변환과 값 검증
├── storage.py       # JSONL 읽기·쓰기, 잠금, 원자적 교체
├── csv_io.py        # CSV 스키마와 입출력
├── errors.py        # 원인과 힌트를 가진 오류
├── decorators.py    # 공통 CLI 오류 처리
└── __init__.py      # 패키지 정보
```

실행 흐름은 `__main__.py → cli.main() → BudgetService → 저장소 → JSONL`입니다. 이후 각 파일을 위에서 아래로 읽으면서, 모델 검증과 파일 상태 검증의 책임 차이를 확인합니다.

전체 구현본의 `docs/ARCHITECTURE.md`, `docs/REQUIREMENTS_MATRIX.md`, `docs/PEER_REVIEW_GUIDE.md`에는 설계·명세 대응·피어 평가 설명을 정리했습니다. `docs/VERIFICATION.md`는 실제 실행한 검증과 미검증 범위를 구분합니다.

## 8. 확인 범위와 남은 작업

2026-10-09 전체 구현본의 자동 테스트 175개를 Linux / Python 3.13.5에서 다시 실행해 실패·오류·건너뜀 없이 통과했습니다. `-S` 실행에서도 같은 175개가 통과했습니다. 애플리케이션의 Python 3.10 문법 검사와 표준 라이브러리 의존성 검사도 통과했습니다.

Python 3.10 실제 인터프리터, 사용자 Mac·Windows, 정전 상황은 직접 검증하지 않았습니다. GitHub Actions나 원격 전체 소스의 테스트 통과를 뜻하지 않습니다.

10만 건 성능 검증 도구도 전체 구현본에 포함되어 있습니다.

```bash
python3 -m tools.benchmark --sizes 100000
python3 -m tools.benchmark_import
```

시간·메모리 수치는 실행 환경에 따라 달라집니다. `tracemalloc` 결과는 전체 프로세스 메모리나 실제 사용자 체감 시간과 다릅니다.

선택 보너스 중 임시 파일 교체는 적용했습니다. 자동 백업 명령·반복 거래 생성·정교한 표 너비 정렬은 미구현입니다. 최종 완료 판단에는 전체 소스·테스트·README의 원격 반영 확인과 해당 원격 코드 재검증이 필요합니다.
