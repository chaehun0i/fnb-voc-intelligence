# ServIQ 프로젝트 구조 — AI Architecture Simplification

## 코드를 찾는 기준

`backend/`, `db/`, `frontend/` 실행 경계와 Day 26 Closed Loop를 유지하며 AI 코드를 다섯 책임으로 통합했습니다. **Decision, Intelligence, Workflow, Execution, AX**만 기억하면 Runtime을 찾을 수 있습니다. 상세 측정·검증·제한은 [Architecture Simplification](serviq_architecture_simplification.md)을 참고합니다.

```text
backend/src/
├─ ai/
│  ├─ models.py          # SDK 독립 frozen/sensitive-field 공통 계약
│  ├─ decision/          # models / pure engine / Shadow·query service
│  ├─ intelligence/      # models / Gateway service / node composition·prompts
│  │  └─ providers/      # Fake / Gemini SDK / Ollama HTTP adapter
│  ├─ workflow/          # models / agents / policy / graph / runtime
│  ├─ execution/         # 내부 실행·검증 / Harness / tools·bound runtime
│  └─ ax/                # 기존 안전한 실행 Trace projection/query service
├─ domain/               # Incident·Approval·Job·Config 순수 규칙
├─ application/          # 공유 권한·업무 Command/Query
│  └─ ports/             # repositories.py / identity_provider.py
├─ infrastructure/       # tenant-scoped Repository·Outbox·Job Worker
├─ api/                  # HTTP routes·DTO·인증 dependency
├─ mcp/                  # 공식 SDK private in-memory adapter (안전 정책은 Execution)
└─ data·rag·ingestion·analysis·dashboard·config/ # 기존 Data Intelligence

frontend/src/
├─ features/
│  ├─ incidents/         # Incident 화면 + api.ts
│  ├─ reviews/           # 기존 Review + api.ts
│  ├─ operations/        # Queue·Integrations + api.ts
│  ├─ settings/          # Control Plane + api.ts / types.ts
│  ├─ dashboard/         # KPI + api.ts
│  └─ ai/                # 실제 Trace·Decision API·응답 decoder
├─ shared/               # api.ts의 연결·인증 / Mock fixture·adapter
├─ contracts/            # 공유 업무 DTO (generated contract 중복 없음)
├─ components/           # 공통 UI
└─ app·lib·test/          # 앱 조립·표시 도우미·테스트 fixture
```

Decision=Jev, Intelligence=LLM+LangChain Node composition, Workflow=LangGraph+최소 Multi-Agent+bounded Loop, Execution=Harness/Business Tool 안전 경계, AX=Agent Experience입니다. 문서의 9개 개념은 유지합니다. 현재 Execution은 **내부 실행/Verification Command·승인 재검증·read Tool Harness**를 포함하고 MCP adapter는 이를 호출합니다. Connector write·외부 Action reconciliation 전체는 미구현입니다. AX는 안전한 Trace·조사 진행·근거 범위·Loop 제어·Tool 업무 상태를 투영하며 새 자율 AI Brief 정책은 추가하지 않았습니다.

## 안전 경계

순수 계약/Decision은 DB·HTTP·Graph·Provider를 import하지 않습니다. Workflow Node는 repository 구현체나 Provider SDK 대신 Port와 Gateway를 사용합니다. Intelligence는 Domain 상태를 변경하지 않고 내부 실행/Verification은 기존 Application/Domain invariant를 통과합니다. LangGraph는 Domain State Machine을 대체하지 않습니다.

Repository Protocol 9개는 `application/ports/repositories.py`로 통합하고 IdentityProvider는 독립 유지합니다. AccessUnitOfWork는 keyword-only이며 transaction/rollback/lock semantics는 동일합니다. IncidentCommands는 명시적 public method와 공통 auth/idempotency/audit helper를 사용합니다. 새 DI framework나 compatibility shim은 없습니다.

Job Worker의 `src.infrastructure.jobs.runtime` 진입점과 Outbox dispatch·claim/lease 책임은 유지합니다. Config version은 Run 시작 때 고정하며 AgentRun/business trace와 LangGraph Checkpoint는 분리합니다. 프론트엔드는 `shared/api.ts`에서 공통 연결·인증·명령 키를 가져오고 기능 API는 화면 옆에서 찾습니다. Review의 Incident DTO decoder 재사용, 서버 permission source of truth, HTTP 실패 시 Mock fallback 금지는 동일합니다.

## 실행·검증

`backend/`는 루트 Python 프로젝트를 editable dependency로 사용하며 실제 구현은 `backend/src/`의 `src` 패키지입니다. 루트와 backend lockfile, 기존 CLI/RAG/Streamlit을 유지합니다. `src.infrastructure.migrations`는 현재 `db/migrations/001`~`023`을 패키지 리소스로 읽습니다. 구조 리팩토링 당시에는 018까지였으며 Day 29는 새 DB schema/migration 없이 기존 AgentRun document에 안전한 Tool receipt를 추가합니다.

```bash
# backend 디렉터리
uv sync --locked
uv run --locked fastapi run --help
uv run fastapi run
# repository 루트
uv run --extra dev ruff check .
uv run --extra dev pytest
uv run --project backend python -m src.infrastructure.migrations
# frontend 디렉터리
npm ci
npm run dev
npm run lint
npm test -- --run
npm run build
```

FastAPI 기본 바인딩은 `0.0.0.0`이며 로컬만 허용하려면 `--host 127.0.0.1`을 사용합니다. Compose API/nginx는 localhost 제한을 유지합니다. 실제 DB는 `SERVIQ_REPOSITORY=postgres`, `SERVIQ_DATABASE_URL`로 지정하고 개발 예시가 필요한 때에만 `SERVIQ_SEED_DEMO=true`를 사용합니다. frontend 기본은 Mock이며 `.env.local`의 `VITE_API_MODE=http`, `VITE_API_BASE_URL=http://localhost:8000/api/v1`로 실제 API에 연결합니다. 비밀 정보는 커밋하지 않습니다.

PostgreSQL은 고정 Compose 프로젝트 **serviq**의 `db`를 사용합니다. 컨테이너는 `db:5432`, 호스트는 `127.0.0.1:${POSTGRES_PORT:-5432}`입니다. 개발 DB/볼륨은 보존하며 검증 DB만 격리합니다.

## 측정·제한

`main@9eacffb` 대비 백엔드 Python 모듈 **196→167**, AI 모듈 **46→25**, 최상위 패키지 **13→11**입니다(`__init__.py` 포함, cache 제외). AI 구현 모듈은 42→18개, 최대 runtime은 569줄입니다. 파일 수만 줄이지 않고 순수 계약·조사·정책·Graph·Application 연결을 분리했습니다.

Public API, DB schema, Checkpoint payload, Runtime behavior는 동일합니다. 구조 테스트는 특정 파일 존재 대신 dependency direction·SDK 격리·repository 구현체 금지·순환 의존을 검사합니다. 기존 테스트를 삭제/skip/xfail/약화하지 않습니다. 이전 Day 문서의 검증 수는 당시 결과이며 최신 검증은 리팩토링 문서를 따릅니다.

Day 27의 정적 Registry·capability-aware 선택·최소 reference Context·3개 read-only branch와 fan-in/복구/업무 AX는 [Multi-Agent 문서](serviq_multi_agent.md)를 따릅니다. Workflow 영역을 다시 Agent별 package로 분할하지 않았고 read-only source adapter 하나만 추가했습니다. 적용 migration은 additive `019_multi_agent.sql`까지입니다. 기존 단일 History v1~v4와 내부 실행/Verification의 의미는 유지합니다.

Day 28은 기존 Workflow/Execution 책임 안에 제한 Loop·Harness·Manifest·사람 제어를 추가했습니다. `application/data_intake.py`/`intake_schema.py`, `infrastructure/data_intake.py`/`intake_workbook.py`, `features/data`는 온보딩/입력/첫 조사를 담당하며 별도 AI framework가 아닙니다. additive migration은 `020_loop_harness.sql`, `021_data_intake.sql`입니다. 실제 계약/검증은 [Loop/Harness](serviq_loop_harness.md)와 [첫 사용 가이드](serviq_onboarding_import.md)를 따릅니다.

Day 29의 `intelligence/node.py`·`prompts.py`, `execution/tools.py`·`runtime.py`, `application/tool_queries.py`, `mcp/server.py`는 좁은 composition/read Tool 경로를 담당합니다. MCP transport는 안전 정책을 소유하지 않습니다. 상세 책임·버전·검증·제한은 [LangChain/MCP](serviq_langchain_mcp.md)를 따릅니다.

Day 30은 기존 AX 영역의 `models.py`/`projector.py`/`actions.py`/`explanations.py`/`service.py`로 Incident 단위 업무 projection을 제공합니다. `releases.py`와 `measurement.py`는 per-run RC snapshot/Golden 비교 및 제한된 ProductEvent/지표를 담당합니다. 기존 Domain/Workflow/Execution 안전 경계는 유지합니다. additive migration은 `022_ax_product_events.sql`이며 상세 결과는 [AX/AI MVP RC](serviq_ax_mvp_rc.md)를 따릅니다.

Day 31의 `ai/ax/validation.py`는 순수 과업/Session/Journey 계약, 기존 `measurement.py`는 표본·availability를 가진 지표 projection입니다. `application/user_validation.py`가 권한·동의·실제 Incident/Approval/AgentRun 상태·영속 멱등성을 연결하고 `api/routes/user_validation.py`는 bounded HTTP 경계를 제공합니다. 기존 ProductEvent repository와 UoW를 확장하며 additive `023_user_validation.sql`만 추가합니다. `features/ai/ValidationMode.tsx`와 `ValidationSummary.tsx`는 기존 화면의 선택형 관찰 모드와 관리자 요약입니다. 별도 Analytics framework나 Incident 상태 머신은 없습니다. [User Validation](serviq_user_validation.md)의 Synthetic 결과는 실제 사용자 검증이 아닙니다.

production OIDC/SSO·deployment, 전체 retention/migration engine, 고급 Context enrichment·동적 Registry·자율 planner, public MCP endpoint, 외부 Action reconciliation 전체는 후속 범위입니다. 승인된 내부 실행을 실제 외부 변경과 구분하며 Jev Shadow 전체를 자동 실행하지 않습니다. 현재는 AX/AI MVP RC이지 Production Ready가 아닙니다. 다음은 실제 사용자 과업 관찰·AX friction 개선·Golden 재검증과 필요한 Productionization입니다.
