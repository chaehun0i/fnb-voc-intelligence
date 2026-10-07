# Day 29 — LangChain Node Runtime + MCP + Tool AX

## 목적과 기준

Day 28의 Loop/Harness·Manifest·사람 제어와 온보딩을 유지하면서, Node 안의 composition과 좁은 read-only Business Tool을 연결합니다. Agent가 자유롭게 Tool을 계획하거나 외부 시스템을 변경하는 기능이 아닙니다.

- 기준 main: `23165a331f1d89b94cb1d56806430e7d553539de` (PR #57, Day 28)
- 설계 정본: `ServIQ_v0.6_AX_AI_Runtime_MVP_통합설계`
- Drive 루트와 실제 10/20/38/39 및 Data Governance 문서 재확인, 더 높은 버전 없음, fallback 없음
- Issue: [#58](https://github.com/chaehun0i/fnb-voc-intelligence/issues/58)
- Drive 원문 변경 없음. Day 30 RC/AI Release 기능은 구현하지 않음

Current → Target: 기존 직접 observation 조회를 없애지 않고, **새 Multi-Agent + Loop Run의 거래/재고 branch**를 canonical Tool → Harness → Application Query 경계로 실행합니다. 기존 Run의 Manifest를 새 계약으로 덮어쓰지 않습니다.

## 책임과 실제 경로

```text
Decision/Jev → Workflow/LangGraph → Agent Registry/Capability/Context
  → Intelligence/LangChain Node composition + Prompt Registry
  → MCP 공식 in-memory Client/Server adapter
  → Execution/Tool Registry + Harness
  → Application Query → 기존 Repository/source port
  → canonical reference result → Evidence/fan-in/Sufficiency/RCA
  → 기존 CAPA/Approval/내부 실행/Verification → AX
```

MCP는 protocol adapter이고 안전 경계는 Harness입니다. 서버를 직접 호출해도 같은 Harness를 통과합니다. Registry resolve/schema validation은 adapter와 Harness 양쪽에서 수행합니다.

| 책임 | 구현 위치 | 하지 않는 일 |
|---|---|---|
| Workflow | `ai/workflow/{agents,runtime,graph,policy,models}.py` | Provider SDK·DB 구현체 직접 호출, Domain 임의 전이 |
| Intelligence | `ai/intelligence/{node,prompts,service}.py` | Gateway 우회, 전체 workflow/checkpoint/권한 관리 |
| Execution | `ai/execution/{tools,runtime,harness}.py` | 임의 shell/SQL/HTTP, 실제 외부 write |
| Application | `application/tool_queries.py` | MCP decorator에 업무 규칙 복제 |
| MCP adapter | `mcp/server.py` | 인증 source of truth, public anonymous HTTP listener |
| AX/API/UI | `ai/ax/service.py`, `api/schemas/agent_runs.py`, `features/ai` | frontend가 Tool 결과로 risk/승인/업무 상태 재계산 |

LangGraph의 topology·fan-out/fan-in·checkpoint·interrupt/resume와 Domain State Machine은 그대로입니다. History branch는 기존 검색을 유지합니다. 거래/재고는 deterministic read이므로 LLM을 호출하지 않습니다. 새 경로의 RCA가 LLM을 필요로 할 때만 등록 Prompt의 reference fact composition을 **기존 LLM Gateway**로 전달합니다. Gateway의 Data Policy·routing·schema/repair·budget·usage·fallback이 계속 source of truth입니다.

## Tool Registry와 Application Query

`ai/execution/tools.py`의 frozen 계약과 immutable Registry bundle `read-tools-1`을 사용합니다. Tool version은 모두 `1`이며 중복 등록·unknown/version mismatch·schema drift는 거부합니다.

| Tool | Agent/capability | 실제 의미 |
|---|---|---|
| `get_incident` | HISTORY / HISTORY_DATA | 현재 허용 Incident의 안전한 참조·시각 |
| `search_similar_incidents` | HISTORY / HISTORY_DATA | 같은 허용 매장·severity의 다른 Incident 참조 |
| `get_transactions` | TRANSACTION / TRANSACTION_DATA | 해당 매장/관측 기간의 기존 거래 observation |
| `get_inventory` | INVENTORY / INVENTORY_DATA | 해당 매장/관측 기간의 기존 재고 observation |

유사 Incident 조회는 현재 **같은 매장·severity heuristic**입니다. semantic RAG 검색으로 표현하지 않습니다. 4개 Tool 모두 등록/프로토콜/권한 테스트가 있으며, 실제 Multi-Agent 전환은 거래/재고 2개 Tool부터 적용합니다.

계약은 input/output schema, LOW/read-only risk, current Incident/store scope, side effect NONE, timeout 10초, bounded Loop retry, pinned read-result idempotency, read-only approval policy, evidence semantics, when-to-use/not-use, preconditions/common-errors/retry-guidance를 포함합니다. MCP description/AX metadata도 같은 계약을 읽습니다.

입력은 `incident_id`, `limit`(1~20)뿐입니다. 출력은 최대 20개의 검증된 source reference/type/time/rank/provenance/observation code/stance입니다. raw VOC·이름·전화번호·원본 문서·생성된 요약을 source로 넣지 않습니다. 거래/재고의 `synthetic_operational`과 `file_imported_operational` 출처를 구분하며 **POS/ERP 원장/Connector로 표현하지 않습니다**.

## ExecutionContext와 Harness

Tool argument나 MCP metadata로 tenant/actor/store/scope/approval을 받을 수 없습니다. `ToolHarness`는 tenant-scoped run lock 아래 immutable delegation, 현재 Incident, Context Pack, Config, Capability를 읽어 `ToolExecutionContext`를 만듭니다. context에는 tenant/principal/run/correlation/config/store/tool version/manifest digest만 있습니다.

Registry → 현재 Tenant/store/RBAC → Manifest/config compatibility → Agent/operation allowlist → 현재 Capability → risk/approval 정책 → control state → 남은 예산 → receipt/replay 확인 → Application Query 순서로 기존 Day 28 Harness를 재사용합니다. Application Query도 기존 Principal/Incident access 경계를 적용하며 source의 tenant/store/window를 검사합니다.

바깥 Loop claim이 이미 예약한 operation은 Tool에서 두 번 차감하지 않습니다. 예약당 다른 Tool/입력 추가 호출은 거부합니다. 직접 호출은 실제 operation 한 번을 소비합니다. tool count를 올리지 않고 호출하거나 완료 Run에서 새 호출을 시작하는 경로를 허용하지 않습니다. cached 결과라도 현재 authorization/capability/control을 먼저 재검사합니다. Stop/Takeover/Pause에서 cached read로 우회하지 못합니다.

## Prompt Registry / Manifest

`ai/intelligence/prompts.py`는 정적 versioned Registry입니다. 운영 DB Prompt 편집 UI는 없습니다.

| Prompt ID | version | input / output |
|---|---|---|
| `observation-lookup` | 1 | reference-only-1 / investigation-1 |
| `history-grounded-rca` | 1 | reference-only-1 / rca-history-1 |
| `reference-summary` | 1 | reference-only-1 / history-1 (helper 계약 테스트) |

id/version/task/template/input/output/status/change reason의 canonical digest를 계산합니다. unknown/inactive Prompt와 task/schema mismatch는 fail closed입니다. Prompt 본문은 Trace/API에 노출하지 않습니다. 등록한 모든 Prompt를 모든 Agent가 실행했다고 주장하지 않습니다.

새 경로의 Manifest는 기존 workflow/config/agent/context/loop/harness/build reference에 Tool bundle/version 및 Prompt id/version/digest를 더해 pin합니다. resume/replay에서 재계산한 계약과 다르면 fail closed입니다. 실제 존재하는 계약만 기록하며 미래 Tool/AI Release version placeholder는 없습니다. 기존 `tool_runtime_enabled=false` Run은 기존 의미를 유지합니다.

## LangChain과 공식 MCP SDK

루트 `pyproject.toml`, 루트/backend `uv.lock`에 최소 dependency를 고정했습니다. 설치 검증 버전은 `langchain-core 1.6.7`, 공식 `mcp 2.3.0`입니다. Provider integration package를 추가하지 않았습니다.

LangChain은 `ChatPromptTemplate`, `RunnableLambda`/typed tool binding만 사용합니다. binding 자체는 authorization이 아닙니다. 고정 Prompt와 검증된 reference/fact code만 composition하며 raw spreadsheet/VOC를 전송하지 않습니다. implicit LangSmith export는 비활성화합니다.

설치 SDK public API `from mcp.server import MCPServer`, `from mcp import Client`로 구현했습니다. `Client(server_instance)` in-memory transport로 list-tools/call-tool 계약을 실제 검증합니다. protocol input/schema → bound server session → Harness → canonical result/safe error만 담당합니다. 새 public HTTP route, stdio shell entrypoint, 임의 network destination은 없습니다.

공식 참고: [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), [SDK 변경 사항](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md), [LangChain ChatPromptTemplate](https://reference.langchain.com/python/langchain-core/prompts/chat/ChatPromptTemplate), [Runnable](https://reference.langchain.com/python/langchain-core/runnables/base).

## Persistence / failure / recovery

Day 29 DB migration/schema 변경은 없습니다. 최신 applied migration은 `021_data_intake.sql`입니다. 기존 AgentRun document에 reference-only `ToolCall` receipt를 저장합니다. business trace와 LangGraph checkpoint는 분리합니다.

실행 전 pending receipt를 run lock으로 기록하고, 실행 후 canonical result 또는 safe error로 한 번만 완료합니다. Repository validation은 receipt 삭제/identity 변경/완료 결과 변경을 거부합니다. 다른 branch가 저장한 state를 현재 row에서 merge하여 보존합니다. 이는 Application/Repository 무결성 검사이며 별도 SQL Tool receipt trigger를 추가한 것은 아닙니다.

동일 context/manifest/reservation/argument의 완료 결과는 재사용합니다. claim 뒤 결과가 불확실한 경우 `OUTCOME_UNKNOWN`이며 자동 재실행하지 않습니다. 임의 exception의 vendor 메시지/stack/SQL/credential은 protocol로 나가지 않습니다. 기존 branch/effect ledger와 checkpoint recovery를 유지합니다.

ToolError는 code/category/retryable/safe_message/suggested_action/human_action/details_ref를 갖고 안전한 서버 정의 문구만 허용합니다. temporary source failure는 기존 bounded Loop retry 후보이며 무한 retry가 아닙니다. permanent/NO_DATA는 Evidence Gap, authorization은 fail closed, policy/budget/control은 기존 termination 경계로 전달합니다. 성공 branch의 Evidence는 보존합니다. timeout으로 취소된 read의 완료 여부가 불확실하면 pending receipt가 재실행을 차단합니다.

## Tool AX / Data Governance

기존 AgentRun detail에 additive `tools` projection을 제공합니다. Tool name/version/status, 서버가 계산한 업무 문구, 근거 개수, safe error/human action만 공개합니다. 예: “거래 자료 확인 완료”, “재고 자료 확인 완료”, “필요한 데이터 없음”. 기본 UI는 업무 문구를 사용하고 Tool/version은 technical details 안에 둡니다.

raw receipt/ExecutionContext/context digest/checkpoint/prompt/provider response/delegation token/idempotency key는 공개하지 않습니다. 기존 cross-tenant 404, same-tenant store/RBAC 403 의미와 서버 permission을 유지합니다. API path 변경이나 arbitrary execution POST는 없습니다. frontend HTTP 오류를 Mock으로 대체하지 않습니다.

기존 Evidence/Sufficiency/RCA/CAPA/Approval/내부 실행/Verification 계약을 그대로 사용합니다. 승인 ≠ 외부 실행이며 내부 실행은 INTERNAL_RECORD_ONLY, Verification source는 SIMULATED입니다. Tool read 성공이 현장 개선이나 Verification PASS를 의미하지 않습니다.

## Validation

검증 명령은 기존 CI 구조를 유지합니다.

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest
# backend/
uv sync --locked
uv run --locked fastapi run --help
# frontend/
npm ci
npm run lint
npm test
npm run build
# repository root, 격리된 SERVIQ_TEST_DATABASE_URL
uv run --extra dev python -m scripts.serviq_tool_runtime_smoke
```

- Tool Registry/schema/AX, 4개 read Tool, scope/forgery/current capability/budget/control, immutable/pending receipt, official MCP Client/schema drift, safe exception, Prompt pin, Fake Gateway structured output, 실제 Graph/RCA와 Import provenance 회귀를 검증합니다.
- 새 PostgreSQL smoke: normal / partial / capability filter / checkpoint restart, 완료 branch/receipt 재사용과 Tool source lineage를 검증합니다.
- 격리 DB에서 기존 postgres/security/queue/dashboard/settings/jev/llm_gateway/langgraph/verification/multi_agent/loop_harness/onboarding_import 및 새 tool_runtime **13개 smoke 통과**. 개발 `fnb_voc` DB/volume은 삭제하지 않았습니다.
- Python lint 통과, 전체 pytest **752 passed**. frontend `npm ci`/lint/test/build 통과, **30 files / 190 passed**. backend locked install/import/FastAPI help 통과. Windows help 출력은 UTF-8 환경에서 검증했습니다. 원격 CI 결과는 PR Validation에 별도로 기록합니다.
- 로컬 새 이미지/Compose/HTTP 검증은 C: 여유 약 0.9GB로 보류했습니다. 기존 개발 스택의 정상 상태를 새 코드 이미지 검증으로 간주하지 않습니다. 원격 CI의 실제 image/Compose/nginx/Worker 검증과 로컬 결과를 구분합니다.
- CI PostgreSQL job 및 Compose API-image 검증에 새 Tool smoke를 추가했습니다. 실제 Gemini/Ollama 호출 0회, 외부 business write 0회입니다. 테스트 삭제/skip/xfail/assertion 완화로 실패를 숨기지 않습니다.

## Known Limitations / Not Implemented / Next

- 정적 Prompt/Tool Registry이며 동적 plugin/원격 Registry/Prompt 관리 UI는 없습니다.
- 기존 모든 Agent Node를 LangChain으로 migration하지 않았습니다. History 검색은 기존 경로입니다.
- 유사 Incident Tool은 bounded heuristic reference lookup이며 semantic retrieval을 대체하지 않습니다.
- 거래/재고는 합성 또는 확인 Import observation입니다. 실제 POS/ERP Connector나 external write MCP Tool은 없습니다.
- MCP는 Workflow가 소유하는 private in-memory read adapter입니다. production public endpoint/auth deployment가 아닙니다.
- arbitrary SQL/shell/HTTP/filesystem Tool, production OIDC/SSO/deployment, AI Release/Shadow/Canary/Feedback pipeline은 없습니다.
- Manifest/source compatibility는 엄격하며 호환되지 않는 build에서 기존 Run을 자동 업그레이드하지 않습니다.
- 다음은 최신 main/Drive 재확인 후 **Day 30 AX/AI MVP Release Candidate**입니다. 이번 Day에 RC나 production-ready를 선언하지 않습니다.
