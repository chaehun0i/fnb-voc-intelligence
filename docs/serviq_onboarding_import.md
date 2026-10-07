# Day 28 — 처음 사용하는 ServIQ / 데이터 입력

## 목적 / 실행 기준

Loop/Harness와 같은 Issue #56 / Day 28 PR에서 첫 접속 → 매장 → 데이터 → 확인 Import → 실제 첫 조사 경로를 연결했습니다. 기준 main/Drive와 안전 경계는 [Loop/Harness 문서](serviq_loop_harness.md)를 따릅니다. 새 Day나 별도 제품 Runtime을 만들지 않았습니다.

## 처음 사용하는 방법

1. `.env`의 기존 DB/비밀값을 보존하고 고정 Compose 프로젝트 `serviq`에서 `docker compose --profile serviq up --build -d --wait api frontend worker`를 실행합니다. DB/volume을 삭제하지 마세요.
2. `http://localhost:8080`에 접속합니다. 현재 기본 로컬 호환 인증은 별도 로그인 화면이 없으며 production OIDC가 아닙니다. 로컬 인증 사용 시 서버 Identity 설정을 따릅니다. Frontend 개발 서버는 `VITE_API_MODE=http`를 사용해야 하며 Mock은 실제 입력 경로가 아닙니다.
3. HTTP 모드의 빈 서버 상태이면 온보딩으로 안내합니다. 기존 사용자는 정상 Dashboard로 진입하며 사이드바 **데이터 시작하기** 또는 Dashboard 빈 상태 CTA에서 다시 접근합니다. localStorage의 완료값으로 데이터 존재를 판단하지 않습니다. 예시 모드에서는 실제 데이터 조회/입력 명령을 실행하지 않고 HTTP 연결 안내만 표시합니다.
4. 현재 권한으로 관리할 **매장명**을 등록합니다. 기존 사건/허용 source의 매장도 서버가 조회합니다.
5. **샘플 데이터로 체험하기**, **엑셀 템플릿으로 시작하기**, **내 파일 가져오기** 중 선택합니다. 샘플은 추가 내용을 확인하고 대상 매장을 선택합니다.
6. 템플릿의 예제 행을 자신의 자료로 바꾸거나 일반 Excel/UTF-8 CSV를 선택합니다. CSV/일반 Sheet는 데이터 종류를 지정합니다.
7. **검증 / 미리보기**에서 원본 컬럼→ServIQ 필드, 정상/오류 위치, warning, 최대 5개 preview row를 확인합니다. VOC 본문은 미리보기에서 숨깁니다. 잘못된 매핑은 수정하고 **다시 검증**합니다.
8. 오류가 없을 때 대상 매장/매핑/미리보기를 명시적으로 확인하고 **Import**합니다. Preview만으로 canonical 데이터는 생성되지 않습니다. 오류 행이 하나라도 있으면 전체 Import를 거부합니다.
9. **ServIQ 시작 체크리스트**가 실제 서버 stores/imports/incidents/runs/results를 표시합니다. 관리자는 설정이 전혀 없는 조직에만 동의 후 **안전한 초기 조사 설정**을 적용할 수 있습니다. 기존 config는 덮어쓰지 않으며 운영 설정에서 검토해야 합니다.
10. VOC에 포함된 짧은 검색어(샘플은 `품질`)로 **이 자료로 첫 조사 시작**을 누릅니다. 확인된 Import만 실제 Incident/Application Command → Jev → 영속 History Job으로 연결합니다. 원문 전체/개인정보를 검색어에 넣지 마세요.
11. 연결된 사건 상세에서 실제 Agent 조사, Evidence/Gap, Sufficiency, RCA와 CAPA를 확인합니다. Worker가 필요합니다. 검토 대기함의 사람 승인은 실행 완료가 아니며 외부 시스템은 변경하지 않습니다.

## 지원 파일 / Canonical Template Schema

`application/intake_schema.py` 하나의 metadata가 template 생성, alias mapping, Backend validation과 UI field 목록을 결정합니다. 정적 바이너리를 커밋하지 않고 `/api/v1/data/template`에서 Workbook을 생성합니다.

| Sheet | 필수 컬럼 | 선택 / 값 |
|---|---|---|
| 매장 | 매장명 | UI에서 대상 매장을 먼저 등록; 매장 Sheet만으로 분석 자료를 만들 수 없음 |
| VOC | 매장명, 자료ID, 발생일시, VOC 내용, 평점 | 제품명 선택; 평점 1~5 정수; 내용 2~2,000자 |
| 판매_거래 | 매장명, 자료ID, 발생일시, 관측코드 | REFUND_SIGNAL / CANCEL_SIGNAL |
| 재고 | 매장명, 자료ID, 발생일시, 관측코드 | STOCK_SHORTAGE / STOCK_ADJUSTMENT |

자료ID는 영문/숫자/`._:-` 1~64자입니다. 같은 source는 같은 ID를 사용합니다. ISO 8601 시간대 포함 날짜/시각을 권장하며 날짜만 입력하면 UTC 00:00, Excel의 시간대 없는 datetime은 UTC로 해석합니다. 거래/재고는 read-only Observation이며 금액/수량 원장이나 POS/ERP Connector가 아닙니다.

사용하지 않는 데이터 Sheet는 삭제하고 모든 예제 행을 실제 입력 자료로 교체하세요. 빈 데이터 Sheet는 오류로 처리합니다. 가이드 Sheet는 유지할 수 있습니다. 매장 등록은 UI에서 별도로 수행합니다.

`.xlsx`, UTF-8/BOM `.csv`만 지원합니다. 최대 2MB, Workbook 최대 5 sheets(가이드 포함), 합계 1,000행, 20열, 셀 4,000자이며 VOC 등 실제 필드의 더 작은 상한을 추가 적용합니다. `.xls`, `.xlsm`, 암호화/손상 Workbook은 지원하지 않습니다. 확장자/MIME/signature, ZIP entry 수/해제 크기, XML 선언, header/필수값/타입/날짜/중복 source를 검사합니다.

## Mapping / Preview / Confirm

별칭(`지점명`, `store_name`, `접수일`, `고객의견` 등)을 deterministic하게 제안합니다. 중복/모호한 매핑은 자동 확정하지 않으며 unmapped column을 표시하고 사용자가 수정합니다. LLM은 호출하지 않으며 Excel을 AI가 완전히 이해했다는 의미가 아닙니다.

정상 Preview의 normalized row는 tenant/store/요청자에 제한된 임시 입력 기록으로 15분 보관합니다. 원본 파일은 저장하지 않습니다. 만료 검증은 confirm에서 강제하며 물리 정리는 해당 tenant의 상태 조회/새 preview 시 수행합니다. 백그라운드 retention worker는 없습니다. 임시 row는 AI Trace/Checkpoint에 복제하지 않습니다.

Confirm은 digest/명시적 동의/Idempotency-Key/current tenant/store/RBAC/요청자를 확인합니다. 같은 요청 재전송과 같은 canonical Import는 receipt를 재사용합니다. 같은 자료ID에 다른 값을 넣으면 409이며 기존 값을 덮어쓰지 않습니다. source/receipt/audit/idempotency는 같은 UoW에서 원자적으로 처리합니다.

## Sample Dataset / 실제 첫 분석

`demo-intake-1`은 대상 매장에 품질 VOC 2개, 환불 관측 1개, 재고 부족 관측 1개를 생성합니다. PII/랜덤 Faker/실제 고객은 없습니다. 내용과 source identity는 결정적이며 최초 생성 시각은 freshness를 위해 현재 시각으로 고정합니다. 같은 매장의 같은 버전은 재클릭/재시작해도 늘어나지 않습니다. receipt와 canonical row의 sample marker로 Demo와 파일 입력을 구분합니다. Demo는 별도의 비어 있는 체험 매장에 추가하세요. 서버는 같은 매장의 Demo/운영 자료 혼합을 409로 차단하여 조사 근거가 섞이지 않게 합니다. 운영 파일은 별도 운영 매장으로 가져옵니다.

초기 설정은 관리자 동의 및 expected version 0 조건으로 기존 Settings Command를 사용합니다. Jev/제한 조사/RCA·CAPA 제안을 허용하지만 hosted AI, provider enablement, 자동 실행, 내부 실행은 비활성입니다. 기존 승인/위험 정책을 약화하지 않습니다. 실제 Jev 선택에 따라 사용 가능한 Agent가 조사되며 거래/재고가 있다는 이유로 모든 Agent를 강제로 실행하지 않습니다.

Import 기반 첫 분석은 stable Incident/snapshot/history Job identity를 사용합니다. 같은 요청/자료의 재전송은 기존 사건/Job에 연결합니다. 추가 조사는 기존 사건 업무 흐름을 사용합니다. 단순 서버 메모리 모드에는 별도 Worker/영속 checkpoint가 없으므로 전체 체험에는 Compose/PostgreSQL 모드를 사용합니다.

## Security / Failure

cross-tenant 404, 같은 조직 store/role/다른 preview 요청자 403, invalid 422, conflict 409, 저장소 unavailable 503을 유지합니다. Client가 tenant/risk/config/budget를 지정하지 않습니다. filename/path traversal, macro/embedded object/외부 링크/XML entity를 거부하며 formula를 실행하거나 resolve하지 않습니다. `=+-@` 시작 cell은 값으로 다시 입력하도록 거부합니다. UI는 React text로 표시하고 spreadsheet HTML을 실행하지 않습니다.

VOC 원문은 권한 범위의 canonical 입력 저장소에만 두고 tenant/store 조건으로 lexical 검색합니다. Agent에는 rank/source/time/normalized code만 전달합니다. 감사/receipt/AgentRun/API/Checkpoint에 raw 파일·VOC·prompt·provider response·credential을 복제하지 않습니다. imported observation의 provenance는 FILE_IMPORTED_OBSERVATION으로, Demo는 합성 관측으로 구분합니다. 일반 파일의 vector embedding 신규 생성은 구현하지 않았습니다.

## Validation

최종 로컬 결과와 원격 CI 상태는 Day 28 PR에 기록합니다. 새 `serviq_onboarding_import_smoke`는 실제 PostgreSQL API→샘플→Jev→Worker→Checkpoint→근거→재시작→CSV preview/confirm을 검증합니다. `serviq_http_smoke`는 실제 nginx template/multipart/confirm/idempotency를 추가 확인합니다. 기존 전체 smoke와 Loop/Harness 8 Golden을 유지합니다. 실제 Provider 호출과 external business write는 0입니다.

로컬 전체 `ruff check .` 통과, `pytest` **731 passed**, Backend `uv sync --locked`/FastAPI entrypoint 통과, Frontend `npm ci`/lint/build 통과, **30 files / 187 passed**입니다. 마지막 Demo 분리 안내 변경 후 관련 UI 6개 테스트와 lint/build도 재검증했습니다. PostgreSQL postgres/security/queue/dashboard/settings/jev/llm_gateway/langgraph/verification/multi_agent/loop_harness/onboarding_import **12개 smoke**가 격리 DB에서 통과했고 최종 Demo/운영 분리 후 onboarding smoke를 재검증했습니다. 실패 주입 시 출력되는 stable error는 해당 smoke의 의도된 회귀이며 실패를 skip/xfail로 숨기지 않았습니다.

Compose 이미지 빌드, migration, pgvector, API/nginx/Worker health와 실제 HTTP template/preview/confirm, CAPA 승인 재개, Verification PASS/FAIL/INCONCLUSIVE, Multi-Agent, Loop resume/stop/takeover 경로를 확인했습니다. HTTP fixture의 실행별 멱등 키 충돌은 수정 후 통과했습니다. 원격 GitHub Actions 결과는 PR에 별도로 기록합니다.

## Known Limitations / Not Implemented / Next

모든 임의 Excel schema를 자동 이해하지 않습니다. 별칭 밖의 컬럼은 사용자 확인/수정이 필요하며 미지원 sheet 종류/수식/원장 필드를 추론하지 않습니다. 일반 파일의 semantic/LLM mapping, 실제 POS/ERP/VOC Connector, source 갱신/삭제 UI, 조직/매장 관리 전체, background file retention, production 로그인/OIDC/SSO/deploy는 미구현입니다. 오래된 Demo는 실제 freshness 정책에 따라 부족한 근거가 될 수 있습니다.

MCP, LangChain 신규 Node Runtime, Tool Registry, Prompt Registry, production AI Release, 실제 외부 Action은 Day 28 구현으로 선언하지 않습니다. Day 29는 최신 정본 재확인 후 LangChain/MCP/Tool AX입니다.
