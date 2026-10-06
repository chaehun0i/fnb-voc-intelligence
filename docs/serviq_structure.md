# ServIQ 프로젝트 구조 — Day 26 정리 기준

## 목적

Day 16에 정한 `backend/`, `db/`, `frontend/` 실행 경계를 유지하고, Day 26 이후 흩어진 작은 패키지를 기능별로 통합했습니다. Agent·LLM·Jev는 각각 `agents/`, `llm/`, `routing/` 한곳에서 찾습니다. Incident 핵심 규칙과 공유 권한·저장소는 기존 경계를 유지합니다. API는 백엔드 디렉터리에서 `uv run fastapi run`, 화면은 프론트엔드 디렉터리에서 `npm run dev`를 사용합니다. 기존 RAG/CLI 기능도 유지합니다.

## 코드를 찾는 기준

```text
backend/src/
├─ agents/          # 실행 계약, History/RCA/CAPA, 승인·검증, Graph/Checkpoint
├─ llm/             # Gateway, 정책, Provider 선택, 서비스·조회·실행 설정
│  └─ providers/    # Fake/Gemini/Ollama SDK adapter만 격리
├─ routing/         # Jev 순수 판단 + Context/Shadow/Query 연결
├─ domain/          # Incident·Approval·Job·Config의 순수 업무 계약·규칙
├─ application/     # 공유 보안·UoW port와 Incident/Approval/Job/Config 서비스
├─ infrastructure/  # 공통 DB와 외부 기술 adapter
│  ├─ repositories/ # tenant-scoped persistence
│  ├─ jobs/         # Outbox 전달, Job claim/lease, runtime 진입점
├─ api/             # HTTP routes/DTO/auth dependency, 업무 판단은 하지 않음
└─ data·rag·ingestion·analysis·dashboard·config/ # 기존 Data Intelligence/설정 기능

frontend/src/
├─ api/             # client.ts의 공통 연결·인증 + 기능별 DTO/HTTP adapter
├─ features/        # 운영 화면 (Incident/Review/Queue/Settings/Trace 등)
├─ components/      # 재사용 UI
├─ contracts/       # 공통 화면 계약
└─ app·lib·test/    # 앱 조립, 표시 도우미, 테스트 fixture
```

같은 기능을 Domain/Application/Infrastructure 세 군데로 나누던 Agent 코드는 `agents`로 모았습니다. `models.py`·`verification_contracts.py`·`verification_rules.py`는 SDK 독립 계약/규칙이고, `*_node.py`는 조사 로직, `*_commands.py`는 권한·UoW를 거치는 업무 명령, `graph.py`·`checkpoint.py`·`processor.py`는 durable 실행입니다. 폴더 통합이 책임 통합은 아닙니다. 순수 계약이 Graph/DB/Provider를 import하지 않는 테스트를 유지합니다.

`routing/models.py`·`rules.py`·`profiles.py`·`engine.py`는 I/O 없는 Jev 판단입니다. 같은 폴더의 `context.py`·`shadow.py`·`queries.py`만 Application 연결을 담당합니다. Provider 선택은 별도 업무 라우팅이 아니라 Gateway 책임이므로 `llm/router.py`에 남깁니다. `llm/runtime.py`는 조립, `service.py`는 인증된 실행, `queries.py`는 운영 조회이며 실제 SDK는 `providers` 밖으로 나오지 않습니다. 별도 `decision/jev`·`runtime/workflows`·계층별 `workflows`/`decisions`/`application/llm` 패키지나 compatibility shim은 남기지 않습니다.

Outbox와 Job Worker는 `infrastructure/jobs`에 모으되 `outbox_worker.py`와 `job_worker.py`의 상태 저장/lease 책임은 합치지 않습니다. Compose와 문서의 실행 경로는 `src.infrastructure.jobs.runtime`입니다. 과거 module path는 프로젝트 내부 계약이므로 import/script를 한 번에 갱신했고 compatibility shim을 새로 만들지 않았습니다.

프론트엔드의 연결 모드·API 주소·인증 헤더·명령 키는 `api/client.ts`에서 가져옵니다. Queue/Settings/Dashboard가 이를 위해 Incident adapter를 import하지 않습니다. Review가 실제 Incident DTO decoder를 재사용하는 의존은 유지합니다. 응답 검증과 feature-specific 오류, 같은 요청 키 재사용, HTTP 실패 시 Mock fallback 금지는 바꾸지 않았습니다.

소스가 포함된 백엔드 하위 폴더는 최초 39개 → 1차 정리 35개 → 기능 중심 정리 31개로 줄었습니다(`backend/src` 자체와 빈 폴더/cache 제외). Agent/Jev/LLM 관련 폴더는 8개 → 4개이며 Agent/Jev는 깊이 3에서 1로 줄었습니다. 기능 진입점을 루트로 올렸으므로 최상위 폴더 수 자체를 감소 목표로 삼지 않습니다. 공통 Incident Domain/Application/Infrastructure/API와 기존 RAG, 기능별 frontend API는 그대로 유지합니다.

## 구성

| 디렉터리 | 담당 내용 | 실행 경계 |
| --- | --- | --- |
| `backend/` | FastAPI `main:app` 진입점, 실행용 `pyproject.toml`과 `uv.lock` | 백엔드 디렉터리의 uv 환경 |
| `backend/src/` | 기존 Python 구현을 모은 `src` 패키지 | 기존 `src.*` import 유지 |
| `backend/tests/` | 전체 Python 회귀·Domain/API·Worker 테스트 | 루트 `pytest` 및 CI에서 수집 |
| `db/` | ServIQ SQL 초기화 자료 | 설치 가능한 Python 패키지 리소스 |
| `frontend/` | React 운영 화면, Vite 개발 서버, npm lockfile | 프론트엔드 npm 환경 |
| `backend/src/api/` | 기존 FastAPI Factory, Routes, DTO, 오류 변환 | `backend/main.py`가 가져오는 API 구현 |
| `backend/src/domain/`, `backend/src/application/` | Incident 상태 규칙과 Query/Command 서비스 | HTTP 및 저장 기술과 분리된 계층 |
| `backend/src/infrastructure/` | Repository, SQL 초기화 로더, Outbox Worker | 공통 Python 패키지 |
| `backend/src/llm/` | Provider 중립 계약·정책·Gateway·실행 조립·사용량 조회 | SDK는 Provider 어댑터에만 격리, Shadow 자동 호출 없음 |
| `backend/src/agents/` | AgentRun·실행 허용·History/RCA/CAPA·승인·검증·Graph 복구 | 기존 Job으로 명시적 실행, Config 고정, 참조만 Checkpoint 저장 |
| `backend/src/routing/` | Jev 판단·정책 snapshot·Shadow·감사 조회 | 순수 판단과 I/O 연결 파일은 import 경계로 분리 |
| `backend/src/data/`, `backend/src/rag/`, `backend/src/ingestion/`, `backend/src/dashboard/` | Day 1~12 Data Intelligence 구현 | 기존 CLI와 Streamlit 실행 유지 |

`backend/`는 저장소 루트 Python 프로젝트를 로컬 editable dependency로 사용합니다. 루트 패키지 설정은 실제 `backend/src/` 코드를 `src` 패키지로 등록하므로 Domain/API 코드를 복사하지 않습니다. `backend/uv.lock`은 백엔드 실행 환경의 재현 가능한 의존성을 기록합니다. 루트의 기존 `src/`, `tests/`를 중복으로 남기지 않습니다.

Incident와 Outbox SQL은 `db/migrations/001_serviq.sql`에 있습니다. `src.infrastructure.migrations`는 `importlib.resources`로 해당 파일을 읽고 한 트랜잭션에서 실행합니다. 그래서 실행 위치가 저장소 루트인지 `backend/`인지와 관계없이 같은 자료를 사용합니다. Docker의 Python 패키지 설치에도 SQL을 포함합니다.

SQL은 기존 Product/Review/pgvector 테이블을 변경하지 않습니다. 새 ServIQ 테이블과 인덱스를 반복 실행 가능하게 생성하고, 재시도 입력은 `attempts >= 0`, `max_attempts > 0` CHECK로 제한합니다. 이전 개발 DB에 테이블이 이미 있어도 이름을 확인한 후 누락된 제약을 추가합니다. 데이터가 제약을 위반한다면 초기화가 실패하므로 해당 자료를 확인한 뒤 다시 실행합니다.

## 실행 및 검증

현재 초기화 로더는 `001`~`018` migration을 번호순으로 읽습니다. 독립 Job 모델은 `backend/src/domain/jobs/`, 서비스는 `backend/src/application/jobs/`, API는 `backend/src/api/routes/jobs.py`, Worker는 `backend/src/infrastructure/jobs/`에 있습니다. 화면 경계는 `frontend/src/api/jobs/`이며 자세한 책임 분리는 [Day 18 문서](serviq_job_queue.md)를 참고하세요.

AgentRun/Step, History 출처 연결과 외부 호출 claim은 `011`~`013`의 additive schema입니다. 공식 LangGraph Checkpoint 테이블은 운영 실행 원본과 분리합니다. 화면 경계는 `frontend/src/api/agentRuns/`이며 [Day 23 문서](serviq_langgraph_history.md)에 실행 허용·검색 출처·중단 복구·한계와 검증을 기록합니다.

로컬 PostgreSQL은 기본 프로젝트 이름이 `serviq`인 Compose의 `db`로 통일합니다. `127.0.0.1:${POSTGRES_PORT:-5432}`를 사용하므로 루트/Backend의 로컬 DSN은 동일 DB·계정을 가리키도록 설정합니다. 컨테이너 내부는 계속 `db:5432`를 사용합니다. 과거 검증 DB는 운영 `fnb_voc`와 분리한 이력이며, 스냅샷을 운영 테이블에 덮어쓰지 않습니다. 이관 시 백업·테이블별 행 수 대조 후 별도 컨테이너를 정리하고 기존 볼륨은 복구용으로 보존합니다.

설정 계약·상한은 `backend/src/domain/config/`, 조회·변경·복원은 `backend/src/application/config/`, HTTP는 `backend/src/api/routes/settings.py`에 있습니다. `007_control_plane.sql`의 불변 버전과 `008_config_outbox.sql`의 독립 설정 이벤트를 기존 UoW로 함께 저장합니다. 화면 경계는 `frontend/src/api/settings/`이며 [Day 20 문서](serviq_control_plane.md)에 책임·실행·제한 사항을 기록합니다.

### 백엔드 실행

Day 19의 집계 경계는 `application/dashboard`, `infrastructure/dashboard_projection.py`, `api/routes/dashboard.py`와 `frontend/src/api/dashboard`입니다. 원본 Incident/Approval/Job을 복제하지 않으며 상세 책임과 KPI 규칙은 [Dashboard Projection 문서](serviq_dashboard.md)를 참고하세요.

저장소 루트에서 `backend/`로 이동한 후 다음 명령을 그대로 실행합니다.

```bash
cd backend
uv run fastapi run
```

API는 기본 포트 `8000`에서 실행합니다. <http://localhost:8000/api/v1/health>와 <http://localhost:8000/docs>로 확인할 수 있습니다. `uv run`이 실행 환경을 준비하며 이후에는 `backend/uv.lock`을 사용합니다. 변경된 의존성이 없는지 확인할 때는 `uv sync --locked`를 실행합니다.

`fastapi run`의 기본 바인딩은 `0.0.0.0`입니다. 직접 실행할 때 같은 네트워크에서 접근할 수 있다는 점을 고려합니다. 로컬 호스트에만 제한하려면 `uv run fastapi run --host 127.0.0.1`을 사용합니다. Docker Compose의 새 서비스는 호스트 포트를 `127.0.0.1`로 제한합니다. 이 차이는 [FastAPI CLI 문서](https://fastapi.tiangolo.com/fastapi-cli/)에서 확인할 수 있습니다.

PostgreSQL을 사용하는 경우 같은 셸에서 `SERVIQ_REPOSITORY=postgres`와 `SERVIQ_DATABASE_URL`을 설정합니다. `SERVIQ_SEED_DEMO=true`는 개발용 예시 Incident가 필요한 때에만 명시합니다. 기본 실행의 In-Memory 자료는 서버 재시작 시 유지되지 않습니다.

### 데이터베이스 초기화

API에서 사용할 DB 주소를 셸 환경에 설정하고 `backend/`에서 실행합니다.

```bash
uv run python -m src.infrastructure.migrations
```

`db/`에서 자료를 확인하며 실행하려면 백엔드 환경을 지정합니다.

```bash
cd db
uv run --project ../backend python -m src.infrastructure.migrations
```

Docker에서는 환경 파일의 PostgreSQL 설정을 공유하는 `serviq-init`이 API와 Worker보다 먼저 같은 SQL을 실행합니다. 전체 실행 절차는 [ServIQ 실행과 CI/CD](serviq_delivery.md)를 참고합니다.

### 프론트엔드 실행

별도 터미널에서 `frontend/`로 이동합니다.

```bash
cd frontend
npm ci
npm run dev
```

프론트엔드의 기본 개발 모드는 Mock입니다. 실제 로컬 Incident API를 사용하려면 `frontend/.env.local`에 다음 값을 넣고 Vite를 다시 실행합니다.

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

이 설정은 Incident HTTP Adapter에 적용됩니다. 검토·추적·연동·운영 설정의 미리보기 계약은 각 화면의 안내에 따라 동작합니다.

### 검증

기존 전체 검증은 저장소 루트에서 유지합니다.

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest
```

백엔드 디렉터리에서 lockfile과 실행 진입점을 확인합니다.

```bash
uv sync --locked
uv run --locked python -c "from main import app; from src.infrastructure.migrations import migration_sql; assert 'serviq_incidents' in migration_sql(); print(app.title)"
uv run --locked fastapi run --help
```

프론트엔드 검증은 프론트엔드 디렉터리에서 실행합니다.

```bash
npm run lint
npm run test
npm run build
```

## 제한 사항

Day 16 최초 이동은 Python 200개, Day 26의 1차 정리는 Python 650개와 frontend 28 files / 173개를 통과했습니다. 이번 기능 중심 통합은 LLM 계약 경계 테스트를 하나 더 추가해 구조 테스트 6개를 포함합니다. 검증 명령과 최신 결과는 [Day 26 검증 기록](serviq_verification.md) 및 PR #51의 최신 check를 따릅니다. DB/Checkpoint payload나 API 응답 계약은 바꾸지 않습니다.

1차 정리 6개 커밋에 이어 Agent 통합, Routing 통합, LLM 통합, 구조 문서·최종 회귀의 4개 독립 커밋으로 마감합니다. 각 커밋 전에 관련 lint/test를 실행합니다. 기존 CI/테스트를 삭제·약화하거나 새 라이브러리를 추가하지 않습니다. 운영 DB/볼륨은 보존하고 검증 DB만 격리합니다.

Python 코드를 `backend/src/`로 옮기며 실행 위치를 정리하지만 Domain/Application/API의 책임이나 기존 Data Intelligence 동작은 변경하지 않습니다. 루트 Python 패키지는 기존 기능과 새 백엔드가 공유하며, `backend/`의 로컬 경로 의존성은 저장소 전체가 함께 있어야 합니다.

SQL 리소스는 현재 ServIQ 초기 스키마와 입력 제약을 관리합니다. 여러 운영 버전에 걸친 온라인 스키마 업그레이드, 데이터 변환 이력, 다운그레이드를 자동화하는 Migration Engine은 별도 항목입니다.

Tenant/Principal/RBAC 및 개발용 인증은 Day 17 이후 실제 구현되어 있습니다. production OIDC/SSO는 미구현입니다. Docker의 API·프론트엔드 포트는 localhost로 제한하며, Jev Shadow 전체가 자동으로 외부 LLM이나 Workflow를 실행하지 않습니다.

## 다음 단계

운영 인증, DB Migration 버전 이력, 백업·복원과 이미지 기반 배포를 연결합니다. 공유 Python 계층의 경계를 유지하며 실제 실행 기능을 하나씩 추가하고, 각 단계에서 기존 Python/RAG/Streamlit 회귀 검증을 계속 실행합니다.
