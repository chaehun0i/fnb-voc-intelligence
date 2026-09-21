# Day 12: Docker Compose

`.env.example`을 `.env`로 복사하고 강한 `POSTGRES_PASSWORD`를 설정합니다. 비밀 파일은
커밋하지 않습니다.

```bash
docker compose up --build -d
docker compose logs -f
docker compose stop
```

PostgreSQL은 `${POSTGRES_PORT:-5432}`, Dashboard는 `${DASHBOARD_PORT:-8501}`을 사용합니다.
`postgres_data` 볼륨은 `stop` 후에도 유지됩니다. `init-db` 서비스는 pgvector 확장과 기존
스키마를 멱등적으로 생성합니다.

CLI는 `docker compose run --rm cli python -m src.ingestion.cli --help`처럼 실행합니다.
인덱싱, 검색, RAG, 평가, scale 명령도 동일 이미지에서 Python 모듈 또는 등록 CLI로 실행할 수
있습니다. 대시보드는 `dashboard` 서비스로 기동합니다.

스택 smoke는 PowerShell에서 `./scripts/compose_smoke.ps1`로 실행합니다. 이 스크립트는
볼륨을 삭제하지 않습니다. Docker daemon 연결 오류가 나면 Docker Desktop을 시작하고 다시
실행하세요.
