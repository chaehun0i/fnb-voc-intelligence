# Day 22 LLM Gateway

## 목적

Day 21 Jev Shadow 뒤에 정책·구조화 응답·사용량·오류 계약을 가진 Provider 중립 LLM 실행 경계를 추가합니다. Agent나 업무 코드가 Gemini/Ollama SDK에 직접 의존하지 않도록 하는 작은 Vertical Slice입니다. 기존 RAG, Streamlit, Incident/Review/Queue/Dashboard/Settings와 Jev Shadow는 보존합니다.

기준 main은 `3e2f62b41e8649d4602f35827a342202b102c7df`이며 PR #41까지 병합된 Day 21 상태입니다. 설계 정본은 [ServIQ v0.5 운영안전·실행계약 통합설계](https://drive.google.com/drive/folders/1eVwhcoTWaebKUqmJgdGMBF9xY7gXcmmJ)입니다. 작업 시작 시 더 높은 버전은 없었고 v0.4/v0.4.1 fallback을 사용하지 않았습니다. Drive 원문은 수정하지 않았습니다.

v0.5 일부 구현현황은 Day 16 스냅샷입니다. 실제 main의 Day 17~20 운영 안전·Review·Queue·Dashboard·Control Plane과 Day 21 Jev를 다시 만들지 않습니다. 문서 23·37을 중심으로 12·14·16·18·20·21·25·28·36의 실제 책임 계약과 대조했습니다.

현재 → 목표: 외부 AI를 호출하지 않는 Jev 판단에서, 명시적인 Application 요청에 한해 AI를 안전하고 교체 가능하게 호출할 수 있는 Gateway 경계로 확장합니다. **Jev의 `requires_llm`은 자동 호출 명령이 아닙니다.** 이번 Day에도 Job/Incident/Agent 자동 실행에 연결하지 않습니다.

## 구성

### 공통 계약과 책임

명시적 `LLMApplication` → Principal/Tenant/Config snapshot → Data Policy → Gateway/Router → Provider Protocol → Fake/Gemini/Ollama 순서입니다. `src.ai.intelligence.service.configured_llm_application()`이 wiring을 제공하며 공개 prompt POST API는 없습니다.

| 위치 | 역할 |
| --- | --- |
| `backend/src/ai/intelligence/models.py` | 불변 Intent/Request/Response/Usage/Result·Provider Protocol·capability·안정된 오류 코드 |
| `backend/src/ai/intelligence/service.py` | PII 최소화·전송 정책·schema/업무 의미 검증·Config 선택·공유 예산·deadline·제한 retry/repair/fallback |
| `backend/src/ai/intelligence/providers/` | Fake, 공식 Gemini SDK, Ollama HTTP 어댑터 |
| `backend/src/ai/intelligence/service.py` | 명시적 HQ_ADMIN 실행·Tenant/store 조회·Gateway 조립·환경 설정 (공통 계약과 SDK 분리) |
| `backend/src/infrastructure/repositories/llm_call_repository.py` | 메모리 검증용/실제 PostgreSQL 사용 기록 |
| `db/migrations/010_llm_calls.sql` | 추가 테이블·FK·인덱스·append-only trigger |

`LLMIntent`는 request/correlation/tenant/incident, task/model class, 입력 참조, 최소 JSON payload, output schema/version, prompt template/version, token·비용·deadline, fallback 허용, classification, Config version을 전달합니다. 시간대 없는 deadline, 잘못된 enum/JSON/예산은 거부합니다. prompt/response와 정책 payload는 객체 repr에서도 숨깁니다.

Task는 TRIAGE/RCA/CAPA/SUMMARY/CLASSIFICATION/EXTRACTION, 모델 등급은 FAST/STANDARD/REASONING입니다. Provider 객체·예외는 공통 계약 밖으로 노출하지 않습니다. Jev/Domain/Application의 SDK 직접 import를 회귀 테스트로 차단합니다.

기존 RAG의 `generate(str) -> str`는 Tenant·정책·schema·usage를 표현하지 못하므로 그대로 유지하고 ServIQ 계약을 추가했습니다. `google-genai`, `jsonschema`, runtime `httpx`를 lockfile에 반영했습니다. [공식 Google Gen AI SDK](https://googleapis.github.io/python-genai/)와 [Ollama 공식 chat API](https://docs.ollama.com/api/chat)를 어댑터로 격리해 교체 비용을 제한합니다. 별도 Agent 프레임워크·서비스는 추가하지 않았습니다.

### Data Policy와 구조화 출력

Classification은 PUBLIC/INTERNAL/CONFIDENTIAL/PII/RESTRICTED이며 policy 결과 계약은 ALLOW/ALLOW_REDACTED/DENY/HUMAN_ONLY입니다. 거부는 Provider 장애가 아닌 `POLICY_DENIED`입니다.

- RESTRICTED는 이번 경계에서 로컬도 보수적으로 거부합니다.
- hosted Provider는 `hosted_ai_allowed=false`일 때 호출하지 않습니다.
- customer_name/phone/email/address/external_customer_id와 credential/secret/raw document 필드는 중첩 dict/list에서도 제거합니다.
- 자유 텍스트 PII 탐지는 제공하지 않습니다. PII/CONFIDENTIAL 입력은 신뢰할 수 있는 Application의 별도 검토 표시가 필요하며 정확한 classification 부여도 Application 책임입니다.
- 실제 호출과 fallback 모두 정책을 선검증하고 원문 prompt/response/PII/API key를 기록하지 않습니다.

JSON 문법·JSON Schema와 업무 검증 hook을 구분합니다. 외부 `$ref`/`$dynamicRef`/`$recursiveRef`와 NaN/Infinity를 차단합니다. schema가 유효해도 알 수 없는 Evidence ID는 `OUTPUT_DOMAIN_INVALID`입니다. schema repair는 설정이 더 높아도 전체 실행에서 최대 한 번이며, 최소 입력과 공통 수정 지시만 재사용하고 이전 응답 원문은 복제하지 않습니다. 업무 의미 오류는 repair하지 않습니다.

### Config 기반 routing과 실행 안전

Day 20 Runtime Config에 `llm_enabled_providers`, `llm_models`(Provider/등급별 모델명·입력/출력 백만 토큰당 예상 요금), `llm_fallback_allowed`를 추가했습니다. 변경은 기존 Settings의 version/RBAC/Audit/Idempotency 계약을 재사용합니다.

이전 Config Version은 허용 목록과 모델 mapping이 비어 있고 fallback이 꺼진 안전한 기본값으로 읽습니다. 기존 `default_llm_provider=gemini`, `fallback_llm_provider=ollama`만으로 외부 호출이 시작되지 않습니다. 모델·허용·정책을 명시해야 하며 가격은 운영자가 검토한 versioned 값이지 코드의 고정 가격표가 아닙니다.

Application은 tenant-scoped Config Version을 한 번 읽어 snapshot으로 전달합니다. Jev/Gateway가 설정을 임의 재조회하지 않습니다. Router는 허용·mapping·structured capability·model class·Data Policy·예산을 검사합니다. timeout은 Config Provider/Gemini 상한과 deadline 잔량 중 작은 값입니다.

일시 오류·429·일부 5xx는 전체 실행에서 최대 한 번 재시도합니다. 영구 입력/정책/capability/예산/반복 schema 오류는 재시도하지 않습니다. Fallback은 Intent와 Config 모두 허용하고 대체 Provider의 정책/capability와 공유 예산/deadline이 남았을 때에만 한 번 수행합니다. 동일 Provider로 다시 fallback하지 않습니다.

retry·repair·fallback은 동일 예산을 공유합니다. 입력 UTF-8 크기·schema·여유분과 최대 출력으로 보수적으로 예약하고 보고된 usage로 차감합니다. timeout 등 사용량 미확인 실패는 예약량 전체를 차감합니다. 이는 예상 비용 관리이지 Provider 청구 금액 보증이 아닙니다.

### Provider와 안전한 사용 기록

FakeProvider는 명시적 응답/오류 시퀀스를 네트워크 없이 재현합니다. Gemini는 공식 SDK v1 API, JSON Schema, 밀리초 timeout, 추가 SDK retry 없는 설정을 사용하고 reasoning 포함 usage를 정규화합니다. 키는 `GEMINI_API_KEY` 환경 경계에서만 읽으며 누락/인증 오류는 `PROVIDER_NOT_CONFIGURED`입니다.

Ollama는 httpx의 `/api/chat`, JSON Schema format, `stream=false`를 사용합니다. 현재 URL은 loopback만 허용하며 redirect/proxy를 사용하지 않습니다. Ollama가 없더라도 import/startup은 깨지지 않습니다. Docker 내부 Ollama 서비스 연결은 아직 이번 URL 정책의 지원 범위가 아닙니다.

호출 기록은 provider/model/config/task, request/correlation/incident, template/schema version, classification/redacted, 최소 입력 digest, token·예상 비용·latency, retry/repair/fallback, 오류 코드만 포함합니다. 실패의 usage 미확인 상태를 성공으로 꾸미지 않습니다. Provider 호출 전 거부는 실패 코드로 반환하고 청구된 LLM call로 기록하지 않습니다.

`serviq_llm_calls`는 tenant-scoped Incident/Config FK를 갖고 UPDATE/DELETE를 trigger로 차단합니다. 외부 호출 동안 DB transaction을 유지하지 않습니다. 기록 저장 실패는 `TRACE_UNAVAILABLE`이며 외부 호출을 재실행해 숨기지 않습니다. 메모리는 테스트용이고 PostgreSQL 모드에서만 재시작 후 영속성이 보장됩니다.

읽기 전용 `GET /api/v1/incidents/{incident_id}/llm-calls?limit=20`은 인증·Tenant·매장 범위를 검사합니다. limit은 1~100, 타 Tenant Incident는 404입니다. 저장소 오류는 안전한 `LLM_CALLS_UNAVAILABLE`/503과 request_id이며 Mock으로 대체하지 않습니다.

Settings 화면은 추가 Config를 보존·검증하고 허용 Provider/모델 mapping 수/fallback 상태를 표시합니다. Gateway 준비와 Agent 자동 실행 활성화를 구분하고 기존 한국어 layout·Mock/HTTP 경계를 유지합니다.

## 실행/검증

Backend는 기존처럼 `backend/`에서 실행합니다. Windows 출력 인코딩 문제가 있으면 셸의 `PYTHONUTF8=1`을 사용합니다.

```bash
cd backend
uv sync --locked
uv run --locked fastapi run --help
uv run fastapi run --host 127.0.0.1
```

Gateway는 내부 Application 호출 전용입니다. Jev toggle이나 API 시작만으로 외부 호출하지 않습니다. 실제 Gemini 키는 Secret 경계에서 제공하고 VITE 변수·Config history·fixture에 넣지 않습니다. 실제 모델은 별도 명시적 수동 환경에서 검증해야 합니다.

Frontend는 지원 Node 24 버전을 사용합니다. 이번 검증은 Node 24.21.0입니다.

```bash
cd frontend
npm ci
npm run lint
npm run test
npm run build
npm run dev
```

루트의 실제 검증 명령입니다. DB smoke는 별도의 깨끗한 검증 DB와 `SERVIQ_TEST_DATABASE_URL`을 사용하며 사용자 DB/볼륨을 삭제하지 않습니다.

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest
uv run --extra dev python -m scripts.serviq_postgres_smoke
uv run --extra dev python -m scripts.serviq_security_smoke
uv run --extra dev python -m scripts.serviq_queue_smoke
uv run --extra dev python -m scripts.serviq_dashboard_smoke
uv run --extra dev python -m scripts.serviq_settings_smoke
uv run --extra dev python -m scripts.serviq_jev_smoke
uv run --extra dev python -m scripts.serviq_llm_gateway_smoke
uv run --extra dev python -m scripts.serviq_http_smoke
```

HTTP smoke는 별도 Compose 테스트 스택의 `SERVIQ_TEST_API_BASE_URL=http://127.0.0.1:18080/api/v1`을 명시합니다. legacy smoke는 PowerShell의 `scripts/compose_smoke.ps1`을 별도 project에서 실행합니다. 환경 구성은 [배포 문서](serviq_delivery.md)를 따릅니다.

### 실제 검증 결과

- 전체 ruff 통과, 전체 pytest **484 passed**입니다. 기존 테스트 삭제/skip/xfail/약화는 없습니다. Starlette/httpx deprecation warning 한 건은 남아 있습니다.
- backend lock 설치와 `fastapi run --help` 통과입니다.
- frontend npm ci 통과(취약점 0건), lint 통과, **20개 파일 128 passed**, 실제 production build 통과입니다. lock 설치를 위해 이 저장소 Vite만 잠시 중지하고 검증 후 복원했습니다.
- 실제 PostgreSQL·security·Queue·Dashboard·Settings·Jev·LLM Gateway smoke **7종 통과**입니다. 별도 Day 22 DB를 사용하고 사용자 DB를 보존했습니다.
- Gateway smoke는 실제 Config/Incident/UoW/DB 위에 SDK mock repair 2건과 Fake 1건을 저장합니다. 재시작 조회·Tenant/store·PII/응답 원문 미저장·append-only를 확인했고 **실제 외부 모델 호출은 0회**입니다.
- 전용 Compose build/up/migration과 DB·API·nginx·Worker health, 실제 HTTP smoke 통과입니다. 기존 운영 흐름과 LLM 읽기 API·limit·자동 호출 없음을 검증했습니다. Outbox 14건·Job 2건은 COMPLETED, 자동 LLM 기록은 0건입니다.
- legacy Compose smoke의 기존 스키마·pgvector·Python DB 연결도 통과했습니다. 검증 컨테이너는 중지하고 볼륨/검증 DB를 보존했습니다.
- CI PostgreSQL 단계에 외부 AI 없는 Gateway smoke를 추가했습니다. 원격 Actions는 PR에서 별도로 확인하며 로컬 통과를 원격 통과로 표현하지 않습니다.

각 단계에서도 관련 lint/test와 문서를 함께 기록했습니다. 계약 → Fake core → structured → Data Policy → Config Router → Gemini → Ollama/fallback → usage/runtime 조회 → 테스트/CI → 문서의 정확히 10개 경계이며 실제 SHA는 PR과 `git log main..HEAD`에서 확인합니다.

## 제한 사항

### 추가 요청: 프로젝트의 실제 LLM 기본 방향

Day 22 PR 생성 후 사용자 요청에 따라 보강 커밋 1개를 추가합니다. 최초 10개 커밋을 재작성하지 않으므로 이 PR의 최종 커밋 수는 11개입니다.

프로젝트의 실제 LLM 경로는 **필요한 명시적 요청 → 공통 Gateway → Gemini 기본**, Ollama는 정책상 허용한 경우에만 대체 Provider라는 방향입니다. 단순히 키가 존재한다고 모든 화면·Job이 LLM을 호출하지 않습니다. Jev Shadow와 승인 경계는 그대로 유지합니다.

`backend/main.py`가 `backend/.env`를 읽으므로 해당 폴더에서 `uv run fastapi run`으로 시작할 수 있습니다. 이미 지정한 프로세스 환경변수는 덮어쓰지 않습니다. 실제 키는 로컬 `.env`에만 저장하며 Git/예제/Config Version에는 포함하지 않습니다.

```dotenv
GEMINI_API_KEY=로컬에서만_입력
MODEL=gemini-3.5-flash-lite
SERVIQ_LLM_ENABLED=true
GENERATOR_PROVIDER=gateway
RAG_LLM_INPUT_REVIEWED=false
```

`SERVIQ_LLM_ENABLED=true`는 local/development에서만 최초 실행 Config를 만듭니다. FAST/STANDARD/REASONING 요청을 현재 지정 모델로 매핑하지만 모델 자체의 reasoning 품질을 보장하는 의미는 아닙니다. 기본 fallback은 꺼져 있습니다. Tenant Config Version이 이미 있으면 version 0 bootstrap 사용을 거부하며, 저장된 version의 Provider·모델·hosted 정책을 그대로 사용합니다. 운영 환경은 이 로컬 경로 대신 승인된 versioned 설정을 사용해야 합니다.

로컬 예산 예약 단가는 보수적인 입력 10 / 출력 100 USD per million tokens입니다. 공식 청구 단가를 의미하지 않습니다. `LLM_INPUT_USD_PER_MILLION`/`LLM_OUTPUT_USD_PER_MILLION` 또는 Tenant의 검토된 versioned 단가로 조정할 수 있습니다.

기존 RAG `TextGenerator` 계약을 유지하는 `GatewayTextGenerator`를 추가했습니다. `GENERATOR_PROVIDER=gateway`로 선택하며 SDK를 직접 호출하지 않습니다. 자유 텍스트 VOC는 자동 PII 검출이 없으므로 **비식별화·전송 검토가 끝난 입력에 한해서만** `RAG_LLM_INPUT_REVIEWED=true`로 명시해야 합니다. 그렇지 않으면 `POLICY_DENIED`로 전송을 차단합니다. Fake는 테스트/명시적 demo 모드로 보존합니다. 로컬 RAG 경로는 Tenant 영속 audit 없는 standalone CLI 경계이며, 운영 Incident의 호출은 기존 `LLMApplication`과 영속 trace를 사용해야 합니다.

연결 확인에서 지정 Gemini 모델에 공개 테스트 요청 1회를 실제 전송했고 structured 응답 검증에 성공했습니다(입력 23 / 출력 5 tokens, retry 0회). 이는 연결 확인이지 production 품질·자동 Agent 완성을 의미하지 않습니다. 아래 최초 Day 마감의 외부 호출 0회 기록은 당시 CI/Mock 검증 결과입니다.

보강 후에는 `.env` → local Config → HQ_ADMIN/Tenant Application → Router → Gemini → 안전한 usage 기록 경로도 실제 공개 요청으로 확인했습니다(총 25 tokens, fallback 없음). 전체 lint 통과, **491 passed**, backend lock sync·FastAPI CLI·모델 로드 검증 통과입니다. 테스트에서는 외부 모델을 호출하지 않으며 실제 연결 확인은 별도의 수동 요청입니다.

기존 실제 PostgreSQL Gateway smoke도 재실행하여 3개 기록·Tenant 격리·immutable trace 검증이 통과했습니다. Windows `localhost` 연결 지연은 확인된 IPv4 검증 주소 `127.0.0.1`로 동일 테스트를 실행하여 해결했으며 assertion이나 timeout을 완화하지 않았습니다. 프론트엔드/Compose 코드는 이 보강에서 바꾸지 않았고 최종 원격 CI에서 전체 회귀를 다시 확인합니다.

IMPLEMENTED는 Provider 중립 계약, FakeProvider, Gemini SDK/Ollama HTTP 어댑터, schema/업무 검증·한 번 repair, 최소 Data Policy, Config routing, 공유 예산·deadline·제한 retry/fallback, 안전한 영속 usage와 Tenant/store 읽기 API입니다.

다음은 완료로 선언하지 않습니다.

- 실제 Gemini production 품질/요금·모델 capability 실측, 실제 Ollama 모델 서버 실행 검증
- Jev 기반 자동 AI/Agent 실행, LangGraph, History/RCA/CAPA Agent, AgentRun, Multi-Agent
- Harness/MCP, 실제 Connector/external tool, production OIDC/SSO·배포/Production Readiness 전체
- 전체 retention/delete/object storage lifecycle, 자유 텍스트 PII 탐지, provider 법적 계약·region policy 전체
- 분산 concurrency/rate limiter, full circuit breaker, Redis/Kafka, 실제 Worker tenant concurrency
- 외부 AI 호출과 DB 기록의 원자성·정확히 한 번 보장, 미확인 청구량 사후 정산

local/dev Principal은 production authentication이 아닙니다. 금액은 versioned 예상 단가 기반이며 운영자가 검토해야 합니다. 모델 설정을 저장한다는 이유로 Agent Runtime 활성화를 선언하지 않습니다. 기존 RAG 데이터 정책을 이번 Gateway 규칙으로 대규모 재작성하지도 않았습니다.

## 다음 단계

병합 후 최신 main·열린 PR·Drive 버전을 다시 확인합니다. 현재 후보는 Gateway 뒤의 LangGraph single History Investigation Vertical Slice이며 AgentRun/checkpoint·근거 검증·승인 interrupt의 실제 GAP와 운영 안전 계약을 먼저 대조합니다. 이번 Day에는 LangGraph/Agent를 미리 구현하지 않습니다.
