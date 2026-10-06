# ServIQ 프로젝트 구조 — AI Architecture Simplification

## 코드를 찾는 기준

`backend/`, `db/`, `frontend/` 실행 경계와 Day 26 Closed Loop를 유지하며 AI 코드를 다섯 책임으로 통합했습니다. **Decision, Intelligence, Workflow, Execution, AX**만 기억하면 Runtime을 찾을 수 있습니다. 상세 측정·검증·제한은 [Architecture Simplification](serviq_architecture_simplification.md)을 참고합니다.

```text
backend/src/
├─ ai/
│  ├─ models.py          # SDK 독립 frozen/sensitive-field 공통 계약
│  ├─ decision/          # models / pure engine / Shadow·query service
│  ├─ intelligence/      # models / policy·routing·Gateway service
│  │  └─ providers/      # Fake / Gemini SDK / Ollama HTTP adapter
│  ├─ workflow/          # models / agents / policy / graph / runtime
│  ├─ execution/         # models / approval policy / 내부 실행·검증 service
│  └─ ax/                # 기존 안전한 실행 Trace projection/query service
├─ domain/               # Incident·Approval·Job·Config 순수 규칙
├─ application/          # 공유 권한·업무 Command/Query
│  └─ ports/             # repositories.py / identity_provider.py
├─ infrastructure/       # tenant-scoped Repository·Outbox·Job Worker
├─ api/                  # HTTP routes·DTO·인증 dependency
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

Decision=Jev, Intelligence=LLM+향후 LangChain composition, Workflow=LangGraph+최소 Multi-Agent+향후 Loop, Execution=Harness/MCP 책임 영역, AX=Agent Experience입니다. 문서의 9개 개념은 유지합니다. 현재 Execution은 **내부 실행/Verification Command와 승인 재검증**이며 Harness/MCP transport·Connector write·외부 Action reconciliation은 미구현입니다. AX는 **안전한 Trace 조회/투영과 조사 업무 진행·근거 범위**를 제공하며 새 AI Brief·Next Best Action 정책은 추가하지 않았습니다.

## 안전 경계

순수 계약/Decision은 DB·HTTP·Graph·Provider를 import하지 않습니다. Workflow Node는 repository 구현체나 Provider SDK 대신 Port와 Gateway를 사용합니다. Intelligence는 Domain 상태를 변경하지 않고 내부 실행/Verification은 기존 Application/Domain invariant를 통과합니다. LangGraph는 Domain State Machine을 대체하지 않습니다.

Repository Protocol 9개는 `application/ports/repositories.py`로 통합하고 IdentityProvider는 독립 유지합니다. AccessUnitOfWork는 keyword-only이며 transaction/rollback/lock semantics는 동일합니다. IncidentCommands는 명시적 public method와 공통 auth/idempotency/audit helper를 사용합니다. 새 DI framework나 compatibility shim은 없습니다.

Job Worker의 `src.infrastructure.jobs.runtime` 진입점과 Outbox dispatch·claim/lease 책임은 유지합니다. Config version은 Run 시작 때 고정하며 AgentRun/business trace와 LangGraph Checkpoint는 분리합니다. 프론트엔드는 `shared/api.ts`에서 공통 연결·인증·명령 키를 가져오고 기능 API는 화면 옆에서 찾습니다. Review의 Incident DTO decoder 재사용, 서버 permission source of truth, HTTP 실패 시 Mock fallback 금지는 동일합니다.

## 실행·검증

`backend/`는 루트 Python 프로젝트를 editable dependency로 사용하며 실제 구현은 `backend/src/`의 `src` 패키지입니다. 루트와 backend lockfile, 기존 CLI/RAG/Streamlit을 유지합니다. `src.infrastructure.migrations`는 `db/migrations/001`~`018`을 패키지 리소스로 읽으며 이번 리팩토링은 schema/migration/Checkpoint payload를 변경하지 않습니다.

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

production OIDC/SSO·deployment, 전체 retention/migration engine, 고급 Context enrichment·동적 Registry·branch 자동 Loop, Harness/MCP, 외부 Action reconciliation은 후속 범위입니다. 승인된 내부 실행을 실제 외부 변경과 구분하고 Jev Shadow를 자동 AI 실행으로 바꾸지 않습니다. v0.6 MVP Next는 Day 28 최소 Loop/Harness, Day 29 LangChain/MCP/Tool AX, Day 30 AX/AI MVP RC입니다.
