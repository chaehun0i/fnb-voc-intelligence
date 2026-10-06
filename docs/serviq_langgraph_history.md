# Day 23 LangGraph History Investigation

## 목적

Day 22 LLM Gateway 다음에 단일 History Investigation을 연결합니다. 실제 Incident 하나를 조사하고, 중단 후 같은 실행을 복구하며, 근거 출처와 실행 추적을 운영 화면에서 확인하는 작은 Vertical Slice입니다. LangGraph는 Incident 상태머신을 대체하지 않습니다.

기준 main은 `ffbebcfe679f06a427481c2b9668a84ec2c89c92`이며 Day 22 PR #43 병합 상태입니다. 설계 정본은 [ServIQ v0.5 운영안전·실행계약 통합설계](https://drive.google.com/drive/folders/1eVwhcoTWaebKUqmJgdGMBF9xY7gXcmmJ)입니다. 작업 시작 시 더 높은 버전은 없었고 fallback을 사용하지 않았습니다. 문서 00·07·08·09·15·20·25·28의 실제 내용을 대조했으며 Drive 원문은 수정하지 않았습니다.

Drive 일부 구현현황은 Day 16 스냅샷입니다. 실제 main의 Day 17~22 Tenant/RBAC·Approval/Audit/Idempotency·Review·Job/Queue·Dashboard·Control Plane·Jev·Gateway를 현재 기준선으로 유지합니다. 이번 작업은 Issue #44 하나와 `codex/day-23-langgraph-history` 브랜치 하나로 진행하며 자동 병합하지 않습니다.

## 구성

### 실행 계약과 책임

`명시적 Application 요청 → 기존 Job → AgentRun → LangGraph → History 검색 → 결과 저장/Checkpoint → Trace API/UI` 순서입니다.

| 위치 | 역할 |
| --- | --- |
| `backend/src/ai/workflow/models.py`, `policy.py` | SDK 독립 AgentRun·WorkflowState·Finding·EvidenceCandidate·EvidenceGap·Step 계약과 실행 허용 정책 |
| `backend/src/ai/workflow/agents.py`, `runtime.py` | 조사 Node·Jev/Config 원본 고정·승인 Application 경계 |
| `backend/src/ai/execution/service.py`, `backend/src/ai/ax/service.py` | 내부 실행/검증 Command·Tenant/store 실행 Trace Query |
| `backend/src/ai/workflow/graph.py`, `runtime.py` | 단일 Graph·JSON Checkpoint·Worker 실행 복구 (순수 계약과 import 경계 분리) |
| `backend/src/infrastructure/history_search.py` | 기존 SearchService와 조직/매장 출처 연결 |
| `backend/src/infrastructure/repositories/agent_run_repository.py` | 운영 실행 원본과 단계 이력 저장 |
| `backend/src/api/routes/agent_runs.py` | 인증된 조회 전용 API |
| `frontend/src/features/ai/`, `features/ai/HistoryTrace.tsx` | 실제 HTTP 계약과 한글 실행 추적 |

AgentRun은 운영 조회 원본이며 LangGraph Checkpoint는 실행 복구 상태입니다. 두 entity를 합치지 않습니다. Run에는 Tenant/Incident/Job/workflow/correlation/Config/Jev 원본과 실행 상태가 남습니다. WorkflowState에는 참조, 고정된 Finding 코드, 증거 후보, 근거 공백, 반복/호출/토큰/비용만 저장합니다. 상태는 `RUNNING / COMPLETED / FAILED`이며 완료된 실행은 임의로 다시 변경하지 않습니다.

### 영속 저장과 durable Graph

기존 migration을 수정하지 않고 다음 파일을 추가했습니다.

- `011_agent_runs.sql`: `serviq_agent_runs`, `serviq_agent_steps`. Tenant/Incident/Job/Config/Decision FK와 동일 Tenant/Job의 유일 실행 경계, 추가 전용 단계 이력입니다.
- `012_history_sources.sql`: 조직/매장별로 사용할 수 있는 Review 출처 연결입니다. 기존 Product/Review 원본 스키마는 유지합니다.
- `013_history_effects.sql`: 실행별 외부 호출 전 claim입니다. 중단 후 결과가 불확실한 외부 호출을 자동 재실행하지 않습니다.

공식 LangGraph/PostgresSaver가 관리하는 Checkpoint 테이블은 별도입니다. `thread_id=workflow_id`는 stable UUID이며 인증에 문자열 파싱을 사용하지 않습니다. 테스트는 InMemorySaver, 실제 PostgreSQL은 PostgresSaver와 `durability="sync"`를 사용합니다. JSON 전용 serializer는 pickle이나 임의 클래스 복원을 거부합니다.

Graph는 `validate_context → history_investigation → persist_result → END`입니다. 노드 입출력을 다시 검증하고 저장 실패 시 다음 업무 단계로 진행하지 않습니다. 다음 노드가 없다는 이유만으로 완료로 판단하지 않으며, 실제 저장 상태가 `COMPLETED`인지 확인합니다. AgentRun 완료는 최종 Checkpoint 저장 뒤에만 기록합니다.

### History 조사와 검색 출처

기존 SearchService/hybrid/pgvector 경계를 재사용합니다. lexical/vector SQL 모두 `serviq_history_sources`의 Tenant/store를 필터링한 뒤 상위 결과를 선택합니다. 원본 데이터가 전역 VOC 테이블에 있다는 이유로 모든 조직에 공개하지 않습니다. 신뢰할 수 있는 데이터 적재 경계에서 조직/매장 출처를 연결해야 하며, 연결이 없으면 `NO_AUTHORIZED_HISTORY`를 반환합니다.

증거 후보는 `review:<원본 ID>`, 순위, 검색 시각입니다. Finding은 관련 이력이 존재한다는 정규화 코드와 출처 참조만 보존합니다. RAG의 생성 답변을 Evidence source로 취급하지 않습니다. 원문은 검색 내부에서만 사용하고 Graph/Trace에 복사하지 않습니다.

기본 Worker는 추가 임베딩 서비스 없이 hybrid의 lexical 경로를 사용합니다. pgvector 임베딩 어댑터를 주입한 실제 DB smoke에서는 lexical/vector 두 경로의 출처 격리를 함께 검증했습니다. 실제 임베딩 Provider 운영 연결을 완료했다고 주장하지 않습니다.

### Jev·Config·Gateway 경계

시작은 내부 `HistoryWorkflows.enqueue(RequestContext, incident_id, decision_id)`로 명시적으로 요청합니다. 공개 arbitrary Agent POST는 없습니다. 서버 operate 권한, Tenant/store, 최신 Config와 Decision 일치, HISTORY 후보, 지원 profile, `TRIAGED / INVESTIGATING`, `jev_enabled`, `auto_investigation`, `voc.search` 허용을 확인합니다. 동일 Decision 요청은 같은 Job을 반환하고 새 업무 효과를 만들지 않습니다.

AgentRun은 시작한 Config Version을 고정합니다. 중간에 설정 v2가 생성되어도 기존 Run은 v1으로 복구합니다. Jev Shadow 전체를 자동 실행으로 전환하지 않으며 `requires_human_review`가 실제 Approval 검증을 대신하지 않습니다.

검색 근거가 있고 Jev가 `requires_llm=true`인 경우에만 Day 22 Gateway를 통해 정규화 보조 판정을 요청합니다. 전송 입력은 근거 개수와 출처 ID이며 원문 VOC가 아닙니다. Provider 선택·Data Policy·schema·예산·deadline은 기존 Gateway/Control Plane 책임입니다. Node는 Gemini/Ollama SDK를 import하지 않습니다. 정책 거부는 `LLM_POLICY_DENIED`, 사용 불가/제한은 `LLM_UNAVAILABLE`로 근거 공백에 남기며 검색 출처는 유지합니다.

### Job·중단·중복 전달

기존 JobWorker가 `incident.history_investigation`을 처리합니다. 별도 Queue를 추가하지 않았습니다. PostgreSQL advisory 실행 잠금과 lease heartbeat/fencing으로 동시 인수와 늦은 Worker를 차단합니다. 성공한 검색/정규화 결과는 Checkpoint와 별도로 Run에 메모화하므로 결과 저장 뒤 Checkpoint가 실패해도 재검색·재호출하지 않습니다.

호출 전 claim 이후 외부 Provider가 성공했는지 불확실한 crash는 자동 호출하지 않고 실패 이력으로 남깁니다. 이는 외부 호출의 exactly-once를 주장하는 방식이 아니라 중복 과금·효과를 보수적으로 차단하는 경계입니다. 수동 복구 정책의 확장은 후속 작업입니다. Worker/Graph 실패는 AgentRun/Job 실패이며 Incident를 직접 `FAILED`로 바꾸지 않습니다.

### API·운영 UI·보안

- `GET /api/v1/incidents/{id}/agent-runs`: 기본 20건, 최대 100건, offset 최대 10,000.
- `GET /api/v1/incidents/{id}/agent-runs/{run_id}`: 실행 원본·단계·근거 후보·공백·사용량·안전한 오류.

Principal 인증, Tenant repository scope, Incident store/RBAC를 재사용합니다. 다른 Tenant ID는 404, 허용되지 않은 매장은 403이며 잘못된 pagination은 422입니다. 저장소 장애는 안정된 503이고 내부 DB 오류 원문을 반환하지 않습니다.

HTTP 실행 추적 페이지와 Incident 상세의 실행 추적 탭은 실제 AgentRun을 표시합니다. loading/empty/error·수동 새로고침을 구분하고 HTTP 실패를 Mock으로 대체하지 않습니다. Mock의 미래 Multi-Agent 예시는 명시적인 Demo 모드에만 남깁니다. 원문 prompt/response, credential/access token, 개인정보 전문을 Run·Step·Checkpoint·API에 저장하거나 노출하지 않습니다. 임의 민감 필드는 모델 검증에서 거부합니다.

## 실행/검증

### 로컬 실행

기존 실행 구조를 유지합니다. Backend는 `backend/`에서, Frontend는 `frontend/`에서 시작합니다.

```bash
cd backend
uv sync --locked
uv run fastapi run
```

```bash
cd frontend
npm ci
npm run dev
```

Node.js 24 LTS `24.15.0` 이상을 사용합니다. 이번 최종 검증은 Node 24.19.0입니다. PostgreSQL 모드의 migration과 Queue Worker는 루트에서 실행합니다. `.env`는 로컬 파일이며 credential을 공유하거나 커밋하지 않습니다.

```bash
uv run --env-file .env python -m src.infrastructure.migrations
uv run --env-file .env python -m src.infrastructure.jobs.runtime --poll-seconds 2
docker compose --profile serviq up --build -d api frontend worker
```

Compose의 기본 프로젝트 이름과 예시 `.env`의 `COMPOSE_PROJECT_NAME`은 `serviq`로 고정합니다. Compose DB만 `127.0.0.1:${POSTGRES_PORT:-5432}`에 노출해 로컬 Backend도 같은 DB를 사용할 수 있습니다. 검증은 별도 DB를 사용하고 기존 개발 볼륨을 삭제하지 않습니다. 기존 별도 DB 이관은 데이터 확인과 명시적 승인 뒤 수행해야 하며 이 명령들이 자동 이관·삭제하지 않습니다.

이번 로컬 정리는 승인 후 과거 검증 DB 13개를 Compose PostgreSQL로 복사하고 모든 테이블 행 수를 대조했습니다. 별도 DB 컨테이너는 제거했고 원본 볼륨과 dump 백업은 보존했습니다. 운영 `fnb_voc`는 덮어쓰지 않았으며 root/backend의 로컬 연결과 실제 health가 같은 DB를 사용함을 확인했습니다. 과거 검증 스냅샷은 이름별 이력으로 남고 현재 운영 데이터와 섞지 않습니다.

### 검증 명령과 결과

루트에서 전체 범위를 실행했습니다.

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest
uv run --extra dev python -m scripts.serviq_postgres_smoke
uv run --extra dev python -m scripts.serviq_security_smoke
uv run --extra dev python -m scripts.serviq_queue_smoke
uv run --extra dev python -m scripts.serviq_dashboard_smoke
uv run --extra dev python -m scripts.serviq_settings_smoke
uv run --extra dev python -m scripts.serviq_jev_smoke
uv run --extra dev python -m scripts.serviq_llm_gateway_smoke
uv run --extra dev python -m scripts.serviq_langgraph_smoke
uv run --extra dev python -m scripts.serviq_http_smoke
```

DB smoke에는 `SERVIQ_TEST_DATABASE_URL`을 검증 전용 DB로 명시합니다. HTTP smoke는 `SERVIQ_TEST_API_BASE_URL`을 검증용 nginx `/api/v1`로 설정합니다. 실제 Gemini/Ollama 네트워크 호출은 필수 검증에 포함하지 않습니다.

| 검증 | 실제 결과 |
| --- | --- |
| 전체 Ruff / pytest | 통과 / 529 passed |
| Backend `uv sync --locked`, `fastapi run --help`, 앱·migration import | 통과 |
| Frontend `npm ci`, `npm run lint` | 통과, 지원 Node 24.19.0 |
| Frontend `npm run test` | 22개 파일, 144 passed |
| Frontend `npm run build` | 2회 통과, 빌드 후 lint 통과 |
| 기존 PostgreSQL·security·queue·dashboard·settings·Jev·Gateway smoke | 7개 모두 통과 |
| LangGraph 실제 PostgreSQL smoke | 통과, Checkpoint 실패 후 재시작·Config v1·Fake 호출 1회·외부 AI 0회 |
| HTTP/nginx | Incident·Review·Queue·Dashboard·Settings·Jev·AgentRun 조회 통과 |
| `scripts/compose_smoke.ps1` | 기존 DB/app·pgvector·health 통과 |
| ServIQ Compose 이미지·migration·nginx/API/Worker·LangGraph smoke | 통과, 개발 DB 복원 후 상태 확인 |

회귀는 실행 허용 정책, Config 고정, 민감 필드 거부, Data Policy deny, 중복 Job, 불확실한 호출 재실행 금지, 미완료 Checkpoint 복구, Tenant/store와 SDK 의존 경계를 포함합니다. 기존 assertion을 약화하거나 skip/xfail을 추가하지 않았습니다.

초기 `npm ci`는 실행 중 Vite의 바이너리 잠금으로 실패했습니다. 해당 저장소 서버만 중지하고 다시 설치했습니다. 초기 전체 테스트는 Worker 시작 timeout으로 실패했고, npm 자체까지 지원 Node를 명시하여 최종 144개를 오류 없이 통과했습니다. timeout을 늘리지 않았습니다. Windows FastAPI 도움말의 cp949 출력 문제는 `PYTHONUTF8=1`로 재검증했습니다. Compose smoke의 모듈 경로는 `exec --workdir /app`으로 바로잡았습니다.

CI에 PostgreSQL 및 Compose LangGraph smoke를 추가했습니다. 원격 Actions 상태는 PR에서 별도로 확인하며 로컬 통과를 원격 통과로 표현하지 않습니다. 커밋 경계는 계약 → 저장소 → Checkpoint → History → Jev/Config → Worker → API → UI → 테스트/CI → 문서의 정확히 10개이며 실제 SHA는 PR에 기록합니다.

## 제한 사항

IMPLEMENTED는 단일 History 조사, 운영 Run/Step, durable PostgreSQL Checkpoint, 출처 격리, 명시적 Job 실행, Config 고정, Gateway 사용 경계, 조회 API와 실제 Trace UI입니다.

다음은 미구현 또는 후속 범위입니다.

- Evidence fan-in/sufficiency의 업무 판정, RCA/CAPA Agent, Approval interrupt/resume, Verification Agent.
- Multi-Agent fan-out/fan-in, Supervisor, Harness, MCP, 실제 Connector.
- production OIDC/SSO·배포, 고급 tenant concurrency/backpressure.
- 실제 Gemini/Ollama 품질·장애·비용 운영 검증과 Provider exactly-once 보장.
- 공개 조사 시작 UI/API와 불확실한 외부 호출의 수동 복구 도구.

기존 RAG/Streamlit·ingestion·Product/Review·Incident·Review·Queue·Dashboard·Settings·Jev는 유지합니다. History의 후보는 아직 Incident Aggregate Evidence로 자동 승격하지 않습니다. 이번 결과를 Agent 전체 완성이나 production-ready라고 표현하지 않습니다.

## 다음 단계

최신 main/Drive를 다시 읽되 Day 30 MVP deadline의 핵심 경로를 유지합니다.

- Day 24: Evidence Fan-in / Evidence Sufficiency / RCA Draft.
- Day 25: CAPA / Human Approval interrupt·resume.
- Day 26: Verification / Incident Golden Workflow E2E.
- Day 27: 최소 Multi-Agent fan-out/fan-in.
- Day 28: 최소 Harness / MCP Business Tool.
- Day 29: Golden Evaluation / MVP Hardening.
- Day 30: MVP Release Candidate / 데모·Compose 재현성·전체 회귀.

시간이 부족하면 Agent 종류·Tool 개수·부가 UI를 줄입니다. Evidence provenance, Human Approval, Verification, Tenant/RBAC/Audit/Idempotency, Trace, 결정적 Golden Scenario와 Compose 재현성은 축소하지 않습니다.
