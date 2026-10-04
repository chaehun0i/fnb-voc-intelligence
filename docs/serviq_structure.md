# Day 16 ServIQ 실행 디렉터리

## 목적

API, 데이터베이스, 화면의 실행 위치를 `backend/`, `db/`, `frontend/`로 구분합니다. API는 백엔드 디렉터리에서 `uv run fastapi run`, 화면은 프론트엔드 디렉터리에서 `npm run dev`를 사용합니다. Python 구현과 테스트는 `backend/src/`, `backend/tests/`에 모으고 Day 1~14 기능과 `src.*` import를 유지합니다.

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
| `backend/src/data/`, `backend/src/rag/`, `backend/src/ingestion/`, `backend/src/dashboard/` | Day 1~12 Data Intelligence 구현 | 기존 CLI와 Streamlit 실행 유지 |

`backend/`는 저장소 루트 Python 프로젝트를 로컬 editable dependency로 사용합니다. 루트 패키지 설정은 실제 `backend/src/` 코드를 `src` 패키지로 등록하므로 Domain/API 코드를 복사하지 않습니다. `backend/uv.lock`은 백엔드 실행 환경의 재현 가능한 의존성을 기록합니다. 루트의 기존 `src/`, `tests/`를 중복으로 남기지 않습니다.

Incident와 Outbox SQL은 `db/migrations/001_serviq.sql`에 있습니다. `src.infrastructure.migrations`는 `importlib.resources`로 해당 파일을 읽고 한 트랜잭션에서 실행합니다. 그래서 실행 위치가 저장소 루트인지 `backend/`인지와 관계없이 같은 자료를 사용합니다. Docker의 Python 패키지 설치에도 SQL을 포함합니다.

SQL은 기존 Product/Review/pgvector 테이블을 변경하지 않습니다. 새 ServIQ 테이블과 인덱스를 반복 실행 가능하게 생성하고, 재시도 입력은 `attempts >= 0`, `max_attempts > 0` CHECK로 제한합니다. 이전 개발 DB에 테이블이 이미 있어도 이름을 확인한 후 누락된 제약을 추가합니다. 데이터가 제약을 위반한다면 초기화가 실패하므로 해당 자료를 확인한 뒤 다시 실행합니다.

## 실행 및 검증

Day 20 이후 초기화 로더는 `001`~`008` migration을 번호순으로 읽습니다. 독립 Job 모델은 `backend/src/domain/jobs/`, 서비스는 `backend/src/application/jobs/`, API는 `backend/src/api/routes/jobs.py`, Worker는 `backend/src/infrastructure/queue/`에 있습니다. 화면 경계는 `frontend/src/api/jobs/`이며 자세한 책임 분리는 [Day 18 문서](serviq_job_queue.md)를 참고하세요.

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

폴더 이동만 분리한 Git 스냅샷에서 기존 Python 테스트 200개가 통과했습니다. 이후 기능 테스트를 더하더라도 기존 import와 fixture·CLI 경로 회귀는 유지합니다.

Python 코드를 `backend/src/`로 옮기며 실행 위치를 정리하지만 Domain/Application/API의 책임이나 기존 Data Intelligence 동작은 변경하지 않습니다. 루트 Python 패키지는 기존 기능과 새 백엔드가 공유하며, `backend/`의 로컬 경로 의존성은 저장소 전체가 함께 있어야 합니다.

SQL 리소스는 현재 ServIQ 초기 스키마와 입력 제약을 관리합니다. 여러 운영 버전에 걸친 온라인 스키마 업그레이드, 데이터 변환 이력, 다운그레이드를 자동화하는 Migration Engine은 별도 항목입니다.

API 인증과 운영 접근 제어는 아직 완료되지 않았습니다. 직접 실행은 위 바인딩 특성을 확인하고 로컬 개발 범위로 사용합니다. Docker의 새 API·프론트엔드 포트는 localhost로 제한합니다. 외부 LLM, Jev, LangGraph를 이 실행 구조만으로 호출하지 않습니다.

## 다음 단계

운영 인증, DB Migration 버전 이력, 백업·복원과 이미지 기반 배포를 연결합니다. 공유 Python 계층의 경계를 유지하며 실제 실행 기능을 하나씩 추가하고, 각 단계에서 기존 Python/RAG/Streamlit 회귀 검증을 계속 실행합니다.
