$ErrorActionPreference = 'Stop'
docker compose up --build -d db app
docker compose exec -T db psql -U $env:POSTGRES_USER -d $env:POSTGRES_DB -c 'SELECT extname FROM pg_extension WHERE extname = ''vector'';'
docker compose ps --status running
docker compose stop
