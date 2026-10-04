# Day 21 Jev Decision Layer와 Shadow 실행

## 목적

Day 20의 Versioned Control Plane 다음으로 실제 Incident와 해석된 설정을 받아 외부 AI 없이 판단하는 Jev를 추가합니다. Jev는 AI 모델이 아니라 실행 전에 위험과 조사 범위를 제한하는 결정적인 가드레일입니다. Frontend-first → Contract-first → pure decision → Config/Incident → PostgreSQL audit → Job Shadow → 조회 API/UI의 작은 Vertical Slice입니다.

기준 main은 `9e2d947e27f63c5f47667314c938cf8c2e0ad6dc`(Day 20 PR #39 병합)입니다. 직접 확인한 정본은 [ServIQ_v0.5_운영안전_실행계약_통합설계](https://drive.google.com/drive/folders/1eVwhcoTWaebKUqmJgdGMBF9xY7gXcmmJ)입니다. 루트 semantic version과 실제 20·21·22·23·25·28·37 문서를 대조했으며 v0.4/v0.4.1 fallback은 사용하지 않았습니다. Drive 원문은 수정하지 않았습니다.

Drive 일부 구현현황은 Day 16 스냅샷입니다. 실제 기준 main에는 Day 17 보안/Review, Day 18 Job/Queue, Day 19 Dashboard, Day 20 Settings가 있습니다. 오래된 Day/migration 번호를 복사하거나 기존 기능을 다시 구현하지 않습니다. Day 21 결과는 이 브랜치의 구현이며 PR 병합 전 main 완료로 표현하지 않습니다.

## 구성

### 책임과 비책임

```text
실제 incident.snapshot Job
  → Application: Tenant Incident + 현재 Config Version 조회/해석
  → 원문 없는 DecisionContext
  → Jev 순수 안전 규칙 + 프로필 + Engine
  → DecisionResult
  → Decision와 Audit 같은 트랜잭션 저장
  → 기존 Job 처리/ACK 계속
```

| 위치 | 책임 |
| --- | --- |
| `backend/src/decision/jev/` | 불변 계약, 입력 검증, 안전 gate, 위험도, 정렬된 프로필, 순수 Engine |
| `backend/src/application/decisions/` | Context/Config snapshot 전달, Shadow 실패 경계, 읽기 Query |
| `backend/src/application/ports/decision_repository.py` | 조직별 append/history/by-job 계약 |
| `backend/src/infrastructure/repositories/decision_repository.py` | Memory 테스트 어댑터와 PostgreSQL 감사 원본 |
| `backend/src/infrastructure/queue/runtime.py` | 기존 snapshot processor에 Shadow만 추가 |
| `backend/src/api/routes/decisions.py`, `schemas/decisions.py` | Principal/Tenant/store HTTP 조회 DTO |
| `frontend/src/api/decisions/`, `features/incidents/ShadowDecisionPanel.tsx` | 명시적 Mock/HTTP와 실제 판단 이력 |

Jev 안에는 DB/HTTP/Provider SDK/시간 생성/무작위 ID 생성이 없습니다. ID·Clock·처리 시간·저장은 Application 경계의 책임입니다. 같은 입력·Config·ruleset은 같은 의미 결과를 만듭니다. Incident 상태 변경, Approval 결정, Tool/LLM 호출, Provider/model 선택, Config 재조회, Agent 실행, LangGraph enqueue는 하지 않습니다.

`requires_human_review`는 실제 승인 권한이 아니고 `requires_llm`도 호출 명령이 아닙니다. 후속 실행 계층이 보안·승인·데이터 정책을 다시 검사해야 합니다.

### Decision Contract와 정규화

Context에는 tenant/incident/store 참조, 상태·severity·priority, category, 알려진 증거 유형, 데이터 가용성, recurrence hint, 요청 모드, resolved Config와 버전, 시간대가 있는 발생 시각만 전달합니다.

현재 Incident에는 별도 category/recurrence 필드가 없습니다. 제목이나 VOC를 분류하지 않고 증거 `type`이 TEMPERATURE/INVENTORY/LOT/SUPPLIER/HISTORY/TRANSACTION인 경우에만 정규화합니다. AVAILABLE 증거만 가용 데이터로 봅니다. TEMPERATURE는 COLD_CHAIN, LOT/SUPPLIER는 SUPPLIER_LOT, TRANSACTION은 TRANSACTION, 나머지는 UNKNOWN입니다. 재발 힌트는 근거 없는 추정 대신 false입니다. 실제 외부 연결 상태를 검증하는 Connector는 아닙니다.

Result에는 route/risk/priority, 정렬된 investigation_agents, LLM/사람 검토 필요 여부, workflow/budget 프로필, manual_reason, reason_codes, Config/ruleset 버전, SHADOW 모드가 있습니다. 저장 경계가 decision_id, source_job_id, input_digest, decided_at, duration_ms, Incident 버전, 안정적인 error_code를 추가합니다. 프로필은 향후 실행 식별자이며 실제 실행·비용 청구가 아닙니다.

### 안전 규칙과 Route/Profile

- CRITICAL + critical_manual_only, 금지 분류, 조직 자동 조사 off, 수동/assisted 요청, 조사 불가 상태는 수동 gate입니다. 후속 라우팅이 해제하지 못합니다.
- 기본 위험은 Severity입니다. 식품 안전/콜드체인은 최소 HIGH, 재발은 한 단계 상향, 증거 정보가 없으면 최소 MEDIUM이며 CRITICAL 이상은 늘리지 않습니다.
- DETECTED/TRIAGED/INVESTIGATING/REOPENED만 조사 후보 대상입니다. HIGH/CRITICAL은 P1으로 제안합니다.
- Agent allowlist와 가용 데이터의 교집합을 고정 순서로 선택하고 parallelism 상한을 적용합니다. 후보/데이터가 없으면 모든 Agent 대신 MANUAL_REVIEW입니다.
- 미확인 category는 일반 조사로 fallback하되 가용 후보가 없으면 수동입니다. 잘못된 타입/시간대/설정은 미확인 분류와 구분해 거부합니다.
- hosted_ai_allowed는 기본 false입니다. 거부 시 requires_llm=false와 PROVIDER_POLICY_DENIED를 남깁니다. true도 실제 전송 허가나 Provider Data Policy 완성을 의미하지 않습니다.

| Route | 고정 후보 순서 |
| --- | --- |
| COLD_CHAIN_INVESTIGATION | TEMPERATURE → INVENTORY → HISTORY |
| SUPPLIER_LOT_INVESTIGATION | LOT → SUPPLIER → INVENTORY → HISTORY |
| HISTORY_RECURRENCE | HISTORY → TRANSACTION |
| TRANSACTION_INVESTIGATION | TRANSACTION → HISTORY |
| GENERAL_INVESTIGATION | HISTORY → TRANSACTION → INVENTORY |
| MANUAL_REVIEW | 없음 |

COLD_CHAIN/FOOD_SAFETY, SUPPLIER_LOT, recurrence, TRANSACTION, 일반 순서로 결정합니다. FOOD_SAFETY는 콜드체인 프로필에 대응하지만 실제 Incident 정규화에서 원문으로 식품 안전 분류를 추론하지 않습니다. 이유 코드는 중복 없이 결정적인 순서를 유지합니다.

### Day 20 Config 연동

새 Jev 설정 저장소를 만들지 않습니다. 기존 RuntimeConfig/ConfigVersion/ConfigResolver에 critical_manual_only, hosted_ai_allowed, allowed_agent_types, blocked_categories를 추가했습니다. 이전 JSON은 안전 기본값으로 읽고 변경/history/rollback/RBAC/Idempotency는 기존 Settings 경계를 재사용합니다. RESTRICTED는 금지 분류에서 해제할 수 없습니다.

기본 Jev는 off이며 `jev_enabled=true` 이후 처리되는 Job에만 적용됩니다. 자동 조사 off는 기록 자체를 금지하지 않고 수동 gate를 만듭니다. Application이 **Job 처리 시점의 현재 Config**를 해석하고 결과에 버전을 보존합니다. 이미 기록한 Job/ruleset 재전달은 설정이 바뀌어도 원래 Decision을 반환합니다.

Config의 승인·자동화·병렬 한도와 system cap을 재사용합니다. 실제 Worker concurrency·승인자 수·Provider enforcement를 완성한 것은 아닙니다. Settings의 NOT_CONNECTED 표시는 미래 LLM/Agent 실행 Runtime이며 Jev만 Shadow로 연결됩니다.

### 영속 감사와 데이터 보호

additive `db/migrations/009_jev_decisions.sql`로 `serviq_decisions`를 추가했습니다. 기존 001~008은 수정하지 않습니다. tenant/incident/job/config 복합 참조, Job/ruleset 유일성, 조직별 Incident 이력 index, UPDATE/DELETE 금지 trigger를 사용합니다. Config 버전 0은 플랫폼 기본값이며 실제 저장 버전만 FK로 연결합니다.

Decision은 append-only 판단 감사이고 일반 Audit은 actor/command/result 기록입니다. 두 개념을 합치지 않습니다. 같은 UoW에서 Decision와 `jev_shadow` Audit을 저장하며 감사 실패 시 둘 다 롤백합니다. actor는 job-worker, request ID는 Job ID, correlation ID는 기존 Job 값을 보존합니다. PostgreSQL 조직/Job advisory lock과 유일성으로 동시 중복 전달을 막습니다.

고객 이름/전화/이메일/주소/raw VOC/증거 전문/prompt/secret/credential은 Context나 Decision/Audit에 복제하지 않습니다. 안전한 참조·정규화 정보·Config snapshot으로 input_digest를 만들고 digest만 저장합니다. HTTP에는 digest와 tenant 내부 정보도 반환하지 않습니다. hosted LLM 전송 자체가 없습니다.

### API와 운영 UI

| Endpoint | 의미 |
| --- | --- |
| `GET /api/v1/incidents/{incident_id}/decisions` | 최근순 이력, limit 1~100(기본 20), offset 0~10000, has_more |
| `GET /api/v1/incidents/{incident_id}/decisions/latest` | 최신 판단 또는 null |

기존 Principal/read RBAC, Tenant-scoped Incident 조회, store 권한을 재사용합니다. 다른 조직 ID는 404, 매장 권한 부족은 403, 인증 없음은 401, query validation은 422, 저장소 실패는 503 DECISIONS_UNAVAILABLE입니다. 공개 POST 생성 API는 없습니다.

Incident 팝업의 실행 추적 탭에서 최신 5건부터 이력을 조회·페이지 이동·새로고침합니다. Shadow 배지, route/위험/우선순위, 사람 검토/LLM 필요 여부, 미실행 조사 후보, 한국어 근거/reason code, Config/ruleset/Incident 버전, 판단 시각·처리 시간·원본 Job을 표시합니다.

화면은 “현재 Jev 판단은 실행 경로를 변경하지 않습니다. Agent/LLM 자동 실행은 아직 연결되지 않았습니다.”라고 안내합니다. 기존 Agent Trace 예시는 별도 Mock 영역으로 유지합니다. Mock 모드는 판단 이력을 만들어 표시하지 않습니다. HTTP 실패는 loading/empty/error/권한 안내로 구분하고 fixture로 대체하지 않습니다. 실패 기록은 정상 AI 분석 완료로 표시하지 않습니다.

## 실행/검증

Backend와 Frontend의 독립 실행 경로를 유지합니다.

```bash
cd backend
uv sync --locked
uv run --locked fastapi run
```

```bash
cd frontend
npm ci
npm run dev
```

지원 Node.js 24.15 이상을 사용합니다. 실제 API는 `VITE_API_MODE=http`, `VITE_API_BASE_URL=http://localhost:8000/api/v1`로 연결하고 [Day 17](serviq_access_review.md)의 서버 등록 개발 계정을 사용합니다. 조직 관리자 계정으로 Settings에서 Jev를 켠 뒤 새 Incident 작업을 처리하세요. 기존 완료 Job을 재실행하거나 공개 판단 생성 API를 호출하지 않습니다.

루트에서 `uv run --extra dev ruff check .`, `uv run --extra dev pytest`를 실행합니다. Frontend에서 `npm ci`, `npm run lint`, `npm run test`, `npm run build`를 실행합니다. 전용 DB의 SERVIQ_TEST_DATABASE_URL을 지정한 뒤 루트에서 실제 smoke를 실행합니다.

```bash
uv run --extra dev python -m scripts.serviq_postgres_smoke
uv run --extra dev python -m scripts.serviq_security_smoke
uv run --extra dev python -m scripts.serviq_queue_smoke
uv run --extra dev python -m scripts.serviq_dashboard_smoke
uv run --extra dev python -m scripts.serviq_settings_smoke
uv run --extra dev python -m scripts.serviq_jev_smoke
uv run --extra dev python -m scripts.serviq_http_smoke
```

HTTP smoke는 테스트 nginx의 SERVIQ_TEST_API_BASE_URL을 지정합니다. Compose/기존 PowerShell smoke는 [실행·CI/CD 문서](serviq_delivery.md)를 따릅니다. 사용자 DB를 삭제/검증 대상으로 사용하지 않습니다.

### 실제 검증 결과

- 전체 ruff 통과, 전체 Python **410 passed**, 기존 Starlette/httpx deprecation 경고 1건입니다. 테스트 삭제/skip/xfail/assertion 약화/timeout 변경은 없습니다.
- Jev 회귀 표 24개와 입력·현재 cap·순수 계층·Config propagation·중복 전달·실패 격리·API 보안 테스트가 통과했습니다.
- backend/ `uv sync --locked`, `uv run --locked fastapi run --help` 통과했습니다. Windows cp949에서 CLI emoji 출력이 실패한 뒤 PYTHONUTF8=1로 성공을 재확인했습니다.
- Node.js 24.21.0에서 npm ci 성공(취약점 0건), lint 통과, **20개 파일 127 passed**, 실제 production build 통과입니다. 첫 npm ci는 Vite의 rolldown 파일 잠금으로 EPERM이 발생했고 해당 서버만 중지한 뒤 동일 명령으로 성공했습니다.
- 실제 PostgreSQL·security·Queue·Dashboard·Settings·Jev smoke 6종 통과입니다. 기존 smoke의 깨끗한 DB 전제를 지켜 별도 Day 21 DB에서 실행했습니다. 초기 실패가 남긴 테스트 DB와 사용자 DB는 보존했습니다.
- Jev DB smoke는 실제 Worker 완료, 재시작·동시 재전달의 단일 감사, Config lineage, Tenant/store, PII 미노출, UPDATE/DELETE 차단, Engine 실패 수동 기록, Audit 실패 원자 롤백을 검증했습니다. 실패 주입 시 stable 오류 로그는 예상한 결과이며 성공으로 숨기지 않습니다.
- 전용 Compose build/up/migration/DB·API·nginx·Worker health와 HTTP smoke 통과입니다. Incident/Review/Queue/Dashboard/Settings 회귀와 Shadow history/latest를 확인했습니다. 최종 Outbox 14건·Job 2건 COMPLETED, Decision 1건 SHADOW입니다.
- 기존 `scripts/compose_smoke.ps1`도 별도 legacy 프로젝트에서 pgvector·Python 스키마·health를 검증했습니다. 검증용 Compose는 중지하고 볼륨과 사용자 DB는 보존했습니다.
- CI에 Jev PostgreSQL smoke를 추가했고 Docker HTTP 단계에 Shadow 검증을 포함합니다. 원격 Actions 상태는 PR에서 별도 확인하며 로컬 통과를 원격 통과로 표현하지 않습니다.

### 10개 커밋 경계

1. feat: Jev Decision 계약과 Shadow 운영 표현 정의
2. feat: Jev 안전 규칙과 위험도 판정 구현
3. feat: Jev 라우팅과 조사 프로필 선택 구현
4. feat: Jev Engine과 Runtime Config 정책 연결
5. feat: Jev Decision Audit 영속 저장소 추가
6. feat: Job 처리 경로에 Jev Shadow Decision 연결
7. feat: Jev Decision 조회 API와 Tenant 경계 추가
8. feat: 운영 화면에 실제 Jev Shadow Decision 연결
9. test: Jev Decision Layer와 Shadow 실행 회귀 검증 강화
10. docs: 21일차 Jev Decision Layer와 Shadow 실행 완료

실제 SHA는 PR Commit 목록과 `git log main..HEAD`로 확인합니다. 1~8 기능, 9 테스트/CI, 10 문서만으로 구분하고 최종 커밋 수와 clean tree를 확인합니다.

## 제한 사항

IMPLEMENTED는 deterministic 위험/route/프로필/근거, Runtime Config snapshot, append-only Decision/Audit, 실제 Job Shadow, Tenant/store Query API와 UI입니다.

판단 실패는 DECISION_VALIDATION_ERROR 또는 DECISION_INTERNAL_ERROR 수동 기록과 FAILED Audit으로 관측합니다. **저장소 자체가 실패하면** 저장했다고 표시하지 않고 DECISION_PERSISTENCE_UNAVAILABLE 로그를 남깁니다. 기존 Job 완료는 원래 snapshot 업무 완료이지 Shadow 성공 보장이 아닙니다. 저장 실패의 별도 재처리/DLQ나 metric backend는 이번 Day 범위가 아닙니다.

아직 구현하지 않은 항목:

- 실제 LLM Gateway, Gemini/Ollama 호출, structured output/Provider Data Policy
- Jev 결과 기반 workflow enqueue, LangGraph, AgentRun, Multi-Agent/fan-out/fan-in
- 실제 Tool/external action, Harness, MCP, 실제 Connector
- production OIDC/SSO, production deployment/Production Readiness 전체
- Redis 신규 도입, 실제 tenant concurrency/backpressure 정책 적용
- 별도 Incident category/재발 근거 원본, 실제 Integration/SyncJob/Agent Trace 원본

local/dev Principal은 production authentication이 아닙니다. Jev 후보/승인 필요 여부는 advisory이며 실제 승인 경계를 대체하지 않습니다. “Jev 판단으로 Gemini/LangGraph/Multi-Agent를 자동 실행한다”는 설명은 아직 사실이 아닙니다.

## 다음 단계

Day 21 병합 이후 최신 main·열린 PR·Drive 버전을 다시 확인합니다. 현재 후속 후보는 Provider-neutral LLM Gateway 계약 → FakeProvider → 구조화 응답 → timeout/retry/error taxonomy → Data Policy → Gemini/Ollama 어댑터입니다. Day 22 구현을 이번 Day에 미리 넣지 않습니다.
