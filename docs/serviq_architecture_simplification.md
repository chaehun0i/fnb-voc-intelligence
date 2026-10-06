# ServIQ Architecture Simplification

## 목적·기준

기준 main은 `9eacffb`(PR #51 병합)입니다. Issue #52, branch `refactor/architecture-simplification`에서 **구조만** 정리했습니다. 새 Day나 Multi-Agent 기능은 구현하지 않습니다.

Google Drive의 실제 최신 semantic version인 **ServIQ_v0.6_AX_AI_Runtime_MVP_통합설계**를 확인했습니다. Architecture, Harness/Loop, 실행계약, AX 상세 문서를 읽었고 fallback은 사용하지 않았습니다. Drive는 수정하지 않았습니다. 구현 여부는 main, 안전 경계/개념은 v0.6을 기준으로 합니다.

## 개념과 코드

| 문서 개념 | 코드 책임 | 실제 현재 구현 |
| --- | --- | --- |
| Jev | `ai/decision` | 순수 판단·프로필·Shadow 감사/조회 |
| LLM + LangChain | `ai/intelligence` | 기존 Provider-neutral Gateway·정책·routing·usage, LangChain 신규 기능 없음 |
| LangGraph + Multi-Agent + Loop | `ai/workflow` | 기존 단일 History/Evidence/RCA/CAPA Graph·승인 interrupt/resume·Job/Checkpoint |
| Harness + MCP | `ai/execution` | 기존 내부 실행/검증 Command·승인 재검증만 이동, Harness/MCP 미구현 |
| AX | `ai/ax` | 기존 safe AgentRun Trace 투영/조회, 새 AX 정책 없음 |

```text
Incident → Decision → Workflow → Intelligence
                         ↓
                  Execution (현재 내부 실행만)
                         ↓
                  Evidence / Verification
                         ↓
                    Workflow → AX → User
```

이 그림은 책임 위치이지 모든 요청이 LLM/Execution을 호출한다는 의미가 아닙니다. Jev는 deterministic guardrail이며 LLM/Graph를 실행하지 않습니다. Shadow 전체를 자동 실행으로 바꾸지 않습니다. 내부 실행과 SIMULATED Verification을 실제 외부 시스템 변경/현장 효과로 표현하지 않습니다.

## Before / After

기준은 `.py` 소스이며 `__init__.py`를 포함하고 cache/generated 파일을 제외합니다. Before는 Git main tree, After는 최종 source tree입니다.

| 지표 | Before | After |
| --- | ---: | ---: |
| backend source module | 196 | 167 |
| AI module | 46 | 25 |
| backend top-level package | 13 | 11 |
| AI 구현 module (`__init__` 제외) | 42 | 18 |
| AI tiny module (30줄 이하, `__init__` 제외) | 12 | 2 |
| Repository Protocol 파일 | 9 | 1 |

백엔드 모듈은 순감소 29개입니다. AI 구현 파일은 순감소 24개이며 다섯 책임 영역의 독립 진입점/Provider 경계를 위한 `__init__`는 유지합니다. 두 tiny module은 공통 민감 정보 차단 모델과 FakeProvider로, 안전/대체 구현 책임이 있어 남겼습니다. 최대 파일은 `workflow/runtime.py` 569줄이며 계약이나 Provider를 몰아넣지 않았습니다.

기존 조사 계약·Node·approval policy·resume·checkpoint·processor를 찾던 여러 파일이 Workflow의 **models/agents/policy/graph/runtime**로 모였습니다. Jev는 **models/engine/service**, Intelligence는 **models/service/providers**에서 찾습니다. Execution 승인 검증은 Workflow runtime에 의존하지 않도록 분리했습니다. 순환 의존 검사로 이 방향을 고정합니다.

## Dependency / 안전 경계

- Domain과 pure contracts: FastAPI/psycopg/LangGraph/Provider SDK/실행 서비스 import 금지.
- Decision: DB save/Graph invoke/LLM generate/MCP 실행 금지.
- Intelligence: Provider SDK는 adapter 내부에만, Data Policy→routing→budget→retry/structured validation→usage 순서 유지. Incident mutation 없음.
- Workflow Node: repository 구현체·Provider adapter/SDK 직접 import 금지. Port와 Gateway 사용.
- Execution: authorization·Approval digest/expiry/current policy·idempotency·expected version·Audit/Outbox와 Domain invariant 유지. 외부 transport 추가 없음.
- AX: tenant/store/RBAC 조회와 safe DTO만 투영하며 raw checkpoint/prompt/response/delegation metadata를 노출하지 않음.
- API: repository 구현체를 직접 조작하지 않음.

AgentRun/business trace와 Checkpoint는 분리하며 기존 SafeJsonSerializer의 normalized state/reference와 Config snapshot, effect claim/uncertain outcome/dedup semantics를 유지합니다. 불확실한 외부 LLM 결과를 구조 변경 때문에 자동 재호출하지 않습니다. 외부 Action reconciliation 전체는 미구현 상태로 남기며 fail-closed 경계를 약화하지 않습니다.

`test_source_layout.py`는 특정 파일 존재 대신 역할 정의와 import/call direction을 검사하고 역할 검사가 실제 대상을 찾았는지도 확인합니다. 삭제된 옛 package를 검사하던 SDK 테스트도 새 AI 영역을 검사하도록 변경했습니다. AI dependency cycle 회귀와 명시적 Command/keyword UoW 테스트를 추가했습니다. 테스트 삭제/skip/xfail/약화는 없습니다.

## Ports / UoW / Application

`application/ports/repositories.py`에 Incident/Approval/Audit/Idempotency/Job/Config/Decision/LLMCall/AgentRun Protocol과 안정된 오류 계약을 모았습니다. IdentityProvider는 독립 유지합니다. Memory/PostgreSQL substitute와 transaction boundary는 그대로입니다.

AccessUnitOfWork는 keyword-only로 stores를 명시합니다. 새로운 Stores facade나 DI framework는 도입하지 않았습니다. IncidentCommands의 동적 `__getattr__`를 명시적인 public method로 바꿨으며 `_command`와 기존 `_invoke`가 transaction/authorization/idempotency/audit/error mapping을 공유합니다. 요청 canonical fingerprint와 replay semantics는 동일합니다.

## Frontend

Incident/Review/Queue/Settings/Dashboard의 API를 해당 feature의 `api.ts`로 옮겼습니다. AI Trace와 Decision API/decoder는 `features/ai`, 공통 HTTP 설정·인증·키와 Mock은 `shared`에 있습니다. 공유/generated 계약을 feature마다 복제하지 않았습니다. 실제 HTTP 화면, server permission, error/loading/empty, Mock/Real 구분은 동일합니다. Sufficiency/risk/approval/AX를 브라우저에서 새로 계산하지 않습니다.

## Compatibility / Failure

**Runtime behavior 변경 없음. Public API path/response 변경 없음. DB schema/migration 변경 없음. dependency/lockfile 변경 없음.** 내부 Python/TS import만 새 위치로 갱신했으며 compatibility shim/동일 정의 중복/옛 package는 남기지 않았습니다.

검증 도중 발견한 Workflow→Execution→Workflow cycle은 승인 검증의 책임 분리로 수정했습니다. frontend 이동 시 `.` index import 7개가 끊어진 결함은 `./api`로 수정하고 전체 검증을 다시 실행했습니다. 실패를 timeout 증가나 Mock fallback으로 숨기지 않았습니다.

## Validation

검사 명령은 [프로젝트 구조](serviq_structure.md)와 기존 CI를 그대로 사용했습니다. 최종 결과:

| 검증 | 실제 결과 |
| --- | --- |
| `uv run --extra dev ruff check .` | 통과 |
| 전체 `pytest` | **660 passed**, skip/xfail 없음 |
| backend `uv sync --locked`, FastAPI import/CLI help | 통과 |
| 지원 Node의 `npm ci` | 통과, 0 vulnerabilities |
| frontend lint / `npm test -- --run` / build | 통과, **28 files / 173 passed** |
| PostgreSQL / Security / Queue / Dashboard / Settings | 5개 실제 smoke 통과 |
| Jev / LLM Gateway / LangGraph / Verification | 4개 실제 smoke 통과 |
| LangGraph의 Evidence/RCA/CAPA/Approval | 출처·Tenant/store·interrupt·승인/반려·재시작·중복 방지 통과 |
| Golden PG PASS / FAIL / INCONCLUSIVE | RESOLVED / REOPENED / VERIFYING 통과 |
| 실제 nginx/API/Worker HTTP | 기본 운영 회귀·CAPA 승인 resume·Golden 3경로 통과 |
| `scripts/compose_smoke.ps1` | 실제 기존 DB/app·pgvector·health 검증 통과 |
| ServIQ Compose profile | 새 이미지 build·migration·API/nginx/worker health 통과 |
| 네트워크 없는 이미지 검사 | FastAPI/AI/RAG/ingestion import·비특권 nginx 설정 통과 |

PostgreSQL smoke는 9개의 기존 모듈을 모두 유지했습니다. Evidence/RCA/CAPA/Approval 검증은 기존 LangGraph smoke에 포함되므로 새 smoke framework를 만들지 않았습니다. 의도적인 실패 주입의 안전 로그와 기존 Pydantic 경고는 관찰했지만 assertion/timeout을 완화하지 않았습니다. 이 리팩토링 검증의 실제 외부 Provider 호출과 external write는 **0회**입니다.

운영 `fnb_voc`와 `serviq_postgres_data` 볼륨을 보존하고 고정 `serviq` 프로젝트의 별도 검증 DB 하나만 사용했습니다. 검증 후 운영 연결을 복원하며 생성한 검증 DB만 제거합니다. PowerShell의 첫 Golden seed quoting이 빈 fixture를 만들었을 때 이를 Golden 통과로 계산하지 않았습니다. quoting 수정 후 fixture outcome JSON을 확인하고 전용 HTTP 3경로를 모두 재실행했습니다.

GitHub Actions는 push 후 PR check에서 별도로 확인합니다. 위 표는 실제 **로컬** 결과이며 원격 통과를 미리 주장하지 않습니다. 최종 문서 커밋은 docs 전용이고 소스/의존성/DB 변경은 없습니다.

## Known Limitations / Next

LangChain composition, Multi-Agent/fan-out/fan-in, Context Engineering/Registry, full Loop/Harness/MCP, Connector write, 외부 Action reconciliation, 새 AX Brief/Next Best Action, production OIDC/deployment는 이번 작업에 추가하지 않았습니다. 이후 Day 27의 작은 read-only Multi-Agent 확장은 Workflow 내부에, composition은 Intelligence 내부에 넣을 수 있으나 이 PR은 해당 기능을 미리 구현하지 않습니다.

파일을 합쳐 안전 책임을 없애는 것이 아니라 **dependency rule과 Application contract는 유지하고 물리적 구조만 실제 업무 흐름에 맞췄습니다.**
