# B2-1 평가표 정리

[← README로 돌아가기](../README.md)

<p align="center"><img src="../images/11-evaluation-map.svg" alt="평가표 4개 항목: 항목1 동작하나, 항목2 어떻게 나눴나, 항목3 어떻게와 왜, 항목4 비교와 확장" width="100%"></p>

> 평가표의 질문마다 **한 줄 답**과 **README에서 보여줄 곳**만 모았습니다. 한 줄 답을 먼저 말하고, 꼬리 질문이 오면 README의 그림과 코드로 이어가면 됩니다.

---

## 항목 1 — 동작하나? (직접 실행해서 보여주기)

| 평가 질문 | 보여줄 결과 | README |
|---|---|---|
| add · list · search · summary · export · import · update · delete 가 요구사항대로 동작하나? | 명령별 실제 출력 | [3-3 ~ 3-9](../README.md#3-기능-확인--평가-항목-1) |
| 재실행 후에도 거래 · 카테고리 · 예산이 유지되나? (파일 3개+) | `ls data` → 파일 3개, 다시 `list` | [3-1](../README.md#3-1-처음-실행--저장-파일-3개-자동-생성) · [3-12](../README.md#3-12-다시-실행해도-남아-있나) |
| category add / list / remove, 사용 중 카테고리 처리? | 사용 중이면 "N건 있어 삭제할 수 없습니다" | [3-2](../README.md#3-2-카테고리-추가--목록--category-add--list) · [3-10](../README.md#3-10-카테고리-삭제--category-remove) |
| budget set 저장, summary 사용률 · 초과? | `사용률 43.0%` / `[경고] 예산을 50000원 초과했습니다!` | [3-8](../README.md#3-8-예산--월-요약--budget-set--summary) · [3-9](../README.md#3-9-내보내기--가져오기--export--import) |
| import / export 가 CSV 스키마(UTF-8, 헤더, 컬럼)대로? | `jan.csv` 헤더 `date,type,category,amount,memo,tags` | [3-9](../README.md#3-9-내보내기--가져오기--export--import) |
| 잘못된 입력 · 파일 오류에 스택트레이스 없이 원인 + 힌트? | `[오류]` + `[힌트]` 두 줄 | [3-3](../README.md#3-3-거래-추가--add-대화형) · [3-11](../README.md#3-11-오류와-종료-코드) |
| 오류면 종료 코드 ≠ 0? | `echo $?` → `1` (사용법 오류 `2`) | [3-11](../README.md#3-11-오류와-종료-코드) |

<details>
<summary>평가자 앞에서 한 번에 확인하는 명령 (새 폴더 <code>data/eval</code> 사용)</summary>

```bash
A="python -m budget_app --data-dir ./data/eval"

$A category list                                   # 첫 실행: 파일 3개 생성 + 기본 카테고리
$A import --from examples/import_ok.csv            # [완료] imported=4, skipped=0
$A list --limit 3                                  # 최신순 3건 (TX-000004, 03, 02)
$A search --from 2024-02-01 --to 2024-02-29 --category food
$A budget set --month 2024-02 --amount 150000
$A summary --month 2024-02 --top 3                 # 지출 192000원, 사용률 128.0% + [경고]
$A summary --month 2030-01                         # [안내] 2030-01 데이터 없음
$A update --id TX-000004 --amount 18000            # [수정 완료] …
$A delete --id TX-999999 ; echo "exit=$?"          # [오류]+[힌트], exit=1
$A import --from examples/import_broken.csv ; echo "exit=$?"   # imported=2, skipped=3 + 행 리포트, exit=1
$A category remove                                 # food 입력 → 2건 사용 중이라 거부
$A export --out out.csv --month 2024-02 && head -3 out.csv     # [완료] out.csv (6 records)
$A export --out out.csv ; echo "exit=$?"           # 기간 조건 누락 → 오류, exit=1
ls ./data/eval                                     # 파일 3개 확인 → 다시 list 로 유지 확인
```

</details>

---

## 항목 2 — 어떻게 나눴나? (구조 설계)

| 평가 질문 | 한 줄 답 | README |
|---|---|---|
| 모듈 3개+ 로 나눈 기준은? | **"바뀌는 이유가 같은 코드끼리"** — 화면 `cli.py`, 규칙 `service.py`, 파일 `storage.py`, 모양 `models.py` | [2-3](../README.md#2-3-클래스-설계) |
| 클래스 2개+ 의 책임 경계는? | **파일 1개 = 저장 클래스 1개**, 여러 파일을 함께 봐야 하는 규칙(사용 중 카테고리 삭제 금지 등)은 `BudgetService` | [2-3](../README.md#2-3-클래스-설계) · [3-10](../README.md#3-10-카테고리-삭제--category-remove) |
| 파일 기반 update/delete를 어떻게 안전하게? | 원본은 읽기만, **같은 폴더 임시 파일에 다 쓴 뒤 `os.replace()` 로 한 번에 교체** → 멈춰도 원본 아니면 완성본 | [4-1](../README.md#4-1-파일-기반-update--delete를-어떻게-안전하게-항목-2) |

**꼬리 질문 대비**
- "왜 임시 파일을 같은 폴더에?" → 다른 디스크면 `os.replace` 가 "이름 바꾸기"로 한 번에 끝나지 않을 수 있어서.
- "add 도 다시 쓰나?" → 아니요. add 는 파일 끝에 한 줄 **추가**(`"a"` 모드)라 기존 줄을 건드리지 않습니다.

---

## 항목 3 — 어떻게 · 왜? (파이썬 도구)

| 평가 질문 | 한 줄 답 | README |
|---|---|---|
| list/search 를 제너레이터로 어떻게, 왜? | 한 줄씩 읽어 `yield` 로 한 건씩, 그 위에서 `heapq.nlargest(N)` · 조건 검사 → **메모리는 1건 + 결과 N건뿐** | [4-2](../README.md#4-2-list--search를-제너레이터로-어떻게-왜-항목-3) |
| 데코레이터로 분리한 공통 기능과 이유는? | **`@handle_errors`** — 오류 출력 + 종료 코드를 한 곳에. 명령 11개에 복붙하면 하나만 빠뜨려도 스택트레이스가 샘 | [4-3](../README.md#4-3-데코레이터로-무엇을-분리했나-왜-항목-3) |
| 타입 힌트 이점을 실제 코드로? | `add(amount: int)` 에 `input()` 문자열을 넘기는 실수를 **mypy가 `cli.py:65` 에서 실행 전에** 잡음. 없으면 나중에 summary 에서 TypeError | [4-4](../README.md#4-4-타입-힌트의-이점을-실제-코드로-항목-3) |

**꼬리 질문 대비**
- "최신순인데 전체 정렬 안 해?" → `nlargest` 는 끝까지 훑되 상위 N개만 기억해서 전체를 메모리에 올릴 필요가 없습니다.
- "타입 힌트가 틀리면 실행이 막히나?" → 아니요. 그래서 실제 값 검사(`parse_amount` 등)는 따로 합니다. 타입 힌트 = 개발자 실수, 입력 검사 = 사용자 실수.

---

## 항목 4 — 만약에? (비교 · 확장 · 신뢰)

| 평가 질문 | 한 줄 답 | README |
|---|---|---|
| JSONL vs CSV, 왜 JSONL? | 한 줄 = 한 건 → **추가 · 스트리밍이 쉽고 숫자·목록을 그대로** 저장. CSV는 엑셀용이라 import/export 에만 | [2-1](../README.md#2-1-jsonl이란) · [5-1](../README.md#5-1-jsonl-vs-csv--왜-jsonl) |
| 거래가 10만 건이면 병목은? 어떻게 개선? | 매 명령이 **파일 전체 읽기**, update/delete 는 **전체 다시 쓰기**가 병목 → 월별 파일 분할 → SQLite(`sqlite3`). **`storage.py` 만 교체** | [5-2](../README.md#5-2-거래가-10만-건이면-병목과-개선) |
| import CSV 에 깨진 행이 섞이면? | **부분 성공 + 리포트** — 통과한 행만 저장, 버린 행은 "몇 번째 줄, 왜", 종료 코드 1 | [5-3](../README.md#5-3-import-csv에-깨진-행이-섞이면) |

**꼬리 질문 대비**
- "부분 성공이면 다시 넣을 때 중복되지 않나?" → 리포트가 **실패한 행만** 알려 주므로 그 행만 고쳐 넣으면 됩니다. (전체 롤백은 중복이 없지만 한 줄 실수로 전부 다시 해야 함)
- "지운 id가 다시 쓰이나?" → 가장 마지막 번호를 지우면 다시 쓰입니다. 저장된 거래끼리는 항상 유일하고, 막으려면 마지막 번호를 따로 저장하면 됩니다(10만 건 개선과 같은 방법).

---

## 코드 위치 (평가 때 바로 열기)

| 주제 | 파일 · 위치 |
|---|---|
| 제너레이터 | `storage.py` `read_jsonl()` 30행 · `iter_all()` 69행 / `service.py` `latest()` 145행 · `search()` 151행 |
| 데코레이터 | `decorators.py` `handle_errors()` 11행 → `cli.py` 명령 11개 (56행~) |
| 타입 힌트 · dataclass | `models.py` `Transaction` 8행, 모든 함수 시그니처 (`mypy --strict` 통과) |
| 안전한 update/delete | `storage.py` `atomic_write()` 50행 · `rewrite()` 100행 |
| 클래스 책임 경계 | `storage.py` 저장 클래스 3개 · `service.py` `remove_category()` 122행 |
| import 부분 성공 | `service.py` `import_csv()` 222행 |

[← README로 돌아가기](../README.md)
