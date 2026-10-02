# Day 12: Docker Compose

## 목적

기존 PostgreSQL/pgvector, Python CLI, Streamlit Dashboard를 같은 환경에서 실행합니다.
Day 12 구성은 유지하며, 이후 추가한 ServIQ API와 프론트엔드는 별도의 `serviq` 프로필로
실행합니다. 두 화면의 역할과 데이터 저장 경계를 섞지 않습니다.

## 구성

| 서비스 | 역할 | 실행 범위 |
| --- | --- | --- |
| `db` | PostgreSQL/pgvector와 데이터 볼륨 | 기본 서비스 |
| `app` | 기존 Python 이미지와 DB 연결 확인 | 기본 서비스 |
| `init-db` | pgvector 확장 및 기존 Product/Review 스키마 초기화 | 기본 서비스 |
| `dashboard` | 기존 Streamlit Dashboard | 기본 서비스 |
| `cli` | ingestion, 인덱싱, 검색, RAG, 평가 명령 | `cli` 프로필 |
| `serviq-init`, `api`, `frontend`, `worker` | ServIQ 스키마, API, 운영 화면, Outbox 처리 | `serviq` 프로필 |

PostgreSQL은 Docker 내부의 `db:5432`로 접근합니다. 현재 Compose는 DB 포트를 호스트에
공개하지 않습니다. Streamlit은 `${DASHBOARD_PORT:-8501}`을 사용하며, ServIQ API와 화면은
기본적으로 호스트의 `127.0.0.1:8000`, `127.0.0.1:8080`에서 접근합니다.

`postgres_data` 볼륨은 `stop` 후에도 유지됩니다. `init-db` 서비스는 기존 pgvector 확장과
스키마를 반복 실행해도 유지되도록 생성합니다. ServIQ 스키마는 별도 `serviq-init`에서
준비하며 기존 Product/Review 테이블을 대체하지 않습니다.

### 연결 확인과 준비 상태의 범위

`db`의 `pg_isready`는 PostgreSQL 서버가 연결을 받을 수 있는지 확인합니다. 기존 `app`의
`python -m src.health`는 `POSTGRESQL_URL`로 실제 연결 후 `SELECT 1` 결과를 확인합니다.
설정 누락·잘못된 URL·연결·조회·연결 종료 실패는 종료 코드 `1`, 정상 조회는 `0`입니다.
연결 URL, 비밀번호, 원본 DB 예외나 traceback은 출력하지 않습니다.

ServIQ의 저장 방식과 health 명령은 다음처럼 구분합니다.

| 실행 방식 | 필요한 설정 | 확인 범위 |
| --- | --- | --- |
| 기존 CLI와 Streamlit | `POSTGRESQL_URL` | `src.health`의 실제 PostgreSQL 연결 및 최소 조회 |
| 직접 실행한 ServIQ In-Memory API | `SERVIQ_REPOSITORY=memory` 또는 기본값 | DB 없이 실행 가능, API 프로세스 응답 확인 |
| 직접 실행한 ServIQ PostgreSQL API | `SERVIQ_REPOSITORY=postgres`, `SERVIQ_DATABASE_URL` | 별도 스키마 초기화 및 Incident 조회로 저장소 동작 확인 |
| Compose `serviq` 프로필 | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL 모드와 초기화 완료를 서비스 의존성으로 지정 |

`/api/v1/health`는 현재 HTTP 프로세스가 응답하는지만 확인합니다. DB 조회나 Incident/Outbox
스키마 검증을 하지 않으므로, HTTP `200`만으로 PostgreSQL 저장소의 준비 완료를 판단하지
않습니다. `SERVIQ_REPOSITORY=memory`로 API를 실행해도 기존 `src.health`는 DB 연결을
검사합니다. 이 명령을 In-Memory API의 readiness로 사용하지 않습니다.

## 실행 및 검증

`.env.example`을 `.env`로 복사하고 강한 `POSTGRES_PASSWORD`를 설정합니다. `.env`와 실제
연결 주소는 커밋하지 않습니다. Compose의 DB 연결 주소는 위 PostgreSQL 설정으로 생성되며,
직접 실행하는 Python 서비스의 환경변수와 구분합니다.

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps -a
docker compose logs -f app dashboard
docker compose stop
```

설정 구문 확인에는 `config --quiet`를 사용합니다. 환경변수가 치환된 전체 설정을 화면이나
공유 로그에 출력하면 연결 주소의 비밀번호가 노출될 수 있습니다.

기존 Python 이미지의 DB 연결을 별도 일회성 명령으로 확인합니다. 기본 이미지의 CLI 도움말
명령은 종료될 수 있으므로, 종료된 `app`에 `exec`하지 않고 다음 명령을 사용합니다.

```bash
docker compose run --rm app python -m src.health
docker compose ps app db
```

CLI는 다음과 같이 실행합니다. 인덱싱, 검색, RAG, 평가, scale 명령도 같은 이미지의 Python
모듈 또는 등록 CLI를 사용합니다.

```bash
docker compose run --rm cli python -m src.ingestion.cli --help
docker compose up --build -d dashboard
```

ServIQ 실행과 PostgreSQL 저장소의 별도 검증 방법은
[Day 16 실행과 CI/CD](serviq_delivery.md), [Incident 영속화](serviq_persistence.md)를 참고합니다.

```bash
docker compose --profile serviq config --quiet
docker compose --profile serviq up --build -d api frontend worker
```

DB readiness 코드와 기존 Compose 회귀 테스트는 저장소 루트에서 실행합니다. 이 단위 테스트는
실제 DB나 비밀번호 없이 정상·실패·연결 정리·오류 미노출을 결정적으로 검증합니다.

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest backend/tests/test_health.py backend/tests/test_compose.py backend/tests/test_dockerfile.py
uv run --extra dev pytest
```

스택 smoke는 PowerShell에서 `./scripts/compose_smoke.ps1`로 실행합니다. 이 스크립트는
볼륨을 삭제하지 않습니다. Docker daemon 연결 오류가 나면 Docker Desktop을 시작하고 다시
실행합니다. 환경 준비 실패와 코드 테스트 실패는 구분해서 기록합니다.

## 제한 사항

`SELECT 1` 성공은 테이블·pgvector 인덱스·데이터 적재 완료를 보장하지 않습니다. 해당 기능의
초기화와 조회를 별도로 확인합니다. API health 역시 인증, 스키마 준비, Worker 처리 완료를
보장하지 않습니다.

일반 중지에는 `stop`을 사용합니다. `down -v`는 DB 볼륨을 삭제하므로 일반 실행 절차로
사용하지 않습니다. 로그를 공유할 때도 실제 연결 주소나 비밀 정보를 제거합니다.
현재 구성은 로컬 개발용이며 인증·TLS·운영 비밀 관리·백업 자동화를 대신하지 않습니다.

## 다음 단계

HTTP 프로세스 확인과 저장소 readiness를 분리한 운영 점검을 도입하고, PostgreSQL
백업·복원과 스키마 준비 실패 대응을 검증합니다. 기존 Streamlit과 Data Intelligence의
회귀 테스트를 유지하면서 ServIQ의 실행 및 배포 검증을 보강합니다.
