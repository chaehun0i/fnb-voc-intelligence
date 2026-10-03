$ErrorActionPreference = 'Stop'
docker compose up --build -d db app
if ($LASTEXITCODE -ne 0) { throw '기존 DB/app 이미지를 시작하지 못했습니다.' }
# 기본 app은 CLI 진입점이므로 일회 실행으로 스키마와 연결을 검증합니다.
docker compose run --rm --no-deps app python -c 'from src.init_db import main; raise SystemExit(main())'
if ($LASTEXITCODE -ne 0) { throw '기존 PostgreSQL 스키마 초기화가 실패했습니다.' }
docker compose exec -T db psql -U $env:POSTGRES_USER -d $env:POSTGRES_DB -c 'SELECT extname FROM pg_extension WHERE extname = ''vector'';'
if ($LASTEXITCODE -ne 0) { throw 'pgvector 확장 조회가 실패했습니다.' }
$extension = docker compose exec -T db psql -U $env:POSTGRES_USER -d $env:POSTGRES_DB -Atc 'SELECT count(*) FROM pg_extension WHERE extname = ''vector'';'
if ($LASTEXITCODE -ne 0 -or $extension.Trim() -ne '1') { throw 'pgvector 확장이 준비되지 않았습니다.' }
docker compose run --rm --no-deps app python -m src.health
if ($LASTEXITCODE -ne 0) { throw '기존 Python DB 연결 검증이 실패했습니다.' }
docker compose ps --status running
if ($LASTEXITCODE -ne 0) { throw 'Compose 상태 조회가 실패했습니다.' }
docker compose stop
if ($LASTEXITCODE -ne 0) { throw '검증 프로젝트 중지가 실패했습니다.' }
