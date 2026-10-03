# Day 19 실제 Dashboard Projection

## 목적

Day 18의 실제 Incident·Approval·Job 원본으로 운영 Dashboard를 연결합니다.
Frontend-first → Contract-first → Query/Application → PostgreSQL projection → API → HTTP Adapter → 실제 smoke 순서를 따릅니다.
기존 Day 1~18의 ingestion·PostgreSQL/pgvector·RAG·Streamlit·Incident·Review·Queue는 보존합니다.

기준 main은 `3c75db0605c8c05d30442570307ee7f697e848ce`(Day 18 PR #35 병합)입니다.
직접 확인한 최신 정본은 [ServIQ_v0.5_운영안전_실행계약_통합설계](https://drive.google.com/drive/folders/1eVwhcoTWaebKUqmJgdGMBF9xY7gXcmmJ)이며 v0.4/v0.4.1 fallback은 사용하지 않았습니다.
00·06·13·20·21·25·28·14를 실제로 확인했습니다. Drive의 Day 16 c6060ae 스냅샷과 현재 main의 Day 17~18 완료 상태를 구분합니다.
Day 19 결과는 이 작업 브랜치와 PR의 구현이며 병합 전부터 main 완료로 표현하지 않습니다. Drive 원문은 수정하지 않았습니다.

## 구성

### 책임과 호환성

| 계층 | 책임 |
| --- | --- |
| `frontend/src/contracts/types.ts`, `api/dashboard/` | 단일 DashboardSnapshot, Mock/HTTP 경계와 응답 검증 |
| `backend/src/application/dashboard/` | 읽기 전용 Contract, Principal/기간 검사, 주입 가능한 clock |
| `backend/src/infrastructure/dashboard_projection.py` | 실제 PostgreSQL 집계와 명시적 memory 모드 |
| `backend/src/api/routes/dashboard.py`, `schemas/dashboard.py` | GET DTO·인증 경계·stable error |
| `frontend/src/features/dashboard/` | 한국어 KPI·추세·분포·기준 시각·상세 이동·새로고침 |
| `scripts/serviq_dashboard_smoke.py` | 실제 DB 범위·집계·읽기 전용·Worker 연결 검증 |

IMPLEMENTED는 위 코드와 테스트로 확인한 범위입니다.
Dashboard는 업무 Command나 새로운 상태머신이 아닌 Query입니다.
현재 규모에서는 live query가 충분하므로 writable projection table·event consumer·Redis·별도 OLAP DB를 추가하지 않았습니다.
새 dependency나 migration은 없으며 기존 001~006 SQL도 수정하지 않았습니다.
기존 Incident/Approval/Job 저장소 Port는 Dashboard 집계 때문에 변경하지 않았습니다.

### Projection Contract

`GET /api/v1/dashboard?window=7d`를 사용합니다. 현재 지원 기간은 7d 하나입니다.

| 응답 필드 | 의미 |
| --- | --- |
| `as_of` | 서버 Query가 한 번 읽은 timezone-aware UTC 기준 시각 |
| `window`, `timezone` | 7d, UTC |
| `kpis` | open_incidents, critical_incidents, pending_approvals, failed_jobs, dlq_jobs, queue_depth, running_jobs |
| `incident_trend` | day(UTC YYYY-MM-DD), detected, resolved; 0인 날짜도 포함한 7개 버킷 |
| `root_cause_distribution` | label과 실제 원인 후보 count |
| `capa_status` | PROPOSED/APPROVED/EXECUTED별 count; 없으면 각각 0 |
| `priority_incidents` | 조회 범위 안의 열린 사건 최대 4개: id/title/store/owner/severity |
| `integration_health` | NOT_IMPLEMENTED와 준비 중 사유; 가짜 연동 상태를 반환하지 않음 |

브라우저가 Incident·Review·Queue API를 여러 번 호출하여 KPI를 합산하지 않습니다.
HTTP 화면의 운영 정보는 Dashboard 응답 하나로 표시합니다.

### KPI 정의

| 지표 | 고정 계산 규칙 |
| --- | --- |
| Open Incident | 현재 status가 RESOLVED/CLOSED가 아닌 사건; 예외 상태도 포함 |
| Critical Incident | 위 열린 사건 중 severity=CRITICAL |
| Pending Approval | 실제 Approval status=PENDING 기록 수; Incident의 Tenant/store와 연결 |
| Failed Job / DLQ Job | 실제 Job status=FAILED / DLQ 각각 분리 |
| Queue Depth | Job status=PENDING 전체; 미래 available_at의 예약 대기 포함 |
| Running Job | RUNNING 별도 집계; Queue Depth와 합치지 않음 |
| Incident Trend 감지 | 날짜 버킷 안에 created_at이 있는 사건 수 |
| Incident Trend 해결 | 사건별 as_of 이전 마지막 RESOLVED timeline 기록의 날짜; 한 사건의 중복 해결 기록은 한 번 |
| RCA Distribution | 안정적인 category가 없어 실제 root_cause_candidates 수를 미분류로 집계; 0이면 빈 목록 |
| CAPA Status | 범위 안 전체 Incident의 실제 corrective_actions 상태별 수 |

현재 KPI·RCA·CAPA는 최근 7일 생성 사건만이 아니라 범위 안 전체 원본을 집계합니다.
COMPLETED/CANCELLED Job은 Queue Depth에 포함하지 않습니다.
Pending Approval은 상태 count이며 만료 여부나 즉시 실행 가능한 승인 건수를 뜻하지 않습니다.
원인 후보·조치는 해결/종결 사건의 기록도 포함합니다. 존재하지 않는 LLM category를 만들어내지 않습니다.

### as_of와 날짜

clock은 테스트에서 주입할 수 있으며 naive timestamp는 거부합니다.
추세 범위는 UTC 오늘 00:00에서 6일 전부터 as_of까지(경계 포함)입니다.
created_at이 as_of보다 미래인 사건/Job, requested_at이 미래인 Approval은 집계하지 않습니다.
이 API는 현재 snapshot의 관찰 시각을 제공하며 과거 시각의 업무 상태를 재구성하는 historical/time-travel API가 아닙니다.

PostgreSQL은 `REPEATABLE READ READ ONLY` transaction에서 모든 집계를 수행하며 statement timeout은 5초입니다.
여러 SELECT가 같은 DB snapshot을 읽고 상태·버전·Audit·Outbox·멱등성 기록을 변경하지 않습니다.
목록 API의 100건 제한을 적용하지 않고 SQL count/JSONB 집계를 사용합니다.

### Tenant와 보안

기존 Principal/RequestContext와 중앙 read authorization을 재사용합니다.
모든 Incident·Approval·Job SQL에 tenant predicate와 store_scope를 적용합니다.
Approval은 같은 Tenant의 Incident와 JOIN합니다.
STORE_MANAGER의 빈 매장 범위는 전체 접근으로 확대하지 않습니다.
다른 Tenant의 정보는 count·trend·distribution·우선 사건 목록으로도 전달하지 않습니다.

전체 document·원본 payload·RCA/CAPA 본문·DB 오류 세부정보·다른 Tenant 식별자를 노출하지 않습니다.
우선 사건 목록은 기존 읽기 권한 범위에서 제목·담당자 등 화면에 필요한 최소 필드만 반환합니다.
Dashboard 조회는 새 Audit/Idempotency business effect를 만들지 않습니다.

### Mock/HTTP와 실패

기본 Mock은 화면 검토용 예시이며 실제 KPI와 혼합하지 않습니다.
HTTP는 서버 단일 Snapshot만 사용하고 실패 시 fixture나 memory로 조용히 fallback하지 않습니다.
memory는 명시적 Backend 개발 모드이며 PostgreSQL 장애 대체 경로가 아닙니다.

401 인증 필요, 403 권한 부족, 422 VALIDATION_ERROR(기간), 503 DASHBOARD_UNAVAILABLE(집계 실패)을 구분합니다.
Frontend는 NETWORK_ERROR·CONTRACT_ERROR와 HTTP 오류를 사용자 안내/요청 ID로 표시합니다.
로딩 중과 오류 화면에서는 오래된 KPI를 최신 성공값처럼 표시하지 않습니다.
정상 빈 조직은 0 지표와 빈 안내를 제공합니다.
Integration Health는 실제 Integration/SyncJob 원본이 없어 준비 중입니다. 기존 Integration Mock을 실제 Dashboard KPI에 합치지 않습니다.

우선 사건은 severity 우선·최신 생성 시각·ID 순으로 결정적으로 정렬하고 기존 상세 팝업으로 이동합니다.
최신 정보 불러오기는 새 서버 Query를 수행합니다. 화면의 Tenant filtering이나 상태 추측은 보안 판단을 대신하지 않습니다.

## 실행/검증

### 실행

기존 [Day 17 인증 설정](serviq_access_review.md)과 [실행 디렉터리](serviq_structure.md)를 따릅니다.
Backend 셸에는 `SERVIQ_REPOSITORY=postgres`와 비밀 `SERVIQ_DATABASE_URL`을 설정합니다.

```bash
cd backend
uv sync --locked
uv run python -m src.infrastructure.migrations
uv run fastapi run
```

Frontend의 .env.local에 설정하고 Vite를 재시작합니다. 개발 인증은 서버 등록 Local Principal을 사용하며 VITE 값에 운영 비밀을 넣지 않습니다.

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

```bash
cd frontend
npm ci
npm run dev
```

Compose 실행과 기존 Streamlit은 [배포 문서](serviq_delivery.md)를 참고하세요.

### 실제 검증 결과

2026년 10월 3일 아래 명령을 실제 실행했습니다.

| 검증 | 결과 |
| --- | --- |
| `uv run --extra dev ruff check .` | 전체 범위 통과 |
| `uv run --extra dev pytest` | 333 passed, 기존 Starlette/httpx 경고 1개 |
| Frontend `npm ci` | 성공, 취약점 0건; Node 24.12의 EBADENGINE 경고 있음 |
| `npm run lint` | 통과 |
| `npm run test` | 17개 파일, 99 passed |
| `npm run build` | 실제 TypeScript/Vite production build 성공 |
| `uv run --extra dev python -m scripts.serviq_postgres_smoke` | 기존 실제 Incident/Outbox 통과 |
| `uv run --extra dev python -m scripts.serviq_security_smoke` | 기존 실제 Tenant/RBAC/Approval/Audit/멱등성 통과 |
| `uv run --extra dev python -m scripts.serviq_queue_smoke` | 기존 Job/Worker/Queue 안전성 통과 |
| `uv run --extra dev python -m scripts.serviq_dashboard_smoke` | 실제 DB 범위·UTC 경계·105건 대기 집계·RCA/CAPA·no mutation·오류·Worker 상태 변화 통과 |
| `uv run --extra dev python -m scripts.serviq_http_smoke` | nginx Incident/Review/Queue/Dashboard 및 실제 Worker 완료 통과 |
| `scripts/compose_smoke.ps1` | 기존 스키마·pgvector·연결 통과 |
| ServIQ Compose build/up/migration/health/HTTP/stop | API·frontend/nginx·DB·Worker 실제 흐름 통과 |
| Backend `uv sync --locked`, entry point/OpenAPI, FastAPI CLI help | 통과; Windows PYTHONUTF8=1 사용 |

CI에는 기존 PostgreSQL→security→Queue 뒤 Dashboard smoke를 추가했고 nginx smoke에도 생성·승인·종결·RCA/CAPA 지표 변화를 추가했습니다.
원격 CI는 로컬 통과와 구분해 PR에서 확인합니다.

초기 테스트 경로 오지정은 테스트 수행으로 계산하지 않았습니다.
앱 테스트 한 번의 timeout은 같은 timeout/assertion으로 재실행하고 최종 전체 99개가 통과했습니다.
실제 PostgreSQL 날짜 alias 오류를 수정한 뒤 DB smoke와 전체 Python을 재실행했습니다.
Dashboard fixture를 먼저 넣은 DB는 기존 PostgreSQL smoke의 ‘대기 작업 없는 DB’ 조건에 맞지 않아 새 전용 DB에서 CI 순서로 검증했습니다.
실패를 삭제·skip·xfail·assertion 약화나 timeout 증가로 숨기지 않았습니다.

Day 19 전용 DB와 Compose 프로젝트를 사용했고 기존 사용자 DB를 삭제하지 않았습니다.
불변 Audit을 포함한 테스트 DB/볼륨은 보존하고 검증 스택은 중지했습니다.
npm ci 파일 잠금 해제를 위해 이 저장소 Vite만 일시 중지했으며 5173 개발 서버를 복구하고 HTTP 200을 확인했습니다.

## 제한 사항

PARTIAL / PLANNED:

- 지원 window는 7d 하나이고 날짜 기준은 UTC입니다. Tenant별 운영 시간대·임의 기간·historical snapshot은 미지원입니다.
- RCA는 category가 없는 실제 후보를 미분류로 표시합니다. 검증된 원인 유형 taxonomy는 후속입니다.
- Integration Health는 실제 원본이 없어 NOT_IMPLEMENTED입니다.
- live query 비용·큰 JSONB/timeline 크기·DB pool·정교한 집계 index/load baseline은 후속입니다. 지금 별도 projection DB를 추가하지 않습니다.
- Settings 실제 API, Integrations 실제 API/SyncJob, Agent Trace Runtime은 아직 없습니다.
- Tenant concurrency/backpressure·Redis Streams 검증/도입은 후속입니다.
- Jev·LLM Gateway·Gemini/Ollama·LangGraph·Multi-Agent·Harness/MCP는 구현하지 않았습니다.
- production OIDC/SSO와 Production Readiness 전체는 미완료입니다. Local Principal이나 Compose smoke 성공을 production-ready로 표현하지 않습니다.
- 기존 Docker Python 설치 방식의 dependency 고정 강화, 운영 migration/backup/observability도 별도 검증이 필요합니다.

## 다음 단계

v0.5 UI 순서에서 다음 후보는 Settings의 실제 versioned Control Plane 계약/API입니다.
Integrations는 실제 원본/SyncJob이 생긴 뒤, Agent Trace는 실제 Runtime이 생긴 뒤 연결합니다.
Worker 운영 정책·Redis 필요성도 현재 GAP로 남습니다.
Day 20 착수 전 최신 main·Drive·열린 PR과 구현 현황을 다시 확인하여 우선순위를 결정합니다.
