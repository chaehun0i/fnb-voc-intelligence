# Day 17 Tenant RBAC와 Review 실행 계약

## 목적

Day 16의 실제 Incident Runtime 위에 요청자 → 조직·역할 검증 → 멱등성 → 승인 기록 → 감사 기록 → Review API/UI를 연결합니다. 기존 Data Intelligence, RAG, ingestion, PostgreSQL/pgvector, Streamlit, Incident 상태머신과 Outbox/Worker는 유지합니다.

구현 기준은 [ServIQ v0.5 운영 안전 설계 폴더](https://drive.google.com/drive/folders/1eVwhcoTWaebKUqmJgdGMBF9xY7gXcmmJ)입니다. 실제 상세 문서가 있는 04 데이터 모델, 05 API·오류·Idempotency, 13 UI/UX, 14 보안, 24 실행 계약, 25 GAP, 28 코딩 청사진, 30 Principal 계약을 확인했습니다. v0.4/v0.4.1 fallback은 사용하지 않았습니다. 시작 기준은 main@c6060ae, Day 16 PR #31 병합 상태입니다. v0.5는 설계 기준이며 운영 배포 완료 선언이 아닙니다.

## 구성

### 책임과 현재 구현 상태

| 구분 | 구현과 책임 | 상태 |
| --- | --- | --- |
| 요청자 경계 | Principal의 principal_id·tenant_id·roles·store_scope·authentication_source, RequestContext의 요청/상관 ID | IMPLEMENTED |
| 인증 공급자 | 서버에 등록한 개발 계정을 LocalIdentityProvider가 해석하며 IdentityProvider Port로 분리 | IMPLEMENTED / 개발 전용 |
| 서버 권한 | 조직에 고정된 Repository와 중앙 RBAC, 조회·운영·검토·관리 역할 구분 | IMPLEMENTED |
| Approval | 조치 digest·위험도·버전·요청자·기한·결정자·시각·사유를 PostgreSQL에 저장 | IMPLEMENTED / PostgreSQL 모드 |
| Audit | 별도 불변 기록, actor·tenant·command·resource·result·request/correlation ID, 추가만 허용하는 DB trigger | IMPLEMENTED / PostgreSQL 모드 |
| Idempotency | 조직·요청자·명령·키의 유일성, fingerprint와 완료 결과 저장·재사용 | IMPLEMENTED / PostgreSQL 모드 |
| Review | Approval 원본의 Query/Command, 서버 permission, React Mock/HTTP Adapter | IMPLEMENTED |
| 로그인·회원 범위 | 실제 OIDC/SSO·JWT 검증·계정/조직 membership 저장은 미연결 | PARTIAL / PLANNED |
| Job/Queue | 독립 Job 운영 API와 실제 Queue UI는 아직 없음. 기존 Outbox Worker만 실제 동작 | PLANNED |

주요 코드는 backend/src/application/security·approvals·commands·ports, backend/src/domain/approvals, backend/src/infrastructure/auth·repositories·access_unit_of_work.py, backend/src/api/routes/reviews.py·schemas/reviews.py, frontend/src/api/reviews와 features/reviews에 있습니다.

Principal의 역할과 조직은 서버 설정에서 결정합니다. 브라우저의 X-Role/X-Tenant-ID 같은 값을 권한으로 신뢰하지 않습니다. HQ_ADMIN은 전체 업무 역할, QA_MANAGER/OPS_MANAGER/STORE_MANAGER는 운영, REVIEWER는 승인·반려, AUDITOR는 읽기를 지원합니다. STORE_MANAGER는 지정한 매장만 접근하며 검토자는 조사 명령을 실행하지 못합니다. 실제 관리 설정 API는 이번 범위가 아닙니다.

다른 조직의 ID는 Repository의 tenant 조건에서 차단해 404로 숨깁니다. 같은 조직의 역할·매장 권한 부족은 403 AUTHORIZATION_DENIED입니다. 서버 권한은 응답 permission과 실행 시 검사 모두에 적용하며 UI는 결과만 표시합니다.

### 승인·감사·멱등성 실행 경계

승인 요청은 현재 조치 목록과 Incident 버전을 묶어 24시간 기한의 Approval을 만듭니다. 승인·반려는 기존 Incident Application/Domain 명령을 재사용합니다. 최고 위험(CRITICAL) 조치는 요청자와 다른 검토자가 승인해야 합니다. 이미 결정됐거나 기한·조치 digest·Incident 버전이 맞지 않으면 새 결정을 거부합니다. 실행 전에는 유효한 영속 승인 기록을 다시 확인합니다. 승인은 외부 조치 실행이 아닙니다.

PostgreSQL은 같은 연결의 트랜잭션에서 Incident·Approval·성공 Audit·기존 Outbox·완료 Idempotency 결과를 저장합니다. 하나라도 실패하면 전부 롤백합니다. 인증된 요청자의 권한 거부는 업무 롤백 후 별도의 DENIED 감사로 남깁니다. 인증되지 않은 요청에는 Principal이 없으므로 이 업무 Audit을 생성하지 않습니다. 다른 조직의 존재 여부를 숨긴 404 역시 승인/업무 성공 기록으로 만들지 않습니다.

Audit에는 토큰·비밀번호·전체 HTTP payload를 저장하지 않습니다. 승인 사유는 Approval의 의사결정 자료이고 Audit과 별개입니다. 서버의 감사 저장 Port는 추가/조직별 조회만 제공하고 PostgreSQL trigger는 기존 행의 UPDATE/DELETE를 거부합니다. DB 관리자까지 제한하는 WORM/권한 분리·보관 정책은 후속입니다.

같은 조직·요청자·명령의 Idempotency-Key와 같은 semantic request는 완료 결과를 돌려주며 version·Approval·성공 Audit·Outbox를 중복 생성하지 않습니다. 같은 키의 다른 내용은 409 IDEMPOTENCY_CONFLICT입니다. 다른 조직은 같은 문자열 키를 써도 충돌하지 않습니다. DB 유일성으로 동시 요청을 직렬화하고 잠금 대기는 제한합니다. 처리 중 충돌은 PROCESSING으로 재시도 안내합니다. 재사용 전에도 현재 권한을 다시 검사합니다. expected_version의 동시 수정 방어와는 별도 계약입니다.

### Additive migration과 기존 자료

001_serviq.sql은 수정하지 않았습니다. SQL runner는 파일 순서대로 설치된 리소스를 읽으며 반복 실행할 수 있습니다.

- 002_tenant_security.sql: 기존 Incident/Outbox를 legacy-local 조직으로 보존하고 tenant 조회 조건을 추가합니다.
- 003_approval.sql: 조직·Incident를 참조하는 별도 Approval을 저장합니다.
- 004_audit.sql: 조직별 감사 로그와 변경 거부 trigger를 만듭니다.
- 005_idempotency.sql: 요청 범위 유일성과 완료 결과를 저장합니다.

기존 approved boolean을 누가 검토했는지 모르는 Approval로 꾸며 이관하지 않습니다. 기존 자료의 조회와 Domain 구현을 유지하되 HTTP 실행에는 실제 승인 기록이 필요합니다.

### Review HTTP 계약

| Endpoint | 입력과 결과 |
| --- | --- |
| GET /api/v1/reviews | 현재 조직의 목록, status·limit(1~100)·offset |
| GET /api/v1/reviews/{approval_id} | approval과 detail, 실제 조치·증거·요청/결정 이력 |
| POST /api/v1/reviews/{approval_id}/approve | reason·Approval expected_version·Idempotency-Key 필수, Incident 결과 |
| POST /api/v1/reviews/{approval_id}/reject | 동일 계약, 반려 후 기존 ACTION_PROPOSED 흐름 재사용 |

Incident expected_version과 Approval expected_version을 혼용하지 않습니다. approval.version은 Review 응답에서 얻습니다. reason은 공백이 아닌 1~2000자이며 추가 필드는 거부합니다. Idempotency-Key는 영문/숫자와 . _ : -로 구성한 1~128자입니다. Authorization: Bearer <서버 등록 개발 토큰>과 선택적인 X-Request-ID를 보냅니다.

Review의 actions.allowed/reason은 서버가 역할·매장·결정 여부·기한·조치 변경을 계산한 값입니다. edit/request_more_evidence는 아직 HTTP command가 없으므로 명확한 사유와 함께 비활성화합니다. evidence_completeness는 등록 증거 중 AVAILABLE 비율이며 별도 정책 엔진이 평가한 증거 품질 점수가 아닙니다. 임의 status PATCH는 여전히 제공하지 않습니다.

등록 계정은 기존 Incident approve/reject 경로로 사유 입력을 우회할 수 없습니다. 해당 경로는 422 REVIEW_COMMAND_REQUIRED와 검토 대기함 안내를 반환하며, Incident permission도 비활성화됩니다. 기존 기본 개발 계정에만 사유 미입력을 명시한 호환 경로를 유지합니다. Incident의 실행 permission도 boolean만 보지 않고 실제 승인 기록과 기한을 확인합니다.

## 실행 및 검증

### Backend와 개발 계정

backend/에서 실행합니다. 기본 메모리 모드는 DB 없이 동작하는 개발 예시이며 프로세스를 다시 시작하면 승인·감사·멱등성 기록도 사라집니다. 영속 운영 경로를 확인하려면 SERVIQ_REPOSITORY=postgres와 SERVIQ_DATABASE_URL을 먼저 지정하고 migration을 실행하세요.

```powershell
cd backend
$env:SERVIQ_REPOSITORY = 'postgres'
$env:SERVIQ_DATABASE_URL = '<전용 개발 DB 연결 문자열>'
uv run python -m src.infrastructure.migrations
uv run fastapi run
```

기본 서버 바인딩은 0.0.0.0입니다. 로컬 접근만 허용하려면 uv run fastapi run --host 127.0.0.1을 사용합니다. backend/에는 package.json이 없으므로 npm install을 실행하지 않습니다.

등록 계정을 사용하려면 같은 Backend 셸에서 다음처럼 개발 전용 매핑을 지정한 후 서버를 실행합니다. 아래 토큰은 설명용 값이지 운영 비밀이 아닙니다.

```powershell
$env:SERVIQ_ENV = 'development'
$env:SERVIQ_IDENTITY_PROVIDER = 'local'
$env:SERVIQ_LOCAL_IDENTITIES = '{"local-operator-demo":{"principal_id":"operator-demo","tenant_id":"tenant-demo","roles":["OPS_MANAGER"]},"local-reviewer-demo":{"principal_id":"reviewer-demo","tenant_id":"tenant-demo","roles":["REVIEWER"]},"local-reader-demo":{"principal_id":"reader-demo","tenant_id":"tenant-demo","roles":["AUDITOR"]}}'
uv run fastapi run --host 127.0.0.1
```

매핑을 설정하면 익명 기본 계정을 사용하지 않습니다. 해당 계정으로 조회하려면 등록 토큰이 필요하고, Incident 명령도 Idempotency-Key가 필수입니다. 개발 계정을 바꾸면 tenant 범위와 허용 업무도 달라집니다. 키가 없으면 422 IDEMPOTENCY_KEY_REQUIRED, 없는 토큰은 401 INVALID_CREDENTIALS입니다.

### Frontend

별도 터미널의 frontend/에서 npm ci와 npm run dev를 실행합니다. .env.local을 다음처럼 설정하고 Vite를 다시 시작합니다.

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_LOCAL_AUTH_TOKEN=local-reviewer-demo
```

개발 토큰은 개발 모드에서만 전송합니다. VITE_ 값은 브라우저에 공개되는 설정이므로 실제 비밀번호·OIDC client secret을 넣지 마세요. 운영 인증 토큰 전달 경로는 아직 구현하지 않았습니다. Incident 운영 계정으로 조치와 승인 요청을 만든 뒤 Reviewer 계정으로 검토할 수 있습니다. 기본 Mock 모드는 기존 demo/test 자료와 Action을 유지합니다.

HTTP Review는 실제 API의 로딩·오류·빈 목록·서버 permission을 표시합니다. 제출 중에는 중복 클릭을 막고, 연결 실패 후 같은 항목·결정·사유·버전으로 재시도하면 같은 키를 보냅니다. 결정 내용을 변경하면 새 사용자 요청으로 키를 새로 만듭니다. 성공 후 서버 목록을 다시 읽으며 UI가 다음 Incident 상태나 역할 정책을 결정하지 않습니다.

### 검증 명령

저장소 루트에서 실행합니다.

```powershell
uv run --extra dev ruff check .
uv run --extra dev pytest
$env:SERVIQ_TEST_DATABASE_URL = '<전용 테스트 DB 연결 문자열>'
uv run --extra dev python -m scripts.serviq_postgres_smoke
uv run --extra dev python -m scripts.serviq_security_smoke
$env:SERVIQ_TEST_API_BASE_URL = 'http://127.0.0.1:18080/api/v1'
uv run --extra dev python -m scripts.serviq_http_smoke
```

PostgreSQL smoke는 다른 Worker/업무 자료가 없는 전용 DB에서 실행합니다. 보안 smoke는 고유한 테스트 조직 자료를 만들며 감사 기록은 불변이므로 테스트 DB에 남깁니다. 감사 실패 테스트의 임시 제약은 finally에서 해제하고 외부 AI/실제 조치 서비스는 호출하지 않습니다. HTTP smoke에는 별도 Compose 스택과 nginx/API가 필요합니다.

frontend/에서는 npm ci → npm run lint → npm run test → npm run build를 실행합니다. Windows 실행 정책에 따라 npm.cmd를 사용할 수 있습니다. scripts/compose_smoke.ps1은 pgvector 스키마 준비·확장 존재·기존 Python health·native command 종료 코드를 확인합니다. 검증 전 COMPOSE_PROJECT_NAME을 전용 값으로 지정하세요. 기존 자료가 있는 볼륨을 삭제하는 절차가 아닙니다.

### Day 17 검증 기록

2026년 10월 3일 다음을 실제 확인했습니다.

| 검증 | 결과 |
| --- | --- |
| uv run --extra dev ruff check . | 통과 |
| uv run --extra dev pytest | 305 passed, 의존성 안내 경고 1개 |
| backend/ uv sync --locked·진입점/SQL import·fastapi run --help | 통과 |
| frontend/ npm ci | 설치 완료, 취약점 0건 |
| npm run lint·npm run test·npm run build·빌드 후 lint | 통과, 75 tests passed |
| 실제 PostgreSQL 기존 smoke | Repository·version·Outbox·lease·retry·DLQ·롤백 통과 |
| 실제 PostgreSQL 보안 smoke | Tenant/RBAC·승인/반려·불변 Audit·재시작/동시 Idempotency·전체 롤백 통과 |
| 실제 Compose 이미지/serviq 프로필/HTTP smoke | nginx·실제 Review·기존 Incident 종결 흐름 통과 |
| 실제 Worker | HTTP 흐름 상태 이벤트 9건 COMPLETED |
| 실제 API 컨테이너 재시작 후 승인 재전송 | 이전 결과 재사용, 종결 상태·version·Audit·Outbox 추가 변경 없음 |
| 강화한 compose_smoke.ps1 | pgvector 존재·스키마 초기화·기존 DB health 통과 |

로컬 Node.js 24.12.0의 일부 테스트 의존성에 EBADENGINE 경고가 있었지만 설치·테스트·빌드는 실제 성공했습니다. 새 환경은 Node.js 24 LTS 24.15.0 이상을 사용합니다. Python 경고는 Starlette TestClient의 httpx 사용 안내입니다. 경고를 숨기는 필터는 추가하지 않았습니다.

Docker 이미지 빌드와 동시에 실행한 프론트 검증에서 기존 팝업 테스트가 5초 제한을 넘겨 한 차례 실패했습니다. assertion과 timeout을 변경하지 않고 이미지 빌드 종료·검증용 Compose 중지 후 전체를 단독 재실행해 75개가 모두 통과했습니다. 초기 Compose smoke의 빈 pgvector 조회도 성공으로 기록하지 않고 검사 자체를 보강한 뒤 실제 통과를 확인했습니다. 검증용 볼륨과 기존 테스트 컨테이너는 보존했습니다. 원격 CI 결과는 PR에서 별도로 확인하며 로컬 결과를 원격 성공으로 간주하지 않습니다.

## 제한 사항

- 이번 Tenant/RBAC 적용 대상은 ServIQ Incident·Review API입니다. 기존 Streamlit·RAG·데이터 CLI 전체의 인증이 통합됐다는 뜻은 아닙니다.

- 실제 로그인/OIDC/Keycloak/SSO, JWT 서명·issuer·audience·만료 검증, 계정/조직 membership 영속화는 아직 없습니다. LocalIdentityProvider는 production authentication이 아니며 development/test 외 환경에서는 시작을 거부합니다.
- 서버 매핑을 지정하지 않은 기본 로컬 계정은 기존 실행 호환을 위한 legacy-local/HQ_ADMIN입니다. 이 계정의 기존 Incident 명령만 키 누락 시 새 키를 생성하므로 해당 예외에는 재전송 보호가 없습니다. Review command는 이 계정에도 키를 요구합니다. API를 인터넷에 공개하지 마세요.
- 기존 승인 boolean으로 승인 기록을 소급 생성하지 않습니다. 영속 Approval이 없는 기존 승인 대기 자료나 기한 경과 건의 갱신·복구 운영 명령은 후속 범위이며 우회 실행을 허용하지 않습니다.
- Idempotency 보관/만료 정책, 전용 DB 사용자 권한 분리·감사 WORM·백업/복원, 대규모 Review cursor/query 최적화와 설정별 승인 Policy Engine은 후속입니다.
- Review 수정·추가 증거 요청은 HTTP로 아직 연결하지 않았습니다. Mock에서만 예시 Action을 유지합니다. Incident 화면의 새로운 제출마다 키를 만들며, 동일 키의 UI 네트워크 재시도 보장은 이번 Day의 Review에 집중했습니다.
- 독립 Job/Queue 운영 Query, 실제 운영 집계·연동·Trace·Settings API, Jev, LLM Gateway, Gemini/Ollama runtime, LangGraph, Multi-Agent, Harness, MCP, production-ready deployment는 PLANNED입니다.

## 다음 단계

가장 큰 다음 Vertical Slice는 실제 Job/Queue API + Queue UI입니다. 기존 Outbox Worker를 전체 Queue 제품이 완성된 것으로 취급하지 않고, Tenant/RBAC·Idempotency·Audit 경계를 재사용해 조회·retry/DLQ 운영과 서버 permission을 연결합니다. OIDC·회원 범위·승인 갱신·운영 보관/복원은 별도의 완료 기준으로 추적합니다.

Google Drive v0.5의 Day 16 GAP 스냅샷과 이번 브랜치의 검증 결과를 구분해 이 문서에서 4대 GAP의 변화를 추적합니다. 원문이 이미 Day 17/main 병합 완료를 선언한 것처럼 수정하지 않았습니다. 검토·병합 이후 기준 main과 설계 추적표를 갱신하세요. 이 Day는 Issue #32와 브랜치 하나·PR 하나로 관리하고 자동 merge하지 않습니다.
