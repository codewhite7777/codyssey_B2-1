# B2-1 · 나만의 용돈 기입장 프로그램 만들기

> **Python과 Git 심화** · 필수 미션 · 학습시간 60시간

## 💡 이 과제를 한 줄로

### **종이 용돈 기입장을 "터미널 프로그램"으로 옮기는 과제입니다.**

돈을 받거나 쓸 때마다 **명령어 한 줄로 적어 두고**, 필요할 때 **찾아보고**, 월말에 **"얼마 썼고 예산을 넘었는지"** 확인합니다.
기록은 파일에 남아서 프로그램을 껐다 켜도 사라지지 않습니다.

<p align="center"><img src="images/00-story.svg" alt="1월 한 달 이야기: 1일 예산 50만원 설정(budget set), 14일 월급 기록(add), 15일 점심 지출 기록(add), 20일 점심 내역 검색(search), 21일 중복 기록 삭제(delete), 31일 결산(summary)으로 예산 43% 사용 확인. 모든 기록은 파일 3개에 남고 엑셀과는 CSV로 주고받는다" width="100%"></p>

> [!NOTE]
> B2-1은 **팀 프로젝트**이고, 실제 구현은 소속 팀 저장소에서 진행합니다.
> 이 저장소는 **미션이 무엇을 요구하는지 / 각 개념이 무엇이고 왜 필요한지 / 어떤 순서로 만드는지**를 정리한 **학습·피어평가용 저장소**입니다.
> 보너스 과제(백업, 반복 내역, 테이블 정렬, 저장 원자성 강화)는 다루지 않습니다. → [7. 하지 않는 것](#7-하지-않는-것-보너스-제외)

### 이 문서 읽는 법

| 나는… | 여기부터 보세요 |
|---|---|
| 이 과제가 뭔지 **처음** 본다 | 위 그림 → [1. 미션 한눈에 보기](#1-미션-한눈에-보기) |
| 개념(제너레이터·데코레이터 등)을 **공부**한다 | [3. 핵심 개념 7가지](#3-핵심-개념-7가지) |
| 직접 **구현**한다 | [2. 설계 결정](#2-먼저-정해-두는-설계-결정-7가지) → [4. 명령어별 요구사항](#4-명령어별-요구사항-10개-기능) → [5. 진행 흐름](#5-단계별-진행-흐름) |
| **피어평가**를 준비한다 | [`docs/evaluation.md`](docs/evaluation.md) |

---

## 📌 목차

1. [미션 한눈에 보기](#1-미션-한눈에-보기)
2. [먼저 정해 두는 설계 결정 7가지](#2-먼저-정해-두는-설계-결정-7가지)
3. [핵심 개념 7가지 (쉬운 설명)](#3-핵심-개념-7가지)
4. [명령어별 요구사항 (10개 기능)](#4-명령어별-요구사항-10개-기능)
5. [단계별 진행 흐름 (Step 0 ~ 8)](#5-단계별-진행-흐름)
6. [구현 저장소 README에 꼭 들어갈 것](#6-구현-저장소-readme에-꼭-들어갈-것)
7. [하지 않는 것 (보너스 제외)](#7-하지-않는-것-보너스-제외)
8. [평가표 정리 → `docs/evaluation.md`](docs/evaluation.md)

---

## 1. 미션 한눈에 보기

<p align="center"><img src="images/00-at-a-glance.svg" alt="미션은 세 가지로 이루어진다. 만드는 것: 기록·조회·정리·주고받기 명령 10개와 저장 파일 3개. 배우는 것: 제너레이터, 데코레이터, 타입 힌트, 모듈·클래스 나누기. 지킬 것: 표준 라이브러리만, 파일 3개 이상, 모듈 3개 이상, 옵션은 -- 표기, 스택트레이스 금지, 오류면 종료 코드 0 아님" width="100%"></p>

### 1-1. 이럴 때 → 이 명령 (10개 기능)

> 모든 명령은 `python -m budget_app <명령>` 으로 실행합니다. 명령 하나를 처리하면 프로그램이 끝납니다.

| | 이럴 때 | 이렇게 입력 | 이렇게 나온다 |
|---|---|---|---|
| ✏️ | 돈을 받았다 / 썼다 | `add` (질문에 차례로 답하기) | `[저장 완료] id=TX-000012` |
| ✏️ | 금액을 잘못 적었다 | `update --id TX-000012 --amount 18000` | `[수정 완료] id=TX-000012` |
| ✏️ | 기록을 지우고 싶다 | `delete --id TX-000013` | `[삭제 완료] id=TX-000013` |
| 🔍 | 최근 기록을 보고 싶다 | `list --limit 5` | 최신순 5건 |
| 🔍 | 특정 내역만 찾고 싶다 | `search --q 점심 --from 2024-01-01 --to 2024-01-31` | 조건에 맞는 거래 (최신순) |
| 📊 | 이번 달 얼마 썼지? | `summary --month 2024-01 --top 3` | 수입 · 지출 · 잔액 · 지출 TOP 3 · 예산 사용률 |
| 📊 | 이번 달 예산을 정하자 | `budget set --month 2024-01 --amount 500000` | `[저장 완료] 2024-01 예산 500000원` |
| 📊 | 분류(식비·교통…)를 관리 | `category add` / `category list` / `category remove` | 추가 · 목록 · 삭제 결과 |
| 📁 | 엑셀로 보고 싶다 | `export --out jan.csv --month 2024-01` | `[완료] jan.csv (12 records)` |
| 📁 | 엑셀 내역을 한 번에 넣고 싶다 | `import --from bank.csv` | `[완료] imported=5, skipped=0` |

**그리고 잘못 입력하면?** 프로그램이 죽지 않고, 무엇이 틀렸는지와 고치는 방법을 알려 줍니다.

```console
$ python -m budget_app add
날짜(YYYY-MM-DD): 2024-13-40
[오류] 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).
[힌트] 예: 2024-01-15
```

### 1-2. 요구사항 요약표

| 구분 | 내용 |
|---|---|
| **무엇을** | 터미널에서 쓰는 **가계부(용돈 기입장)** 프로그램 |
| **어떻게 실행** | `python -m budget_app <명령> [옵션]` — 명령 하나 처리하고 끝나는 방식, 모든 명령 `--help` 지원 |
| **입력 방식** | 기본은 **대화형**(`add` 처럼 질문에 답하기), 조회·삭제 등은 **옵션** 방식 허용 |
| **저장** | JSONL 또는 CSV 중 1개로, **파일 3개 이상**에 영구 저장 (transactions / categories / budgets) |
| **꼭 쓰는 도구** | 제너레이터(`yield`), 데코레이터(`@`), 타입 힌트, `dataclass`, 모듈 3개 이상 분리 |
| **제약** | Python 3.10+, **표준 라이브러리만** (pip install 금지), 옵션은 `--` 표기, 스택트레이스 출력 금지 |

> **개발자 입장에서 한 문장으로** : "입력은 검사하고, 저장은 파일 3개에, 읽을 땐 한 줄씩, 고칠 땐 새로 써서 바꿔 끼우고, 실패하면 원인과 힌트를 보여준 뒤 0이 아닌 코드로 끝낸다."

---

## 2. 먼저 정해 두는 설계 결정 7가지

미션은 몇 군데에서 **"둘 중 하나를 골라 문서에 고정하라"** 고 요구합니다. 코드를 짜기 전에 먼저 정해야 팀원이 같은 그림을 봅니다.

| # | 결정할 것 | 선택지 | **이 저장소의 선택** | 이유 (한 줄) |
|---|---|---|---|---|
| 1 | 저장 포맷 | JSONL / CSV | **JSONL** | `tags` 같은 목록과 숫자 타입을 그대로 저장 ([3-1](#3-1-파일-기반-영구-저장--jsonl)) |
| 2 | 저장 위치 | `./data` 권장 | **`./data`**, `--data-dir` 로 변경 | 연습용·실사용 가계부를 폴더로 분리 가능 |
| 3 | 카테고리가 비었을 때 | 안 A 자동 생성 / 안 B add 막기 | **안 A** — `food, transport, rent, salary, etc` 자동 생성 | 처음 쓰는 사람이 바로 add 할 수 있다 |
| 4 | update 방식 | 안 A 옵션 / 안 B 대화형 | **안 A 옵션 방식** | 바꿀 필드만 적으면 되고, delete와 사용법이 같다 |
| 5 | 사용 중인 카테고리 삭제 | 삭제 막기 / 대체 카테고리 요구 | **삭제 막기** + 힌트 | 규칙이 단순하고 데이터가 몰래 바뀌지 않는다 |
| 6 | import 중 깨진 행 | 부분 성공 / 전체 롤백 | **부분 성공 + 행 번호 리포트** | 1줄 실수로 나머지를 버리지 않는다 ([4-9](#4-9-import--export-가져오기--내보내기)) |
| 7 | 종료 코드 | 0 / 0이 아닌 값 | **0** 성공 · **1** 실행 오류 · **2** 사용법 오류 | `2`는 argparse 기본값과 같아 일관적 |

---

## 3. 핵심 개념 7가지

미션이 끝나면 아래 내용을 **내 말로** 설명할 수 있어야 합니다. (= 과제 목표 + 평가표 항목 2~4)

### 3-1. 파일 기반 영구 저장 · JSONL

<p align="center"><img src="images/02-data-files.svg" alt="data 폴더의 transactions, categories, budgets JSONL 파일 예시와 JSONL·CSV 비교표" width="100%"></p>

- **영구 저장** = 프로그램이 꺼져도 남는 곳(파일)에 적어 두는 것. 변수는 프로그램이 끝나면 사라지지만 파일은 남습니다.
- **JSONL**(JSON Lines) = **한 줄에 JSON 객체 하나**. 줄 하나가 거래 하나라서 "한 줄 읽기 = 한 건 처리"가 됩니다.
- **왜 파일을 3개로 나누나?** 성격이 다른 데이터라서입니다. 거래는 계속 늘어나고, 카테고리·예산은 작고 가끔 바뀝니다. 섞어 두면 카테고리 하나 바꿀 때 거래 파일 전체를 다시 써야 합니다.
- **CSV는 어디에?** 저장은 JSONL, **가져오기/내보내기(import/export)만 CSV** 입니다. CSV는 엑셀로 열기 쉬워 "밖과 주고받는 용도"에 맞습니다.

```python
import json

line = '{"id": "TX-000012", "type": "expense", "amount": 15000, "tags": ["meal"]}'
record = json.loads(line)      # 문자열 → 딕셔너리
record["amount"] + 1000        # 16000  (숫자로 읽혀서 바로 계산 가능)
json.dumps(record, ensure_ascii=False)  # 딕셔너리 → 문자열 (한글 그대로 저장)
```

### 3-2. 계층(모듈 · 클래스) 나누기

<p align="center"><img src="images/01-layers.svg" alt="cli.py 카운터 직원, service.py 주방장, storage.py 창고 관리인, models.py 주문서 양식. 위에서 아래로만 호출하고 decorators.py가 모든 명령을 감싼다" width="100%"></p>

식당에 비유하면 쉽습니다. **카운터 직원(CLI)** 은 주문만 받고, **주방장(서비스)** 은 요리 규칙을 알고, **창고 관리인(저장소)** 은 재료 보관만 합니다. 모두 같은 **주문서 양식(모델)** 을 씁니다.

| 모듈 | 클래스 / 함수 | 책임 | 모르는 것 |
|---|---|---|---|
| `models.py` | `Transaction` (`@dataclass`) | 거래 한 건의 모양 | 저장 방법, 화면 |
| `storage.py` | `TransactionRepository`, `CategoryStore`, `BudgetStore` | 파일 읽기/쓰기 (파일 1개 = 클래스 1개) | 예산 초과 같은 규칙 |
| `service.py` | `BudgetService` | 검증, 정렬, 요약 계산, 카테고리 사용 여부 판단 | 화면 출력, 파일 형식 |
| `cli.py` | `main()`, `cmd_add()` … | argparse, `input()`, `print()`, 종료 코드 | 파일 형식, 계산 방법 |
| `decorators.py` | `handle_errors` | 모든 명령의 오류 출력 · 종료 코드 통일 | 각 명령의 내용 |
| `errors.py` | `AppError` | "원인 + 힌트"를 담는 예외 | — |

- **경계를 정한 기준** : "이 코드가 **바뀌는 이유**가 뭐지?" 화면이 바뀌면 CLI, 규칙이 바뀌면 서비스, 파일 형식이 바뀌면 저장소.
- **효과** : JSONL을 CSV(또는 SQLite)로 바꿔도 `storage.py` 만 고치면 됩니다. 나머지는 그대로입니다.

```python
from dataclasses import dataclass, field

@dataclass
class Transaction:
    id: str
    type: str            # "income" | "expense"
    date: str            # "YYYY-MM-DD"
    amount: int          # 양수
    category: str
    memo: str = ""
    tags: list[str] = field(default_factory=list)   # 기본값이 리스트면 field 사용
```

### 3-3. 제너레이터 (`yield`) — 한 줄씩 흘려 읽기

<p align="center"><img src="images/03-generator.svg" alt="리스트로 한꺼번에 읽으면 10만 건이 메모리에 올라가고, 제너레이터는 한 건씩 흘려보내며 필요한 3건만 기억한다. yield는 일시정지 버튼처럼 동작한다" width="100%"></p>

- **리스트** = 양동이로 물을 **다 퍼온 뒤** 마시기 → 파일이 커질수록 메모리도 커짐
- **제너레이터** = 빨대로 **필요한 만큼씩** 마시기 → 파일이 커져도 메모리는 거의 그대로
- `yield` 는 **일시정지 버튼** 입니다. 값 하나를 넘겨주고 그 자리에서 멈췄다가, 다음 값을 달라고 하면 멈춘 곳부터 다시 실행합니다.

```python
from collections.abc import Iterator
import heapq, json

def iter_transactions(path) -> Iterator[Transaction]:
    """파일을 한 줄씩 읽어 거래를 하나씩 내보낸다."""
    with open(path, encoding="utf-8") as f:
        for line in f:                   # 파일 객체도 한 줄씩 읽는다 (전체를 안 올림)
            if line.strip():
                yield Transaction(**json.loads(line))

# list --limit 3 : 전체를 흘려보내면서 "최신 3건"만 손에 쥔다
latest = heapq.nlargest(3, iter_transactions(path), key=lambda t: (t.date, t.id))

# search : 조건 검사도 흘려보내면서 (제너레이터 표현식)
matched = (t for t in iter_transactions(path) if t.category == "food")
```

> **"최신순"인데 왜 정렬을 안 하나?** 전부 정렬하려면 전부 메모리에 올려야 합니다.
> `heapq.nlargest(N, ...)` 는 끝까지 훑되 **상위 N개만** 기억하므로 메모리가 N건이면 충분합니다.
> (조건 없는 search처럼 개수 제한이 없을 때는 **조건에 맞는 것만** 모아 정렬합니다 → 원본 전체보다 훨씬 작음)

### 3-4. 데코레이터 (`@`) — 공통 일을 한 곳에

<p align="center"><img src="images/04-decorator.svg" alt="데코레이터 없이는 명령마다 try/except를 복붙해야 하지만, @handle_errors로 감싸면 성공은 종료 코드 0, 예상한 오류와 예상 못한 오류는 오류+힌트 출력 후 종료 코드 1" width="100%"></p>

- **데코레이터** = 함수를 **포장지로 감싸는** 함수. 원래 함수는 그대로 두고 "앞뒤에 할 일"을 붙입니다.
- **공통 관심사** = 모든 명령에 똑같이 필요한 일 (오류 처리, 실행 로그, 시간 측정). 기능과는 상관없지만 빠지면 안 되는 것.
- **왜 분리하나?** 10개 명령에 같은 `try/except` 를 복붙하면, 하나만 빠뜨려도 그 명령에서 스택트레이스가 튀어나옵니다. 포장지로 만들면 **규칙이 한 곳**에 있습니다.

```python
import functools

class AppError(Exception):
    """사용자에게 보여줄 오류: 원인(message) + 해결 힌트(hint)."""
    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.hint = hint

def handle_errors(func):
    @functools.wraps(func)                 # 원래 함수 이름·설명 유지
    def wrapper(*args, **kwargs) -> int:
        try:
            func(*args, **kwargs)
            return 0                       # 정상 종료
        except AppError as e:
            print(f"[오류] {e}")
            print(f"[힌트] {e.hint}")
            return 1
        except Exception:                  # 예상 못한 오류도 스택트레이스 대신 안내
            print("[오류] 알 수 없는 오류가 발생했습니다.")
            print("[힌트] 입력값과 data 폴더의 파일을 확인하세요.")
            return 1
    return wrapper

@handle_errors
def cmd_delete(args) -> None:
    ...   # 할 일만 쓴다. 없는 id면 raise AppError(...)
```

### 3-5. 타입 힌트 — 함수의 계약서

<p align="center"><img src="images/05-type-hints.svg" alt="함수 시그니처에 입력과 출력 타입을 적으면, 금액을 문자열로 저장하는 실수를 mypy가 실행 전에 잡는다. 타입 힌트가 없으면 며칠 뒤 summary에서 TypeError가 난다" width="100%"></p>

- **타입 힌트** = "이 함수는 **무엇을 받고 무엇을 돌려준다**"를 코드에 적어 둔 약속.
- Python은 실행할 때 **타입을 검사하지 않습니다.** 대신 **에디터**(VS Code 등)와 **mypy** 같은 검사 도구가 읽고 실수를 미리 알려 줍니다.
- 이 미션에서 특히 쓸모 있는 곳 : `input()` 은 **항상 문자열**을 돌려줍니다. 금액을 `int()` 로 안 바꾸고 저장하는 실수를 타입 힌트가 잡아 줍니다.

```python
def total_expense(items: Iterable[Transaction], month: str) -> int: ...
def find_by_id(tx_id: str) -> Transaction | None: ...   # 없으면 None — 호출하는 쪽이 None 처리를 잊으면 경고
```

```console
$ python -m mypy budget_app        # 개발 중 확인용 도구 (프로그램 실행에는 필요 없음)
error: Argument "amount" to "Transaction" has incompatible type "str"; expected "int"
```

> 💡 mypy 는 **개발할 때만 쓰는 검사 도구**라 "표준 라이브러리만" 제약과 별개입니다. 설치가 부담되면 에디터의 빨간 밑줄로도 같은 확인을 할 수 있습니다.

### 3-6. 파일 기반 update / delete — 새로 써서 바꿔 끼우기

<p align="center"><img src="images/06-safe-rewrite.svg" alt="원본을 w로 열면 즉시 비워져서 중간에 멈추면 데이터가 사라진다. 안전한 방법은 원본을 읽으며 임시 파일에 쓰고, id를 찾았을 때만 os.replace로 한 번에 교체하는 것" width="100%"></p>

- 텍스트 파일은 **중간 한 줄만 지우거나 고칠 수 없습니다.** 그래서 update/delete는 "전체를 다시 쓰기"가 됩니다.
- 원본을 `open(path, "w")` 로 열면 **여는 순간 내용이 비워집니다.** 쓰다가 오류가 나면 데이터가 사라집니다.
- 그래서 **① 원본은 읽기만 → ② 같은 폴더의 임시 파일에 새 내용 쓰기 → ③ 다 쓰면 `os.replace()` 로 한 번에 교체** 합니다. `os.replace` 는 "이름표를 바꿔 붙이는" 동작이라 중간 상태가 없습니다.

```python
import os, tempfile, json
from dataclasses import asdict

def delete_transaction(path, tx_id: str) -> bool:
    found = False
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")  # 같은 폴더!
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            for t in iter_transactions(path):          # 원본은 한 줄씩 읽기만
                if t.id == tx_id:
                    found = True
                    continue                           # 지울 줄만 건너뛴다
                out.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")
        if found:
            os.replace(tmp, path)                      # 다 쓴 뒤 한 번에 교체
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)                             # 실패/미발견 시 임시 파일 정리
    return found                                       # False → "없는 id" 안내
```

> **왜 같은 폴더에 임시 파일을?** 다른 디스크(폴더)로 옮기면 "이름표만 바꾸기"가 안 되고 복사가 일어나서 한 번에 교체되지 않을 수 있습니다.

### 3-7. 오류 처리와 종료 코드

사용자는 스택트레이스(빨간 오류 덩어리)를 읽을 수 없습니다. **원인 + 해결 힌트** 두 줄이면 됩니다.

```console
$ python -m budget_app delete --id TX-999999
[오류] id=TX-999999 거래를 찾을 수 없습니다.
[힌트] list 명령으로 id를 먼저 확인하세요.
$ echo $?          # 방금 명령의 종료 코드 확인 (Windows PowerShell: $LASTEXITCODE)
1
```

| 종료 코드 | 의미 | 예 |
|---|---|---|
| `0` | 정상 | 저장 완료, 목록 출력 |
| `1` | 실행 중 오류 | 없는 id, 파일 손상, 사용 중 카테고리 삭제, import 일부 건너뜀 |
| `2` | 사용법 오류 | 없는 명령, 필수 옵션 누락 (argparse가 자동으로 2를 돌려줌) |

- **왜 0이 아닌 값이 중요?** 다른 프로그램(스크립트, 자동화)은 화면 글자를 읽지 않고 **종료 코드로 성공/실패를 판단**합니다.
- `__main__.py` 에서 `sys.exit(main())` 처럼 **명령의 반환값을 종료 코드로** 넘깁니다.

| 입력 검증 대상 | 잘못된 예 | 처리 |
|---|---|---|
| 날짜 | `2024-13-40`, `2024/01/15` | `datetime.strptime(s, "%Y-%m-%d")` 실패 → 오류 + 예시 힌트 |
| 금액 | `-500`, `0`, `만원` | `int()` 실패 또는 `<= 0` → 오류 |
| 타입 | `spend` | `income` / `expense` 외 → 오류 |
| 카테고리 | `golf` (미등록) | 등록 목록을 보여주고 다시 입력 |

---

## 4. 명령어별 요구사항 (10개 기능)

> 공통 : 모든 명령은 `--help` 지원 · 옵션은 `--` 로 통일 · 저장 폴더는 `--data-dir`(기본 `./data`) · 출력 문구는 예시이며 똑같을 필요는 없습니다.

| # | 명령 | 입력 방식 | 출력 | 놓치기 쉬운 점 |
|---|---|---|---|---|
| 1 | `add` | **대화형** (날짜·타입·카테고리·금액·메모·태그) | `[저장 완료] id=...` | 미등록 카테고리 → 재입력 |
| 2 | `list` | `--limit N` (기본 10) | 최신순 목록 | **제너레이터 스트리밍** 필수 |
| 3 | `search` | `--from --to --category --type --q --tag` | 최신순 목록 | 조건 여러 개 = 모두 만족(AND) |
| 4 | `summary` | `--month YYYY-MM --top N` | 수입·지출·잔액 + TOP N (+ 예산) | 거래 없는 달 → "데이터 없음" |
| 5 | `budget` | `budget set --month --amount` | 저장 완료 | 결과 확인은 summary에서 |
| 6 | `category` | `add` / `list` / `remove` | 목록·결과 | 사용 중이면 삭제 막기 |
| 7 | `update` | `--id` + 바꿀 옵션만 (옵션 방식) | 수정 성공/실패 | 없는 id, 바뀐 값도 다시 검증 |
| 8 | `delete` | `--id` | 삭제 성공/실패 | 없는 id → "없는 데이터" |
| 9 | `import` | `--from <csv>` | `imported=n, skipped=m` | 깨진 행 리포트 |
| 10 | `export` | `--out <csv>` + (`--month` 또는 `--from/--to`) | `[완료] 파일 (n records)` | 기간 조건 **필수** |

### 4-1. add (거래 추가)

<p align="center"><img src="images/07-add-flow.svg" alt="add 명령은 날짜, 타입, 카테고리, 금액, 메모, 태그를 차례로 묻고 각각 검사한다. 실패하면 그 칸만 다시 묻고, 모두 통과하면 id를 만들고 파일 끝에 한 줄 추가한 뒤 저장 완료를 출력한다" width="100%"></p>

```console
$ python -m budget_app add
날짜(YYYY-MM-DD): 2024-01-15
타입(income/expense): expense
카테고리: food
금액(양수): 15000
메모(선택): 점심
태그(쉼표로 구분, 없으면 엔터): meal
[저장 완료] id=TX-000012
```

- 새 거래는 파일 **맨 끝에 한 줄 추가**(`"a"` 모드) → 추가는 전체 재작성이 필요 없습니다.
- id는 `TX-` + 6자리 번호. 파일을 한 줄씩 읽으며 **가장 큰 번호 + 1** (유일성 보장).

### 4-2. list (목록) · 4-3. search (검색)

```console
$ python -m budget_app list --limit 3
TX-000012 | 2024-01-15 | expense | food | 15000 | 점심
TX-000011 | 2024-01-14 | income  | salary | 3000000 |
TX-000010 | 2024-01-12 | expense | transport | 20000 |

$ python -m budget_app search --from 2024-01-01 --to 2024-01-31 --type expense --q 점심
TX-000012 | 2024-01-15 | expense | food | 15000 | 점심
```

| 옵션 | 의미 | 검사 방법 |
|---|---|---|
| `--from`, `--to` | 기간 (양 끝 포함) | `"2024-01-01" <= t.date <= "2024-01-31"` (YYYY-MM-DD 문자열은 사전순 = 날짜순) |
| `--category` | 카테고리 일치 | `t.category == 값` |
| `--type` | income / expense | `t.type == 값` |
| `--q` | 메모 키워드 포함 | `값 in t.memo` |
| `--tag` | 태그 포함 | `값 in t.tags` |

- **최신순 기준** : 날짜(`date`)가 최근인 것 먼저, 같은 날짜면 id가 큰 것(나중에 입력한 것) 먼저.
- list/search 모두 **파일 → 제너레이터 → 조건 → 상위 N개** 흐름을 유지합니다. ([3-3](#3-3-제너레이터-yield--한-줄씩-흘려-읽기))

### 4-4. summary (월별 요약) · 4-5. budget (예산)

<p align="center"><img src="images/08-summary-budget.svg" alt="summary는 거래를 한 건씩 보면서 수입 합계, 지출 합계, 카테고리별 지출에 더하기만 한다. 예산이 있으면 사용률을 계산하고 초과하면 경고한다" width="100%"></p>

```console
$ python -m budget_app budget set --month 2024-01 --amount 500000
[저장 완료] 2024-01 예산 500000원

$ python -m budget_app summary --month 2024-01 --top 3
총 수입: 3000000원
총 지출: 215000원
잔액: 2785000원
예산: 500000원 (사용률 43.0%)

지출 TOP 3
1) rent 150000원
2) food 45000원
3) transport 20000원

$ python -m budget_app summary --month 2030-01
[안내] 2030-01 데이터 없음
```

- 합계는 **훑으면서 더하기만** 하므로 거래를 모아 둘 필요가 없습니다. 카테고리별 합계는 `collections.Counter`, TOP N은 `Counter.most_common(N)`.
- 같은 달에 `budget set` 을 다시 하면 **덮어쓰기**(달마다 예산 1개). budgets 파일은 작아서 전체 재작성으로 충분합니다.
- 사용률 = `총 지출 / 예산 * 100`. 100%를 넘으면 `[경고]` 문구를 추가합니다.

### 4-6. category (카테고리 관리)

```console
$ python -m budget_app category add
카테고리명: hobby
[저장 완료] category=hobby

$ python -m budget_app category list
- etc
- food
- hobby
...

$ python -m budget_app category remove
카테고리명: food
[오류] food 카테고리를 사용하는 거래가 3건 있어 삭제할 수 없습니다.
[힌트] update --id <id> --category <다른 카테고리> 로 먼저 옮기세요.
```

- 첫 실행에 categories 파일이 비어 있으면 **기본 카테고리 자동 생성** (`food, transport, rent, salary, etc`) — 결정 #3
- 이미 있는 이름 추가 → 중복 오류 / 없는 이름 삭제 → "없는 카테고리" 오류

### 4-7. update (수정) · 4-8. delete (삭제)

```console
$ python -m budget_app update --id TX-000012 --amount 18000 --memo "점심+커피"
[수정 완료] id=TX-000012

$ python -m budget_app delete --id TX-000012
[삭제 완료] id=TX-000012

$ python -m budget_app delete --id TX-000012
[오류] id=TX-000012 거래를 찾을 수 없습니다.
[힌트] list 명령으로 id를 먼저 확인하세요.
```

- update는 **옵션 방식으로 고정** (결정 #4). 적은 옵션만 바뀌고 나머지는 그대로. 옵션을 하나도 안 적으면 사용법 오류.
- 바뀐 값도 add와 **같은 검증**을 거칩니다 (음수 금액으로 수정 불가).
- 둘 다 [3-6. 새로 써서 바꿔 끼우기](#3-6-파일-기반-update--delete--새로-써서-바꿔-끼우기) 방식으로 저장합니다.

### 4-9. import / export (가져오기 / 내보내기)

<p align="center"><img src="images/09-import-report.svg" alt="깨진 행이 섞인 CSV를 import하면 통과한 행만 저장하고 버린 행은 행 번호와 이유를 리포트한다. 부분 성공, 전체 롤백, 리포트 세 가지 선택지 비교" width="100%"></p>

**CSV 스키마 (import / export 공통, 고정)**

| column | required | 설명 |
|---|---|---|
| `date` | Y | `YYYY-MM-DD` |
| `type` | Y | `income` / `expense` |
| `category` | Y | 등록된 카테고리 |
| `amount` | Y | 양수 정수 |
| `memo` | N | 문자열 |
| `tags` | N | 쉼표(`,`) 구분 문자열 — 예: `"meal,lunch"` |
| **공통** | | **UTF-8**, 첫 줄 **헤더 포함** |

```console
$ python -m budget_app export --out export.csv --month 2024-01
[완료] export.csv (12 records)

$ python -m budget_app export --out export.csv
[오류] 내보낼 기간이 없습니다.
[힌트] --month YYYY-MM 또는 --from YYYY-MM-DD --to YYYY-MM-DD 중 하나를 지정하세요.

$ python -m budget_app import --from examples/import_broken.csv
[완료] imported=2, skipped=3
  3행: amount는 양수여야 합니다 (0)
  5행: 등록되지 않은 카테고리 (golf)
  6행: 날짜 형식 오류 (2024/01/09)
```

- `csv.DictReader` / `csv.DictWriter` 사용. 파일은 `open(..., encoding="utf-8", newline="")` 으로 엽니다 (`newline=""` 은 메모 속 쉼표·줄바꿈을 csv 모듈이 올바르게 처리하게 함).
- `id` 는 CSV에 없습니다 → import 할 때 **새 id를 발급**합니다.
- 헤더에 필수 컬럼이 빠졌으면 **한 줄도 읽지 않고 거부** (파일 자체가 잘못됨).
- 예시 파일 : [`examples/import_ok.csv`](examples/import_ok.csv) · [`examples/import_broken.csv`](examples/import_broken.csv)

---

## 5. 단계별 진행 흐름

<p align="center"><img src="images/12-roadmap.svg" alt="Step 0 결정 고정, Step 1 모델, Step 2 거래 저장소, Step 3 카테고리와 예산, Step 4 서비스, Step 5 import/export, Step 6 CLI, Step 7 데코레이터, Step 8 README와 시나리오 점검" width="100%"></p>

> **아래(데이터)부터 위(화면)로** 쌓으면 각 단계를 만든 즉시 `python -c` 나 짧은 테스트로 확인할 수 있습니다. 각 Step의 ✅가 그 단계의 완료 기준입니다.

| Step | 할 일 | 만드는 파일 | ✅ 완료 기준 |
|---|---|---|---|
| **0** | 설계 결정 7가지 고정 | README 초안 | [2장 표](#2-먼저-정해-두는-설계-결정-7가지)의 선택이 문서에 적혀 있다 |
| **1** | 모델 | `models.py` | `Transaction` dataclass + dict ↔ 객체 변환 함수 |
| **2** | 거래 저장소 | `storage.py` | `iter_all()`(yield) · `append()` · `rewrite()` (임시 파일 + `os.replace`) |
| **3** | 카테고리 · 예산 저장소 | `storage.py` | `CategoryStore`, `BudgetStore` / 파일 없으면 자동 생성 → **파일 3개** |
| **4** | 서비스 | `service.py`, `errors.py` | 날짜·금액·타입·카테고리 검증, 최신순·검색·요약·예산 사용률, 사용 중 카테고리 판단 |
| **5** | import / export | `service.py` | 헤더 검사, 행별 검증 + 리포트, export 기간 조건 필수 |
| **6** | CLI | `cli.py`, `__main__.py` | `argparse` 서브커맨드, 모든 명령 `--help`, `--data-dir`, add 대화형 |
| **7** | 데코레이터 · 종료 코드 | `decorators.py` | 모든 명령에 `@handle_errors`, 스택트레이스 없음, 0/1/2 |
| **8** | 문서 · 점검 | `README.md` | [6장](#6-구현-저장소-readme에-꼭-들어갈-것) 4가지 포함, 아래 시나리오 통과 |

<details>
<summary><b>Step 8 — 처음부터 끝까지 점검 시나리오</b> (펼치기)</summary>

```bash
# 0) 깨끗한 연습 폴더에서 시작 (기존 가계부와 분리)
python -m budget_app --data-dir ./data/try category list        # 파일 3개 자동 생성 + 기본 카테고리
python -m budget_app --data-dir ./data/try --help                # 사용법

# 1) 추가 · 조회 · 검색
python -m budget_app --data-dir ./data/try add                   # 대화형 입력 (일부러 2024-13-40 도 넣어 보기)
python -m budget_app --data-dir ./data/try list --limit 5
python -m budget_app --data-dir ./data/try search --type expense --q 점심

# 2) 예산 · 요약
python -m budget_app --data-dir ./data/try budget set --month 2024-01 --amount 500000
python -m budget_app --data-dir ./data/try summary --month 2024-01 --top 3

# 3) 수정 · 삭제 · 없는 id
python -m budget_app --data-dir ./data/try update --id TX-000001 --amount 18000
python -m budget_app --data-dir ./data/try delete --id TX-999999 ; echo "exit=$?"   # exit=1

# 4) 카테고리 · CSV
python -m budget_app --data-dir ./data/try category remove      # 사용 중인 food → 삭제 막힘
python -m budget_app --data-dir ./data/try import --from examples/import_broken.csv ; echo "exit=$?"
python -m budget_app --data-dir ./data/try export --out out.csv --month 2024-01

# 5) 재실행 후 유지 확인 — 같은 --data-dir 로 다시 list
python -m budget_app --data-dir ./data/try list
ls ./data/try        # budgets.jsonl  categories.jsonl  transactions.jsonl
```

</details>

---

## 6. 구현 저장소 README에 꼭 들어갈 것

미션의 **최종 결과물 필수 구성**입니다. 구현 저장소 README에 아래 4가지가 빠지면 안 됩니다.

| # | 항목 | 들어갈 내용 예 |
|---|---|---|
| 1 | **실행 방법** | Python 3.10+ 확인, 저장소 루트에서 `python -m budget_app --help`, `--data-dir` 사용법 |
| 2 | **저장 파일 위치 / 형식** | `./data/transactions.jsonl` 등 3개, 한 줄 예시, 첫 실행 시 자동 생성 |
| 3 | **주요 명령 예시** | 4장의 10개 명령 예시 (입력 → 출력) |
| 4 | **import/export CSV 스키마** | [4-9의 표](#4-9-import--export-가져오기--내보내기) 그대로 + UTF-8 · 헤더 포함 |

추가로 **설계 결정 7가지**(2장)를 함께 적으면 평가 때 "왜 이렇게 했나"를 바로 보여줄 수 있습니다.

권장 폴더 구조 (모듈 3개 이상, 계층별 분리):

```
budget_app/
├── __init__.py
├── __main__.py      # python -m budget_app 진입점 → sys.exit(cli.main())
├── cli.py           # argparse, input(), print()
├── service.py       # BudgetService : 검증 · 계산 · 규칙
├── storage.py       # TransactionRepository · CategoryStore · BudgetStore
├── models.py        # Transaction dataclass
├── decorators.py    # handle_errors
└── errors.py        # AppError
data/                # 실행하면 생기는 저장 폴더 (.gitignore 에 추가)
README.md
```

---

## 7. 하지 않는 것 (보너스 제외)

| 보너스 과제 | 다루지 않는 이유 |
|---|---|
| 백업(`backup`) | 선택 과제. 필수 기능만으로 평가 항목을 모두 충족 |
| 반복 내역(월급·월세 자동 생성) | 선택 과제 |
| 출력 테이블 정렬 | 선택 과제. 필수 출력은 `|` 구분으로 충분 |
| 저장 원자성 강화 | 선택 과제. 단, **필수 요구사항**이 update/delete의 안정성(임시 파일·원자적 교체 "권장")을 요구하고 평가 항목 2가 "어떻게 안전하게"를 묻기 때문에 [3-6](#3-6-파일-기반-update--delete--새로-써서-바꿔-끼우기)의 기본 개념만 설명합니다. `fsync`, 파일 잠금 같은 추가 강화는 다루지 않습니다. |

---

## 📁 이 저장소의 구성

```
README.md              ← 지금 이 문서 (요구사항 · 개념 · 흐름)
docs/evaluation.md     ← 평가표 항목 1~4 정리 (확인 방법 + 예상 질문과 답)
images/                ← 설명 이미지 (SVG)
examples/              ← import 예시 CSV (정상 / 깨진 행 포함)
```

➡️ **평가 준비는 [`docs/evaluation.md`](docs/evaluation.md) 에서 이어집니다.**
