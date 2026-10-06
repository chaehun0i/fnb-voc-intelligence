# Day 18 Persistent Job과 Queue 운영 Console

## 목적

Day 17의 Principal·Tenant/RBAC·감사·영속 멱등성을 재사용해 독립 Job 생명주기와 실제 작업 대기열을 연결합니다.
Frontend-first → Contract-first → Vertical Slice 순서를 유지하며 Incident·Review·RAG·ingestion·Streamlit은 보존합니다.

기준은 main@f90119580df28c662377f74232356ff9faf7f1b8와 병합된 PR #33입니다.
직접 확인한 최신 정본은 Drive의 ServIQ_v0.5_운영안전_실행계약_통합설계입니다.
00·25·28 등의 Day 16 c6060ae 스냅샷을 현재 구현으로 오인하지 않았습니다. 이 저장소에 Day 18의 실제 결과를 기록하며 Drive 원문은 수정하지 않았습니다.

## 구성

### 책임과 실제 구현 범위

| 경계 | 책임 |
| --- | --- |
| `domain/jobs` | 상태·우선순위·시도 횟수·lease·시간대·재시도 원본과 결정적 전이 |
| `application/ports/job_repository.py` | 조직별 조회와 버전 보호 저장 계약 |
| `application/jobs` | 조회 투영·서버 permission·권한 검사·Retry/Cancel 트랜잭션 |
| `infrastructure/repositories/job_repository.py` | PostgreSQL 원본 및 테스트용 메모리 구현 |
| `infrastructure/jobs/job_dispatch.py` | 대표 이벤트를 중복 없이 독립 Job으로 전달 |
| `infrastructure/jobs` | claim·lease·fencing·bounded retry·DLQ·실행 진입점 |
| `api/routes/jobs.py`, `api/schemas/jobs.py` | HTTP DTO와 오류 변환; 업무 규칙은 Application/Domain에 위임 |
| `frontend/src/api/jobs`, `features/operations/Queue.tsx` | Mock/HTTP 교체·상세 팝업·서버 권한 표시 |

IMPLEMENTED는 위 코드와 실제 테스트로 확인한 범위입니다. 실제 OIDC와 Agent Runtime은 완료 항목이 아닙니다.

### Outbox와 Job

Outbox는 발생한 업무 이벤트의 내구성, PostgreSQL `serviq_jobs`는 독립 작업의 실행 생명주기를 담당합니다.
Incident 업무 저장과 Outbox insert의 기존 원자성을 유지하며 Outbox 행을 Job 테이블 대신 사용하지 않습니다.

```text
Incident transaction → Outbox → dispatch → PostgreSQL Job
                                          ↓
                              Queue API / 운영 Console
                                          ↓
                                독립 Worker claim / ACK
```

대표 `incident.created`만 `incident.snapshot`으로 연결했습니다.
처리기는 해당 Tenant의 Incident 원본과 매장 계약을 확인하는 읽기 전용 작업입니다. 조사 Agent·외부 조치·별도 snapshot artifact 저장을 구현한 것은 아닙니다.
기존 상태 변경 이벤트는 계약 검증 경로를 유지합니다.
이벤트 ID 기반 작업 ID·dispatch 유일 제약·트랜잭션 잠금으로 중복 전달을 흡수하며 correlation_id와 Incident 우선순위를 보존합니다.
Job 생성 후 Outbox ACK 전에 장애가 나도 재전달은 기존 Job을 반환합니다.

### 생명주기와 Worker

정상 경로는 `PENDING → RUNNING → COMPLETED`입니다.
자동 재시도 가능한 실패는 남은 횟수 안에서 지연된 PENDING으로 돌아갑니다. 영구 실패는 FAILED, 횟수 소진은 DLQ로 보존합니다.
운영 Retry는 원본 FAILED/DLQ를 덮어쓰지 않고 `parent_job_id`를 가진 새 실행을 만듭니다.
COMPLETED·CANCELLED를 임의로 실행 상태로 되돌리지 않습니다.

Worker는 실행 가능 시각·우선순위 순서로 `FOR UPDATE SKIP LOCKED`를 사용합니다.
짧은 claim 트랜잭션에서 시도 횟수·Worker·lease를 기록하고 처리기는 트랜잭션 밖에서 실행합니다.
만료된 RUNNING은 남은 횟수 안에서 재인수하며 횟수 소진 시 DLQ로 보존합니다.
ACK는 조직·버전·시도 횟수·유효 lease·소유자가 일치할 때만 허용합니다. 늦은 완료 기록은 무시합니다.
자동 backoff는 최대 300초로 제한하며 원본 예외 문자열은 저장하지 않습니다.

취소는 PENDING에만 허용합니다. 실행 중 취소는 `CANCEL_NOT_SUPPORTED_WHILE_RUNNING`으로 거부해 실제 중단처럼 표시하지 않습니다.
Compose worker는 `src.infrastructure.jobs.runtime`으로 전달과 실행을 번갈아 수행합니다. 기존 Outbox 단독 Worker도 보존합니다.
종료 신호는 현재 처리를 마친 뒤 다음 인수를 중단합니다.

### PostgreSQL 원본

`db/migrations/006_serviq_jobs.sql`을 additive하게 추가했습니다. 기존 001~005는 수정하지 않았습니다.
Job ID·Tenant·종류·Incident·매장·correlation·dispatch·부모 작업, 상태·우선순위·시도/최대 횟수, 실행 가능·lease·생성 시각, 버전과 JSONB 문서를 저장합니다.
JSONB에는 시작/완료 시각·Worker·안전한 오류 코드/요약·고정 config_version도 보존합니다.
Tenant와 Incident/부모 Job은 복합 외래 키로 연결하며 dispatch ID는 유일합니다.
Tenant/상태·claim 순서·lease·correlation·Incident 조회 index와 낙관적 버전 검사를 제공합니다.
메모리 저장소는 테스트용이며 재시작 후 영속성은 PostgreSQL 모드에서 보장합니다.

### Query와 운영 Command

| Endpoint | 용도 |
| --- | --- |
| `GET /api/v1/jobs` | 조직별 목록; status·priority·job_type·incident_id·correlation_id, limit 1~100·offset |
| `GET /api/v1/jobs/{job_id}` | 작업 상세와 서버 계산 permission |
| `POST /api/v1/jobs/{job_id}/retry` | 실패 원본을 보존한 새 실행 |
| `POST /api/v1/jobs/{job_id}/cancel` | 안전하게 취소 가능한 대기 작업 취소 |

Command는 `reason`·`expected_version`·`Idempotency-Key`가 필요합니다.
서버는 Tenant·역할·매장 범위를 검사하고 retry/cancel의 allowed와 reason을 제공합니다.
다른 Tenant의 ID는 404로 취급합니다. UI가 상태나 역할로 보안을 대신 결정하지 않습니다.
임의 status PATCH나 임의 SQL/Tool 실행 Endpoint는 만들지 않았습니다.

같은 Tenant·Principal·operation·key와 같은 의미의 요청은 저장된 결과를 replay합니다. 다른 내용은 409 IDEMPOTENCY_CONFLICT입니다.
replay 전에도 현재 권한을 검사합니다. Job 저장·Audit append·멱등성 완료는 기존 공유 트랜잭션에서 함께 commit/rollback됩니다.
Audit에는 주체·Tenant·원본 Job·명령·결과·요청/correlation ID·시각·운영 사유를 기록합니다. 거부 감사 정책은 Day 17을 재사용합니다.
원본 payload와 Worker 예외는 API에 노출하지 않습니다. 사유는 감사 기록이므로 비밀번호·토큰·개인정보를 입력하지 마세요.

### 실제 Queue 화면

기존 화면과 Mock 경로를 유지하며 `api/jobs`로 분리했습니다.
HTTP 모드에서는 목록·상세·retry/cancel을 실제 서버에서 처리하며 Mock을 섞지 않습니다.
ID·종류·우선순위·상태·등록 후 경과·시도/최대 횟수·Incident·correlation·재시도 원본·시각·안전한 오류·permission을 표시합니다.
상세는 기존 Radix Dialog로 열고 로딩·빈 목록·오류를 구분합니다.
제출 중 중복 클릭을 막고 같은 내용의 네트워크 재시도에는 같은 key를 유지합니다. 사유·버전·동작이 달라진 새 명령은 새 key를 사용합니다.
충돌/새로고침 시 기존 상세 snapshot을 버려 최신 상태를 다시 확인합니다.

### 실패 시 동작

| 상황 | 처리 |
| --- | --- |
| 다른 Tenant / 없는 Job | 404 NOT_FOUND, 변경 없음 |
| 역할·매장 권한 부족 | 403 AUTHORIZATION_DENIED, 업무 변경 없음 |
| 같은 key의 다른 내용 | 409 IDEMPOTENCY_CONFLICT, 새 실행 없음 |
| stale version / 잘못된 전이 | 409, 최신 정보 확인 |
| 실행 중 취소 | 중단 미지원 오류; RUNNING 유지 |
| Worker 장애 | lease 만료 후 재인수 또는 횟수 소진 DLQ |
| 늦은 ACK | 완료 기록 거부 |
| Audit insert 실패 | Job·멱등성 결과도 롤백 |
| 일시 실패 / 영구 실패 | 제한된 지연 재시도 / FAILED 보존 |

## 실행/검증

### 로컬 실행

비밀 환경 설정으로 `SERVIQ_REPOSITORY=postgres`와 `SERVIQ_DATABASE_URL`을 지정합니다.

```bash
cd backend
uv run python -m src.infrastructure.migrations
uv run fastapi run
```

같은 Backend 환경을 설정한 별도 터미널에서 Worker를 실행합니다.

```bash
cd backend
uv run python -m src.infrastructure.jobs.runtime --poll-seconds 2
```

Frontend .env.local을 설정하고 Vite를 재시작합니다. 개발 계정은 [Day 17 문서](serviq_access_review.md)를 따릅니다.

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

```bash
cd frontend
npm ci
npm run dev
```

Compose는 기존 환경 설정과 `docker compose --profile serviq up --build -d api frontend worker`를 사용합니다.
기존 Streamlit 경계와 실행은 [배포 문서](serviq_delivery.md)를 참고하세요.

### 실제 검증 결과

2026년 10월 3일 다음 검증을 실제로 수행했습니다.

| 명령/검증 | 결과 |
| --- | --- |
| `uv run --extra dev ruff check .` | 통과, 범위 축소 없음 |
| `uv run --extra dev pytest` | 325 passed |
| Frontend `npm ci` | 성공, 취약점 0건; 로컬 Node 24.12 EBADENGINE 경고 있음 |
| `npm run lint` | 통과 |
| `npm run test` | 14개 파일, 88 passed |
| `npm run build` | 실제 TypeScript·Vite production build 성공 |
| `uv run --extra dev python -m scripts.serviq_postgres_smoke` | 실제 PostgreSQL·Incident·Outbox 통과 |
| `uv run --extra dev python -m scripts.serviq_security_smoke` | Day 17 보안·Review·감사·멱등성 통과 |
| `uv run --extra dev python -m scripts.serviq_queue_smoke` | Job·권한·동시 claim·SKIP LOCKED·우선순위·lease·재시도·DLQ·Audit 롤백·멱등성 통과 |
| `uv run --extra dev python -m scripts.serviq_http_smoke` | nginx·기존 Incident/Review·실제 Queue·독립 Worker 완료 통과 |
| `scripts/compose_smoke.ps1` | 전용 Compose에서 기존 스키마·pgvector·연결 통과 |
| ServIQ Compose build/up/HTTP/stop | API·frontend/nginx·PostgreSQL·Worker 실제 흐름 통과 |
| Backend `uv sync --locked` / FastAPI·Queue CLI help | 통과; Windows 출력은 PYTHONUTF8=1로 확인 |

기존 DB를 지우지 않고 Day 18 전용 테스트 DB와 Compose 프로젝트에서 검증했습니다.
불변 Audit을 포함한 테스트 DB/볼륨은 보존하고 검증 컨테이너는 중지했습니다.
Vite 파일 잠금으로 처음 npm ci가 EPERM 실패했으나 해당 서버만 일시 중지한 뒤 성공하고 기존 5173 서버를 복구했습니다.
새 UI 테스트의 hook 반환 오류와 smoke의 고정 시각 혼용도 수정 후 재실행했습니다. 삭제·skip·xfail·assertion 약화로 숨기지 않았습니다.
pytest의 기존 Starlette/httpx 경고는 남습니다. 원격 CI 결과는 로컬 통과와 구분해 PR에서 확인합니다.

## 제한 사항

PARTIAL / PLANNED:

- 실제 실행기는 읽기 전용 원본 계약 확인 한 종류입니다. 조사·외부 조치·Agent 완료가 아닙니다.
- Redis Streams·Celery·Kafka·Kubernetes는 도입하지 않았습니다. PostgreSQL이 lifecycle 원본입니다.
- Tenant concurrency/fairness·priority aging·backpressure·heartbeat·cooperative cancellation은 후속입니다.
- API는 bounded limit/offset을 제공하지만 화면은 최대 100건 범위입니다. 전체 집계/서버 pagination UI는 후속입니다.
- config_version은 고정 계약 값이며 실제 Control Plane versioning은 아닙니다.
- OIDC/SSO는 미연결입니다. Local Principal은 development/test용이며 production authentication이 아닙니다.
- Jev·LLM Gateway·Gemini/Ollama·LangGraph·Multi-Agent·Harness·MCP·실제 Agent Trace·운영 배포는 구현하지 않았습니다.
- 온라인 migration ledger·운영 DB 권한 분리·백업/복원·일반 개인정보 redaction은 후속입니다.

## 다음 단계

현재 큰 UI GAP는 서버 Dashboard projection과 실제 Settings 연결입니다.
다음 후보는 Approval/실패 Job/Queue 지표와 as_of를 실제 서버로 연결하거나, Job 기반 Worker 정책을 확장하며 Redis 필요성을 검증하는 것입니다.
Day 19 착수 전 최신 main·Drive·열린 PR을 다시 확인해 결정합니다. 이번 Day에서 Jev/LLM으로 넘어가지 않았습니다.
