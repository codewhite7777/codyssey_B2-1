# 제공 명세·평가표와 구현 연결

## 범위와 해석

기준은 사용자가 제공한 B2-1 과제 원문과 평가 항목 1~4이다. 과제 밖의 요구를 필수 평가 조건으로 추가하지 않는다. 기본 기능 묶음은 add/list/search/summary/budget/category/update/delete/import/export의 10개로 구분했다.

원문에 단일/이중 하이픈 표기가 섞였지만, 상세 기능 요구의 명시적 규칙에 따라 모두 `--`로 통일했다. 내부 저장 형식은 JSONL, 외부 교환은 CSV로 구분했다. 아래 테스트 이름은 `tests/`의 실제 테스트에서 찾을 수 있다.

## 필수 기능

| 제공 요구사항 | 구현 위치/정책 | 실제 검증 근거 |
|---|---|---|
| 대화형 add, 입력 검증, 생성 ID 출력 | cli._add / prompt, validators, service.add | CLI interactive add/retry/EOF, 모델·검증 테스트 |
| list 최신순, 기본 limit, 스트리밍 | service.list_transactions/search, repository.iter_transactions | 정렬·기본 20건·명시 limit·추가 행 미소비·반복 전용 파일 테스트 |
| search 기간/category/type/q/tag | SearchFilter, service.search | 경계 포함·열린 기간·조건 AND·메모 casefold·정확한 태그·CLI 모든 옵션 |
| summary 월별 수입/지출/잔액/TOP N | service.summary, MonthSummary | 기준 수치 3,000,000/215,000/2,785,000; 카테고리 순위·동률·빈 달 |
| budget set 영구 저장 및 사용률/경고 | set_budget/get_budget, BudgetStore, print_summary | 재실행 조회·동일 월 변경·43.0%·100.0% 비초과·초과 경고 |
| category add/list/remove | CategoryStore, service, 대화형 CLI | 신규·중복·삭제·미등록·사용 중 차단·거래 삭제 후 허용 |
| update 방식 고정, 없는 ID | 옵션 방식, dataclasses.replace | ID 유지·다중 필드·빈 메모/태그·없는 ID·잘못된 값·날짜 순서 재배치 |
| delete ID 기반, 없는 ID | service.delete | 특정/마지막 거래 삭제·없는 ID·원본 보존 |
| CSV import 고정 스키마 | csv_io.iter_csv, service.import_csv | 필수/선택 열·BOM·한글·쉼표·따옴표·개행·잘못된 행 전체 미반영 |
| CSV export 조건 필수 및 건수 | export_filter, export_csv, export_rows | 월/기간·조건 누락/충돌·헤더만 결과·round trip·보호 경로 |
| 저장 파일 최소 3개 | DataStore 초기화 | 세 JSONL 생성, 새 서비스/CLI 프로세스에서 유지 |
| 저장 경로 변경 | 모든 argparse 수준의 --data-dir | 명령 전/중/후 경로 옵션 테스트 |
| 초기 파일 처리 | 새 폴더 자동 초기화; 기존 일부 유실은 오류 | 새 폴더, 빈 초기화 복구, 기존 데이터 일부 유실 차단 |
| 빈 카테고리 정책 | 안 B: 등록 안내, add 차단 | empty_category_blocks_add_without_waiting |
| 데이터 모델 구조와 클래스 최소 2개 | dataclass 모델 4개, 별도 서비스/저장소 | 모델 검증·frozen·replace·각 기능 테스트 |
| 최소 3개 모듈 | 애플리케이션 Python 모듈 10개 | 파일 구성·AST 검사·책임 문서 |
| 직접 구현한 데코레이터 실제 적용 | @handle_cli_errors on cli.main | wraps 보존·예외별 코드·순회 도중 오류 변환 |
| 타입 힌트 | 함수 입출력, Literal, tuple, Iterator, TypedDict, ParamSpec | 타입과 다른 실제 값의 거부 테스트; 외부 정적 타입 검사 미실행 |
| 스택트레이스 없이 원인·힌트 | AppError + CLI 경계 데코레이터 | 실제 실패 CLI의 stderr 및 비정상 종료 검사 |
| 정상 0 / 실패 비0 | __main__.py SystemExit(main()) | 실제 하위 프로세스 returncode 검사 |
| 표준 라이브러리만 사용 | 앱의 절대 import 루트 17개 모두 표준 라이브러리 | AST import 감사, site 비활성화 CLI 실행 |
| Python 3.10 이상 | 3.10 호환 문법/표준 라이브러리 | 실제 Python 3.13.5 실행 + AST 3.10 문법 검사; 3.10 런타임 미실행 |
| README 필수 문서 | 실행법, 위치/형식, 명령 예, CSV 스키마 | README 실제 포함, 압축 재해제 검증 |

## 피어 평가 항목

| 제공 평가 항목 | 준비 근거 | 주의 |
|---|---|---|
| 항목 1: 기능·영구 저장·예산·CSV·오류/종료 코드 | 테스트 전체, 실제 CLI 시연 로그 | 테스트 통과와 학습자의 설명 능력은 별개 |
| 항목 2: 모듈/클래스 경계, update/delete 안전성 | ARCHITECTURE의 책임 경계·원자적 교체 설명 | 파일 잠금과 원자적 교체의 차이를 구분 |
| 항목 3: 스트리밍/데코레이터/타입 힌트 | ARCHITECTURE의 스트리밍·데코레이터·타입 힌트 설명 | yield 사용만으로 전체 코드가 상수 메모리가 되지 않음 |
| 항목 4: 형식 선택, 10만 건 병목, 깨진 CSV | README의 CSV/안전성 설명, ARCHITECTURE의 복잡도, 성능 결과 | 실제 측정과 개선 제안/미구현을 구분 |

## 선택한 구현 정책 — 새로운 필수 명세가 아님

| 모호하거나 선택 가능한 지점 | 이번 구현의 선택 |
|---|---|
| JSONL / CSV 중 내부 저장 | JSONL |
| 초기 기본 카테고리 여부 | 기본 생성 없음; category add 안내 |
| 최신순의 동률 기준 | 날짜 내림차순, 같은 날짜는 ID 내림차순 |
| update 인터페이스 | 옵션 기반으로 고정 |
| 사용 중 카테고리 | 삭제 차단, 자동 이전 없음 |
| import 일부 오류 | 첫 오류 보고 후 전체 미반영 |
| 내보내기 기간 해석 | 월 단독 또는 시작/종료 날짜 쌍 중 하나 |
| 예산 조회 명령 | budget show 추가 제공 |
| 초기 파일 일부 누락 | 기존 내용이 있으면 손상/유실로 중단 |
| 중복 내용의 CSV 재가져오기 | 새 ID로 신규 등록; 내용 기반 중복 제거 없음 |
| 동시 접근 | 앱 전체 단일 잠금, 충돌 시 안내 후 종료 |

## 선택 보너스

임시 파일 + 원자적 교체 방식은 적용했다. 자동 backup 명령, 반복 거래 생성, 정교한 표 폭 정렬은 구현하지 않았다. 반복내역/backup 명령의 부재를 필수 기능 미완료로 집계하지 않는다.
