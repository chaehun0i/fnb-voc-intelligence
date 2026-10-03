# Day 16 ServIQ 실행과 CI/CD

## 목적

새 운영 프론트엔드, Incident API, PostgreSQL 저장소, Outbox Worker를 한 환경에서 실행하고 변경 사항을 반복 검증합니다. 기존 Day 12 Docker Compose와 Streamlit 실행 방식은 그대로 유지합니다.

이번 단계의 CI는 코드와 이미지를 검증합니다. 수동 릴리스는 검증한 이미지를 GHCR에 게시하는 과정이며, 운영 서버 배포는 별도 절차로 남겨 둡니다.

Day 17에는 [운영 안전 실행 계약](serviq_access_review.md)의 PostgreSQL 보안 smoke와 실제 HTTP Review 검증을 추가했습니다. Compose는 여전히 개발용 Local Principal을 사용하므로 OIDC나 production-ready 배포로 간주하지 않습니다.

## 구성

Day 18에는 [작업 대기열 운영](serviq_job_queue.md)의 PostgreSQL Queue smoke와 nginx HTTP Job 조회를 추가했습니다. `worker`는 Outbox 전달과 독립 Job 실행을 함께 순회합니다. Redis나 Agent Runtime을 도입한 것은 아닙니다.

### 로컬 실행 구성

Day 19에는 [Dashboard Projection](serviq_dashboard.md)의 실제 PostgreSQL 집계 smoke와 nginx Dashboard 지표 변화 검증을 추가했습니다. 스키마 변경 없이 읽기 전용 Query를 제공하며 CI는 기존 PostgreSQL→security→Queue 이후 Dashboard를 검증합니다.

새 서비스는 `serviq` 프로필에만 포함됩니다. 기존 `db`, `app`, `init-db`, `cli`, `dashboard`의 역할과 데이터 볼륨을 유지합니다. Streamlit의 실행 경로만 이동한 `backend/src/dashboard/app.py`로 맞춥니다.

| 서비스 | 역할 | 접근 방식 |
| --- | --- | --- |
| `db` | 기존 PostgreSQL/pgvector와 ServIQ 테이블 저장 | Docker 내부 네트워크 |
| `serviq-init` | Incident 및 Outbox 스키마의 반복 가능한 초기화 | 작업 완료 후 종료 |
| `api` | `main:app`의 FastAPI 서버 | `127.0.0.1:8000` |
| `frontend` | Vite 빌드 산출물을 제공하는 nginx | `127.0.0.1:8080` |
| `worker` | Outbox 전달과 독립 PostgreSQL Job 실행 | 공개 포트 없음 |

`api`와 `worker`는 DB healthcheck와 `serviq-init`의 정상 완료 이후 시작합니다. `frontend`는 API healthcheck가 통과한 후 시작합니다. Python 서비스는 기존 루트 `Dockerfile`을 사용하고, API는 `/app/backend`에서 `fastapi run`으로 실행합니다. 이미지의 `PYTHONPATH=/app/backend` 설정으로 기존 `/app` 작업 경로의 CLI도 같은 소스와 데이터 기준 경로를 사용합니다. 정적 화면은 `frontend/Dockerfile`의 Node.js 24 빌드와 비특권 nginx 실행 단계로 분리합니다.

로컬 실행 경계는 `backend/`, `db/`, `frontend/`입니다. `backend/`는 FastAPI 실행 진입점, 전용 uv lockfile, `backend/src/` 구현과 `backend/tests/` 테스트를 관리합니다. `db/migrations/001_serviq.sql`은 Incident/Outbox 스키마를 보관하고 Python 패키지 리소스로 읽습니다. 기존 Domain/Application/RAG/ingestion/Streamlit 코드는 백엔드 아래로 이동하며 `src.*` import와 기존 동작을 유지합니다. 자세한 구조는 [실행 디렉터리 문서](serviq_structure.md)에서 확인합니다.

브라우저는 화면과 API를 같은 주소에서 사용합니다. 프론트엔드의 빌드 설정은 `VITE_API_MODE=http`, `VITE_API_BASE_URL=/api/v1`이며 nginx가 `/api/` 요청을 Docker 내부의 `api:8000`으로 전달합니다. Vite의 `VITE_` 값은 빌드 시 정적 파일에 포함되므로 API 주소를 변경하면 프론트엔드 이미지를 다시 빌드해야 합니다. 비밀 값은 `VITE_` 변수에 넣지 않습니다.

### 자동 검증과 수동 릴리스

`.github/workflows/ci.yml`은 PR과 `main` push에서 다음을 검증합니다.

- Python 3.12의 `ruff check .`와 전체 `pytest`
- `backend/uv.lock` 기반 설치, `main:app`과 DB SQL 리소스 import, `fastapi run` 명령
- Fake 생성기를 사용하는 기존 RAG/ingestion/health 회귀 테스트
- Node.js 24에서 `npm ci`, lint, test, 두 번의 build와 빌드 후 lint
- 별도 pgvector PostgreSQL 서비스에서 Incident 저장과 Outbox smoke
- 같은 전용 DB에서 Tenant/RBAC·Approval·불변 Audit·재시작/동시 Idempotency·감사 실패 롤백 smoke
- 기존 Python 이미지와 새 프론트엔드 이미지의 Docker build, API/RAG/ingestion import, `PROJECT_ROOT=/app`, nginx 설정
- 기존 서비스와 `serviq` 프로필의 Compose 설정
- `serviq-ci` 전용 Compose 스택에서 nginx 프록시를 거친 Incident 생성부터 수동 검증·종결까지의 HTTP 흐름, 오류 계약과 Worker의 실제 Outbox 완료 기록
- HTTP Review 원본 조회·승인·같은 키 재전송·다른 내용 충돌
- PostgreSQL Job의 Tenant 격리·동시 claim·lease 복구·재시도/취소·Audit·멱등성·DLQ 검증
- nginx Queue 목록·상세 조회, Outbox dispatch와 Job Worker 완료 및 terminal 상태 보호

RAG smoke는 실제 DB 자료나 외부 LLM을 준비해야 하는 CLI 운영 실행 대신 기존 CLI 및 파이프라인 테스트를 실행합니다. 테스트의 Fake 연결과 생성기를 사용하므로 API Key와 외부 네트워크가 필요하지 않습니다. PostgreSQL smoke는 CI 전용 DB와 테스트용 비밀번호를 사용합니다.

GitHub Action은 공식 저장소에서 존재를 확인한 버전을 사용합니다. `setup-uv`는 `v10.2.0` 릴리스 태그를 사용하며, uv 캐시는 `backend/uv.lock`과 루트·백엔드의 `pyproject.toml` 변경을 기준으로 갱신합니다. Node.js 캐시는 `frontend/package-lock.json`을 기준으로 관리합니다. 기본 권한은 `contents: read`이고 checkout에는 자격 증명을 남기지 않습니다. 일반 CI는 같은 브랜치의 이전 실행을 취소하며, 수동 릴리스는 같은 브랜치에서 실행을 순차 처리합니다.

Compose 통합 검증은 `serviq-ci` 프로젝트를 사용하며 테스트 전용 DB·사용자·비밀번호와 `18000`/`18080` 포트를 지정합니다. `api`, `frontend`, `worker`를 `--wait`로 시작한 뒤 표준 라이브러리 HTTP 스크립트로 실제 nginx 프록시를 확인합니다. 검증 후에는 성공 여부와 관계없이 해당 CI 프로젝트에만 `down --volumes`를 실행합니다. 일반 로컬 실행이나 기존 운영 DB 볼륨을 정리하는 명령으로 사용하지 않습니다.

`.github/workflows/release.yml`은 `main`에서 수동 실행할 때 CI 전체를 다시 통과한 후 두 이미지를 게시합니다.

- `ghcr.io/chaehun0i/fnb-voc-intelligence-python`
- `ghcr.io/chaehun0i/fnb-voc-intelligence-frontend`

각 이미지에는 `sha-<전체 commit SHA>`와 `latest` 태그가 붙습니다. 운영 적용 시에는 변경 가능한 `latest` 대신 확인한 SHA 또는 이미지 digest를 선택합니다. 워크플로의 `GITHUB_TOKEN`은 기본적으로 저장소 읽기 권한만 가지며, 게시 작업에만 `packages: write`를 부여합니다. 별도 PAT를 저장할 필요는 없습니다.

## 실행 및 검증

### ServIQ 실행

먼저 `.env.example`을 `.env`로 복사하고 `POSTGRES_PASSWORD`를 안전한 값으로 변경합니다. `.env`는 커밋하지 않습니다. Compose의 ServIQ DSN은 `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`에서 생성합니다. `SERVIQ_DATABASE_URL` 예시는 Docker 외부에서 Python을 직접 실행할 때 사용하는 주소입니다.

```bash
docker compose --profile serviq config --quiet
docker compose --profile serviq up --build -d api frontend worker
docker compose --profile serviq ps -a
docker compose --profile serviq logs api worker frontend
```

화면은 <http://localhost:8080>, API health는 <http://localhost:8000/api/v1/health>, OpenAPI는 <http://localhost:8000/docs>에서 확인합니다. 화면의 API 연결도 <http://localhost:8080/api/v1/health>로 확인할 수 있습니다. `/healthz`는 nginx의 정적 화면 제공 상태를 확인하는 별도 주소입니다.

`SERVIQ_SEED_DEMO`의 기본값은 `false`입니다. 새 DB의 Incident 목록은 정상적인 빈 목록입니다. 개발용 예시 Incident가 필요할 때만 `.env`의 `SERVIQ_SEED_DEMO=true`를 명시하고 API를 다시 시작합니다. 실제 운영 데이터와 예시 데이터를 혼합하지 않습니다.

```bash
docker compose --profile serviq up -d --force-recreate api
docker compose --profile serviq stop frontend api worker
```

`stop`은 DB 데이터를 제거하지 않습니다. 기존 `postgres_data` 볼륨을 삭제하는 `down -v`는 일반 중지 절차로 사용하지 않습니다. 기존 Streamlit은 이전과 같이 `docker compose up --build -d dashboard`로 실행할 수 있습니다.

### 개발 환경 검증

API는 `backend/`에서 다음 명령으로 실행합니다. `fastapi run`은 기본 포트 `8000`을 사용하고 `0.0.0.0`에 바인딩합니다. 로컬 접근만 허용할 때는 `--host 127.0.0.1`을 추가합니다. 직접 실행할 때는 `SERVIQ_REPOSITORY`와 `SERVIQ_DATABASE_URL`을 해당 셸 환경에 설정하며, PostgreSQL 모드에서는 스키마 초기화를 먼저 실행합니다. 기본 In-Memory 실행은 DB 없이도 가능합니다.

```bash
cd backend
uv run fastapi run
```

화면 개발 서버는 별도 터미널의 `frontend/`에서 실행합니다. 기존 Mock 모드 또는 `.env.local`의 `VITE_API_MODE=http`, `VITE_API_BASE_URL=http://localhost:8000/api/v1` 설정을 사용합니다.

```bash
cd frontend
npm ci
npm run dev
```

저장소 루트에서 Python 검증을 실행합니다.

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest
uv run --extra dev pytest backend/tests/test_rag_cli.py backend/tests/test_rag_pipeline.py backend/tests/test_ingestion_pipeline.py backend/tests/test_health.py
```

프론트엔드는 `frontend/`에서 검증합니다. Windows PowerShell에서는 실행 정책에 영향을 받지 않도록 `npm` 대신 `npm.cmd`를 사용할 수 있습니다.

```bash
npm ci
npm run lint
npm run test
npm run build
npm run build
npm run lint
```

Docker 이미지와 Compose 설정은 저장소 루트에서 확인합니다.

```bash
docker build --tag serviq-python:local .
docker build --file frontend/Dockerfile --tag serviq-frontend:local .
docker compose --profile serviq config --quiet
```

이미지 설정과 데이터 기준 경로는 네트워크·포트·볼륨 연결 없이 확인할 수 있습니다.

```bash
docker run --rm --network none --workdir /app/backend serviq-python:local python -c "from pathlib import Path; from main import app; from src.config.settings import PROJECT_ROOT; assert PROJECT_ROOT == Path('/app'); print(app.title)"
docker run --rm --network none --entrypoint nginx serviq-frontend:local -t
```

별도의 로컬 테스트 Compose 스택이 준비되어 있다면 nginx 프록시를 통한 실제 HTTP 흐름을 다음처럼 검증할 수 있습니다. 스크립트는 기본 서버 주소가 없으며 명시한 로컬 loopback 주소만 허용합니다.

```powershell
$env:SERVIQ_TEST_API_BASE_URL = "http://127.0.0.1:18080/api/v1"
python -m scripts.serviq_http_smoke
```

`scripts/serviq_http_smoke.py`는 정적 화면·nginx health·API health, Incident 생성·조회·분류·조사·증거·원인 분석·조치·사람 승인·수동 실행 기록·검증 PASS·종결, Workspace Permission과 목록 필터를 검증합니다. 없는 Incident의 `NOT_FOUND`, 입력 오류의 `VALIDATION_ERROR`, 선행 조건 위반의 `DOMAIN_RULE_VIOLATION`, 오래된 버전의 `CONFLICT`, 임의 상태 `PATCH`의 거부와 요청 식별자 전달도 확인합니다. 실제 운영 서비스를 실행하거나 외부 시스템을 변경하지 않으며, 검증용 Incident는 테스트 DB에 남습니다. CI에서는 전용 프로젝트의 볼륨 정리로 제거합니다.

이 절차는 CI에서 실행하도록 정의한 검증 범위입니다. 실제 CI 성공 여부는 해당 커밋의 Actions 실행 결과에서 확인하며, 워크플로 작성만으로 성공을 기록하지 않습니다.

HTTP 스크립트의 실행 조건은 네트워크 없는 단위 테스트로도 확인합니다. 허용된 loopback 주소는 파싱만 확인하고, 외부 주소·다른 API 경로·명시적 환경 변수 없는 실행은 실제 요청 전에 거부하는지 검증합니다.

```bash
uv run --extra dev pytest backend/tests/test_serviq_http_smoke.py
```

기존 DB readiness 명령 `python -m src.health`는 실제 연결과 `SELECT 1` 결과를 확인합니다. 연결 주소가 없거나 DB 연결·조회가 실패하면 종료 코드 1, 조회가 정상이라면 0을 반환합니다. URL이나 원본 오류를 출력하지 않습니다. HTTP `/api/v1/health`는 HTTP 프로세스 응답을 확인하는 별도 경계입니다.

PostgreSQL smoke 스크립트는 사용자가 지정한 테스트 전용 DB에서 실행합니다. 운영 DB 주소를 사용하지 않습니다. Bash에서는 다음과 같이 실행합니다.

```bash
SERVIQ_TEST_DATABASE_URL=postgresql://user:password@localhost:5432/serviq_test uv run --extra dev python -m scripts.serviq_postgres_smoke
```

PowerShell에서는 같은 변수를 세션에 설정한 후 실행합니다.

```powershell
$env:SERVIQ_TEST_DATABASE_URL = "postgresql://user:password@localhost:5432/serviq_test"
uv run --extra dev python -m scripts.serviq_postgres_smoke
```

### 수동 릴리스 준비

저장소 관리자가 GitHub의 `Settings → Environments`에서 `release` 환경을 만들고 `Required reviewers`와 `main` 브랜치 제한을 설정합니다. 워크플로에 `environment: release`를 적는 것만으로 승인 규칙이 생성되지는 않습니다. Required reviewers의 사용 가능 여부는 저장소 공개 여부와 GitHub 요금제에 따라 달라집니다. 이 설정과 실제 승인 여부는 [GitHub 환경 보호 문서](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)에서 확인합니다.

PR을 검토하고 `main`에 병합한 다음 `Actions → ServIQ 수동 이미지 릴리스 → Run workflow`에서 `main`을 선택합니다. CI 성공과 환경 승인을 거쳐 GHCR 게시가 완료됩니다. 이 절차는 PR 병합이나 운영 서버 적용을 자동으로 수행하지 않습니다.

## 제한 사항

API 인증과 사용자별 권한 검증은 아직 운영 수준으로 연결되지 않았습니다. 그래서 새 API와 화면 포트는 호스트의 `127.0.0.1`에만 연결하며, 인터넷 공개 배포를 위한 설정으로 사용하지 않습니다. 기존 Streamlit의 포트 설정은 Day 12 구성을 유지합니다.

Incident HTTP 경계 외의 검토·추적·연동·설정 화면은 명시된 미리보기 계약을 사용합니다. Mock 검토나 화면의 설정 변경을 실제 Agent/LLM 실행으로 해석하지 않습니다. Worker와 API의 실제 처리 범위는 [Incident 영속화 문서](serviq_persistence.md)에서 확인합니다.

운영 TLS, 인증, 멀티테넌트 격리, Secret 관리, 자동 서버 배포, 외부 LLM Runtime은 이번 배포 구성에 포함하지 않습니다. GHCR에 이미지를 게시해도 운영 서버가 자동으로 변경되지 않습니다. 로컬 Docker daemon이나 패키지 다운로드가 실패하면 환경 문제와 코드 검증 결과를 구분해서 기록합니다.

## 다음 단계

운영 인증과 접근 제어를 연결하고, PostgreSQL 백업·복원 절차와 이미지 digest 기반 적용·되돌리기를 검증합니다. 이후 실제 Queue/Worker 실행 정책, Jev, 공통 LLM Gateway, LangGraph를 순서대로 연결하며 기존 RAG와 Streamlit 회귀 검증을 유지합니다.
