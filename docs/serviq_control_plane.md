# Day 20 Versioned Control Plane과 Settings

## 목적

Day 19의 실제 Dashboard 다음으로 Settings를 서버의 버전 설정 원본에 연결합니다.
Frontend-first → Contract-first → Domain/Application → PostgreSQL → API → HTTP Adapter 순서를 유지합니다.
기존 Day 1~19의 VOC·RAG·Streamlit·Incident·Review·Job Queue·Dashboard를 대체하지 않습니다.

기준 main은 `a8765e06cb982b23d562255ad867afc604f191fb`(Day 19 PR #37 병합)입니다.
직접 확인한 정본은 [ServIQ_v0.5_운영안전_실행계약_통합설계](https://drive.google.com/drive/folders/1eVwhcoTWaebKUqmJgdGMBF9xY7gXcmmJ)입니다.
00·12·13·20·21·25·28 문서를 확인했으며 v0.4/v0.4.1 fallback은 사용하지 않았습니다.
Drive의 일부 구현현황은 Day 16 스냅샷입니다. 현재 코드의 Day 17~19 완료 상태와 구분하며 Drive 원문은 수정하지 않았습니다.
Day 20 결과는 이 작업 브랜치와 PR의 구현이고 병합 전부터 main 완료로 표현하지 않습니다.

목표는 설정 폼의 저장이 아니라 변경 이유·버전·안전 상한·감사·복원 이력을 함께 보존하는 Control Plane입니다.
설정 계약이 있어도 Jev·Gemini/Ollama·Agent가 실행되는 것은 아닙니다.

## 구성

### 책임과 호환성

| 위치 | 책임 |
| --- | --- |
| `backend/src/domain/config/` | 불변 RuntimeConfig/ConfigVersion, 결정적인 안전 검증 |
| `backend/src/application/config/` | Tenant 조회·서버 diff·변경·복원 Command |
| `backend/src/application/ports/config_repository.py` | 설정 저장소 계약과 버전 충돌 |
| `backend/src/infrastructure/repositories/config_repository.py` | PostgreSQL append-only 저장과 명시적 memory 테스트 구현 |
| `backend/src/infrastructure/access_unit_of_work.py` | Config·Audit·Outbox·Idempotency를 한 트랜잭션으로 기록 |
| `backend/src/api/routes/settings.py`, `schemas/settings.py` | 인증·DTO·4개 Settings Endpoint |
| `frontend/src/api/settings/` | Mock/HTTP Adapter와 응답·오류 검증 |
| `frontend/src/features/settings/ControlPlaneSettings.tsx` | 한국어 설정·해석값·이력·복원 화면 |
| `scripts/serviq_settings_smoke.py` | 실제 PostgreSQL 보안·버전·원자 저장 회귀 |

Domain은 React/FastAPI에 의존하지 않습니다. 기존 Principal/RBAC·Audit·멱등성·UoW를 재사용합니다.
새 SDK나 의존성은 추가하지 않았으며 Incident 상태머신과 Review/Job 업무 규칙은 유지합니다.

### Runtime Config 계약

| 영역 | 저장 가능한 설정 |
| --- | --- |
| Queue | `tenant_queue_concurrency`, `priority_policy`, `retry_limit`, `backoff_seconds` |
| Approval | `approval_policy_by_risk`, `required_roles`, `separation_of_duties`, `critical_approver_count` |
| Agent/Workflow | `max_agent_iterations`, `max_tool_calls`, `parallelism`, `timeout_seconds`, `token_budget`, `cost_budget_usd`, `verification_window_hours`, `allowed_tools` |
| 자동화 | `jev_enabled`, `auto_investigation`, `auto_rca_draft`, `auto_capa_draft`, `auto_execute` |
| 향후 LLM Gateway | `default_llm_provider`, `fallback_llm_provider`, `provider_concurrency`, `provider_timeout_seconds`, `structured_output_retry` |
| 기존 Gemini 표시 계약 | `gemini_concurrency`, `gemini_rate_limit`, `gemini_timeout_seconds` |

기본 Provider는 Gemini, 대체 Provider는 Ollama입니다. 공통 Gateway 필드는 Provider와 독립적입니다.
Gemini 표시 필드는 기존 UI와의 호환성을 유지하며 실제 외부 호출·모델 선택·데이터 정책 적용은 구현하지 않았습니다.
역할·도구 목록도 불변 tuple로 보관하여 외부 리스트 변경으로 snapshot이 바뀌지 않습니다.

ConfigVersion은 `config_version`, `tenant_id`, `scope`, `config`, `reason`, `created_by`, timezone-aware `created_at`, `parent_version`, `rollback_source`를 보존합니다.
버전은 Tenant 안에서 증가합니다. 저장 전 현재 버전은 **0**이며 플랫폼 기본값입니다. GET은 버전을 생성하지 않습니다.

### Resolution과 System Safety Cap

현재 지원 계층은 플랫폼 기본값·Tenant 설정·서버 안전 상한입니다.
workflow/run override와 별도 platform policy 영속화는 아직 구현하지 않았습니다.
서버는 raw `config`, 검증된 `effective`, 필드별 `sources`, `rules`, `adjusted_fields`를 반환합니다.
Frontend는 병합·권한·상한을 독자적으로 계산하지 않습니다.

상한 초과는 조용히 낮추지 않고 `CONFIG_VALIDATION_FAILED`로 거부합니다.
따라서 성공 시 raw/effective가 같고 `adjusted_fields`는 비어 있습니다.
출처는 `PLATFORM_DEFAULT` 또는 `TENANT`입니다.

| 설정 | 서버 허용 범위 |
| --- | --- |
| 반복 / 도구 호출 | 1~20 / 1~50 |
| 병렬 / Tenant 동시 작업 | 각각 1~10 |
| 실행 시간 / 토큰 / 비용 | 5~600초 / 100~100,000 / 0.01~20 USD |
| Gateway·Gemini 동시 요청 / 제한 시간 | 1~10 / 5~300초 |
| Gemini 분당 요청 / 구조화 재시도 | 1~300 / 0~3 |
| Queue 재시도 / 기본 대기 | 0~10 / 1~60초 |
| 긴급 승인자 / 검증 기간 | 2~5명 / 1~168시간 |

숫자 문자열·boolean을 숫자로 변환하는 입력·무한대·잘못된 역할/Provider/도구는 거부합니다.
HIGH/CRITICAL 사람 승인과 요청자·승인자 분리 계약은 해제할 수 없습니다.
승인 역할은 기존 HQ_ADMIN/REVIEWER로 제한합니다.
예약 읽기 도구는 `incident.get`, `voc.search`, `inventory.snapshot`, `transaction.search`입니다.
실제 Tool 실행기는 없으며 `execute_sql`이나 임의 shell은 허용하지 않습니다.
`auto_execute=true`를 저장해도 기존 승인 Command·상태머신을 우회하거나 자동 실행하지 않습니다.

### PostgreSQL Versioning과 실행 계약

`007_control_plane.sql`은 `serviq_config_versions`를 추가합니다.
Tenant/버전 복합 PK, 동일 Tenant 부모·복원 원본 FK, 현재 조회 인덱스와 UPDATE/DELETE 금지 trigger를 사용합니다.
모든 변경은 INSERT이며 기존 001~006 migration은 수정하지 않았습니다.
`expected_version`과 조직 advisory transaction lock으로 첫 버전 생성부터 동시 수정을 보호합니다.
같은 현재 버전으로 다른 내용을 저장하면 한 요청은 VERSION_CONFLICT입니다.

`008_config_outbox.sql`은 기존 Incident FK를 보존하면서 독립 config.changed 이벤트에만 Incident ID 없는 참조를 허용합니다.
이벤트에는 설정 원문 대신 Tenant·aggregate/version·부모·복원 원본·correlation/time 참조를 기록합니다.
기존 Outbox Worker는 계약 검증과 전달 완료만 기록하며 Agent나 Job을 새로 실행하지 않습니다.

변경·복원은 HQ_ADMIN, 필수 사유(1~1000자), expected_version, Idempotency-Key를 검사합니다.
Tenant·Principal·Command 범위의 fingerprint를 영속 저장합니다.
동일 key/동일 요청은 원래 결과를 반환하며 버전·성공 감사·이벤트를 중복 생성하지 않습니다.
다른 내용은 IDEMPOTENCY_CONFLICT이며 replay 전에도 RBAC를 검사합니다.
Config INSERT·SUCCESS Audit·Outbox·멱등 결과는 같은 UoW입니다. Audit 실패도 전체 롤백합니다.
권한 거부는 DENIED Audit으로 기록하며 내부 DB 오류·secret을 응답에 노출하지 않습니다.
변경 사유에 비밀번호·토큰·고객 원문을 넣지 마세요.

Rollback은 과거 row를 current로 바꾸지 않습니다.
snapshot을 현재 상한으로 재검증하고 새 버전을 생성합니다.
v2에서 v1을 복원하면 새 v3의 `parent_version=2`, `rollback_source=1`입니다.
과거 설정이 현재 상한을 위반하면 복원을 거부하고 기존 이력은 유지합니다.

### Query/Command API

| Endpoint | 역할 |
| --- | --- |
| `GET /api/v1/settings/runtime` | raw/effective/source/rules, 현재 버전·변경자·사유, 서버 Permission |
| `GET /api/v1/settings/runtime/history` | snapshot·변경자·시각·사유·부모·복원 원본·서버 diff |
| `POST /api/v1/settings/runtime` | 전체 config·expected_version·필수 reason으로 새 버전 생성 |
| `POST /api/v1/settings/runtime/rollback` | target_version·expected_version·필수 reason으로 복원 버전 생성 |

조회는 기존 read 역할을 사용하며 AUDITOR도 읽을 수 있습니다. 수정·복원은 HQ_ADMIN만 가능합니다.
Repository 조회·변경은 항상 Principal Tenant 범위이며 다른 조직의 버전으로 복원할 수 없습니다.
history는 기본 limit 20, 범위 1~100, offset 0~10000, has_more를 제공합니다.
`changes`는 부모 대비 변경, `rollback_changes`는 현재에서 해당 snapshot 복원 시의 변경입니다.
`compared_to_version`을 함께 반환하여 UI가 JSON 비교를 재구현하지 않습니다.

### 실제 화면과 실패 동작

기존 한국어 Tailwind/Radix UI를 유지합니다.
현재 버전·변경자·사유, Provider/예산/Queue/승인/도구, effective/source/상한, 이력 페이지와 복원 diff를 표시합니다.
서버 Permission의 비활성 사유를 사용하며 제출 중 이중 클릭을 막습니다.
같은 입력의 네트워크 재시도는 같은 key, 새로운 독립 변경은 새 key입니다.
복원은 현재·대상 버전·차이·사유·위험 안내를 보여줍니다.

Mock은 미리보기·테스트이고 HTTP는 실제 서버만 사용합니다. 오류나 잘못된 응답에 fixture fallback하지 않습니다.
화면은 **향후 Runtime 적용 설정 · 현재 Runtime 미연결**을 명시합니다.

| 오류 | 사용자 처리 |
| --- | --- |
| 401 | 서버에 등록된 개발 인증 또는 인증 설정 확인 |
| 403 AUTHORIZATION_DENIED | 조회·수정 역할 구분, HQ_ADMIN 권한 확인 |
| 404 NOT_FOUND | 현재 조직에서 복원 가능한 버전인지 확인 |
| 409 VERSION_CONFLICT | 최신 설정을 불러와 변경·복원 내용 재검토 |
| 409 IDEMPOTENCY_CONFLICT / PROCESSING | 요청 key 내용 충돌과 처리 중 상태 구분 |
| 422 | 필드별 안전 범위·승인 정책 오류와 request_id 확인 |
| 503 SETTINGS_UNAVAILABLE | 저장소 확인, 성공이나 예시로 대체하지 않음 |

## 실행/검증

API는 기존처럼 backend/에서 실행합니다. DSN·개발 Principal 계정은 [Day 17 문서](serviq_access_review.md)를 따릅니다.
설정 수정에는 서버에 등록된 HQ_ADMIN 계정을 사용합니다. 브라우저가 Tenant/Role을 직접 지정하지 않습니다.

```bash
cd backend
uv sync --locked
uv run python -m src.infrastructure.migrations
uv run fastapi run
```

migration은 SERVIQ_DATABASE_URL을 설정한 PostgreSQL 환경에서 실행합니다.
명시적 In-Memory 개발 모드는 DB 없이 동작하지만 재시작 영속성을 보장하지 않습니다.
화면은 별도 터미널의 frontend/에서 npm ci, npm run dev로 실행합니다.

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

로컬 인증이 필요하면 .env.local에 서버에 등록된 개발 토큰을 설정하고 Vite를 재시작합니다.
VITE 변수는 공개되므로 운영 비밀이나 OIDC client secret을 넣지 않습니다.

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest
cd frontend
npm ci
npm run lint
npm run test
npm run build
```

루트에서 전용 DB의 SERVIQ_TEST_DATABASE_URL을 명시하고 실제 smoke를 실행합니다.

```bash
uv run --extra dev python -m scripts.serviq_postgres_smoke
uv run --extra dev python -m scripts.serviq_security_smoke
uv run --extra dev python -m scripts.serviq_queue_smoke
uv run --extra dev python -m scripts.serviq_dashboard_smoke
uv run --extra dev python -m scripts.serviq_settings_smoke
uv run --extra dev python -m scripts.serviq_http_smoke
```

HTTP smoke는 테스트용 API/nginx 주소를 SERVIQ_TEST_API_BASE_URL로 지정합니다.
Compose/PowerShell 절차는 [실행·CI/CD 문서](serviq_delivery.md)를 따릅니다. 사용자 DB를 테스트나 삭제 대상으로 사용하지 않습니다.

### 실제 검증 결과

- 전체 ruff 통과, Python **364 passed**. 기존 Starlette/httpx deprecation 경고 1건이 남습니다.
- npm ci 성공, 취약점 0건. Node.js 24.12에서는 기존 의존성의 EBADENGINE 경고가 있었습니다.
- 첫 전체 Frontend 실행은 Windows Worker 시작 시간 초과로 실패했습니다. 지원 Node.js 24.21로 같은 명령을 재실행하여 **19개 파일, 117 passed**를 확인했습니다. 테스트·assertion·timeout은 변경하지 않았습니다.
- Frontend lint, 두 번의 production build와 빌드 후 lint가 모두 통과했습니다.
- 실제 PostgreSQL·security·Queue·Dashboard·Settings smoke 모두 통과했습니다. 격리된 Day 20 테스트 DB를 사용했습니다.
- Settings smoke는 동시 수정·동시/재시작 replay·타 Tenant 복원 차단·과거 row 수정/삭제 차단·Audit 실패 원자 롤백·현재 상한 재검증을 확인했습니다.
- backend/ lockfile 실행, FastAPI 진입점·Settings OpenAPI·migration 리소스 확인이 통과했습니다.
- scripts/compose_smoke.ps1과 최종 코드 Compose build/start/health/migration/nginx HTTP smoke가 통과했습니다.
- 기존 Incident/Review/Queue/Dashboard 및 Settings 저장·이력·복원을 실제 nginx에서 검증했습니다. config.changed 6건과 기존 Incident 이벤트가 모두 COMPLETED입니다.
- 테스트용 Compose 서비스는 중지했고 볼륨·기존 사용자 DB는 보존했습니다.
- CI에는 Settings PostgreSQL smoke를 추가했습니다. 로컬 결과와 PR의 원격 Actions 결과는 구분합니다.

## 제한 사항

IMPLEMENTED는 코드·테스트로 확인한 타입·상한·append-only 버전·조회/변경/복원 API·Audit/Idempotency/Outbox·Settings HTTP 화면입니다.

PARTIAL / PLANNED는 다음과 같습니다.

- production OIDC/SSO는 없습니다. local/dev Principal resolver는 production authentication이 아닙니다.
- Queue concurrency/retry/backoff의 실제 Worker enforcement·tenant backpressure는 미연결입니다.
- 승인자 수·역할·요청자 분리 설정의 동적 Runtime 적용은 후속 과제입니다. Day 17 승인 안전 경계는 유지합니다.
- workflow/run override·동적 platform policy·Provider 데이터 정책은 예약 경계입니다.
- Jev·LLM Gateway·Gemini/Ollama Runtime·LangGraph·AgentRun·Multi-Agent·Harness·MCP는 구현하지 않았습니다.
- 허용 도구 이름은 향후 계약이며 Tool 실행기가 아닙니다. config.changed를 소비하는 Agent Runtime도 없습니다.
- Integrations/SyncJob·Agent Trace는 실제 운영 원본에 연결되지 않았습니다.
- Redis Streams·Kubernetes·실제 Connector·production deployment·Production Readiness 전체를 완료했다고 선언하지 않습니다.

## 다음 단계

다음 Day 시작 시 최신 main·열린 PR·Drive 버전을 다시 확인합니다.
Control Plane 이후 로드맵 후보는 작은 deterministic/shadow Jev 결정 계층입니다.
Hosted LLM 도입 전 데이터 정책·실행별 config snapshot·현재 상한 재검증을 먼저 확정합니다.
실제 Integration/SyncJob·Worker 정책 적용도 별도 완료 기준으로 추적하며 설정의 존재를 실행 완료로 혼동하지 않습니다.
