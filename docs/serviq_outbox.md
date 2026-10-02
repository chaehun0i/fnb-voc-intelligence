# Day 16 ServIQ PostgreSQL Outbox Worker

## 목적

인시던트 저장과 이벤트 기록을 같은 PostgreSQL 트랜잭션으로 처리하고, 기록된 이벤트를 별도 Worker에서 인수·검증·완료 처리합니다. 이벤트 누락을 줄이고 재시도와 실패 보관의 경계를 먼저 마련합니다.

현재 기본 처리기는 `incident.created`와 `incident.state_changed`의 계약을 확인하고 식별자와 처리 상태를 구조화 로그로 남깁니다. 처리 완료는 이벤트 검증을 마쳤다는 뜻이며, 실제 조사나 매장 조치를 실행했다는 뜻은 아닙니다.

## 구성

- `backend/src/infrastructure/migrations.py`: `serviq_incidents`와 `serviq_outbox`를 초기화합니다. 기존 Product/Review 테이블과 별도로 관리합니다.
- `PostgresIncidentRepository`: 인시던트 생성 또는 상태 변경과 Outbox 기록을 함께 커밋합니다.
- `backend/src/infrastructure/outbox/worker.py`: 이벤트 인수, 잠금 만료 복구, 재시도, 실패 보관과 종료 신호를 처리합니다.
- `backend/tests/test_outbox_worker.py`: 외부 서비스 없이 계약 검증과 처리 흐름을 검증합니다.

작업 상태는 `PENDING → RUNNING → COMPLETED`입니다. 일시적 오류는 `PENDING`으로 돌아가고, 계약 오류·예상하지 못한 오류·최대 시도 횟수 도달은 `DLQ`로 이동합니다.

### 트랜잭션과 실행 잠금

Worker는 `SELECT ... FOR UPDATE SKIP LOCKED`로 한 건을 인수합니다. 인수 트랜잭션에서는 `attempts`를 증가시키고 `lease_until`을 기록합니다. 실제 처리기는 이 짧은 트랜잭션을 끝낸 뒤 실행하며, 완료 또는 실패 결과는 별도 트랜잭션으로 기록합니다.

잠금이 만료된 `RUNNING` 작업은 남은 시도 횟수가 있을 때 다시 인수합니다. 최대 횟수를 이미 사용했다면 `DLQ`로 보냅니다. 결과 갱신은 인수 당시의 `attempts`와 아직 유효한 잠금을 확인하므로 이전 Worker가 새 시도의 결과를 덮어쓸 수 없습니다.

일시적 실패에는 `RetryableProcessingError`를 사용합니다. 재시도 간격은 기본 5초에서 시작해 두 배씩 증가하며 최대 300초로 제한합니다. 일반 예외와 계약 오류에는 재시도를 적용하지 않습니다.

## 실행 및 검증

먼저 ServIQ 전용 연결 주소를 설정하고 저장소를 초기화합니다. 연결 정보는 환경 변수 또는 로컬 `.env`로 관리하고 저장소에 커밋하지 않습니다. Worker CLI는 `SERVIQ_DATABASE_URL` 환경 변수를 읽습니다.

```powershell
$env:SERVIQ_DATABASE_URL = "postgresql://사용자:비밀번호@localhost:5432/데이터베이스"
uv run python -m src.infrastructure.migrations
```

최대 한 건을 처리하는 실행 방법입니다. 처리할 이벤트가 없으면 즉시 종료합니다.

```powershell
uv run python -m src.infrastructure.outbox.worker --once
```

지속 실행에서는 빈 대기열을 1초 간격으로 확인합니다. 기본 실행 잠금은 60초이며 인수 후 처리기가 이 시간 안에 완료해야 합니다.

```powershell
uv run python -m src.infrastructure.outbox.worker --poll-seconds 1 --lease-seconds 60
```

`Ctrl+C` 또는 `SIGTERM`을 받으면 새 작업 인수를 중단합니다. 현재 처리 중인 작업의 결과를 기록한 뒤 연결을 닫습니다. 프로세스가 강제로 종료되면 잠금 만료 이후 다른 실행에서 다시 인수할 수 있습니다.

```powershell
uv run --extra dev ruff check backend/src/infrastructure/outbox backend/tests/test_outbox_worker.py
uv run --extra dev pytest backend/tests/test_outbox_worker.py
```

실제 DB 통합 검증에서는 다음 명령을 사용합니다. 전용 DB의 다른 대기 작업이 없는 상태에서 실행하며 UUID 검증 데이터와 임시 제약은 종료 시 정리합니다. 자세한 범위와 정리 방식은 [Incident 영속화 문서](serviq_persistence.md)를 확인하세요.

```powershell
$env:SERVIQ_TEST_DATABASE_URL = "postgresql://사용자:비밀번호@localhost:5432/serviq_test"
uv run python -m scripts.serviq_postgres_smoke
```

실제 PostgreSQL 트랜잭션으로 Outbox 기록의 원자성, `SKIP LOCKED`, 만료 잠금 복구, 이전 시도의 완료 기록 차단, 지수 재시도와 `DLQ` 처리를 확인합니다. 시간 경과는 테스트 시계로 조정하며 임의의 기존 작업을 인수하지 않도록 실행 전 대기열을 확인합니다. 2026년 10월 2일 테스트 전용 새 DB에서 이 검증을 실제로 통과했고, 생성한 UUID 데이터와 임시 제약의 정리까지 확인했습니다.

## 제한 사항

- PostgreSQL Outbox를 사용하는 최소 Worker이며 Redis/Kafka, 외부 Queue, 외부 조치 실행기는 연결하지 않습니다.
- Jev, Gemini/Ollama Runtime, LangGraph, Multi-Agent와 MCP를 호출하지 않습니다.
- 잠금 만료·처리 후 결과 기록 실패에는 같은 이벤트가 다시 실행될 수 있습니다. 정확히 한 번 실행을 보장하지 않습니다. 이후 외부 효과가 있는 처리기는 `event_id` 기반 멱등성 기록이 필요합니다.
- 현재 처리기는 검증과 로그만 수행합니다. 장시간 실행을 위한 잠금 갱신, 분산 조정, Worker별 동시성 정책은 아직 제공하지 않습니다.
- 실패 원본 예외를 DB나 로그에 그대로 남기지 않습니다. 운영자가 볼 오류 요약은 안전한 고정 문구이며 이벤트 계약과 식별자로 원인을 추적합니다.
- 프론트의 작업 대기열 화면은 Mock Contract를 사용합니다. 이 Worker의 실시간 상태와 연결되어 있지 않습니다.

## 다음 단계

실제 PostgreSQL 통합 검증과 Worker 운영 관측을 보강한 뒤, 이벤트 소비자의 멱등성·테넌트 동시성·작업 조회 계약을 확정합니다. 그다음 Jev와 공통 LLM Gateway를 연결하며 Gemini/Ollama 호출은 Gateway 뒤에서 수행합니다.
