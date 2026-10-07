# Day 28 — Loop와 Harness 안전 실행

## 목적 / 기준

기준 main `f19c46ce3ee35270be037443fdb2f3a6aac17308`(Day 27, PR #55). Issue #56과 `codex/day-28-loop-harness` 하나에서 작업합니다. 최신 Drive `ServIQ_v0.6_AX_AI_Runtime_MVP_통합설계`의 실제 00/09/20/21/25/28/38/39를 확인했습니다. 더 높은 semantic version과 fallback은 없으며 Drive 원문은 수정하지 않았습니다. 오래된 상태표보다 실제 main을 구현 기준으로 사용합니다.

추가 사용자 요청으로 정확히 10개 커밋 제약을 해제하고 기존 커밋을 보존했습니다. 온보딩·데이터 입력은 [첫 사용 가이드](serviq_onboarding_import.md)를 따릅니다.

## Current → Target / 책임

Day 27의 read-only fan-out/fan-in과 append-only branch 기록에 제한 반복, 강제 Harness, 불변 Manifest, 사람 제어를 추가했습니다. Decision / Intelligence / Workflow / Execution / AX를 유지하며 별도 Queue·framework·DI·Agent package를 만들지 않습니다.

`ai/workflow/models.py`, `policy.py`, `controller.py`, `graph.py`, `runtime.py`가 계약·정책·operation 경계·topology·복구를 담당합니다. `ai/execution/harness.py`가 실행 허용을 결정하며 `application/agent_controls.py`가 보호된 사람 명령을 처리합니다. AX와 Frontend는 서버의 업무 상태/권한을 사용합니다.

## Loop Policy / 종료

`loop_enabled` 기본값은 false입니다. 명시적 Multi-Agent 실행만 versioned `bounded-investigation-1` 정책을 pin합니다. 최대 3 iteration, 50 operation, 100,000 token, USD 20, 600초의 system cap 아래에서 현재 설정과 pinned 정책 중 더 작은 한도를 사용합니다. 실제 기본값은 Runtime Config에서 resolve됩니다. Client/Agent는 한도를 올릴 수 없습니다.

기존 `iteration`, `tool_call_count`, `token_spent`, `cost_spent`를 재사용합니다. 현재 `tool_call_count`는 실제 read-only source operation claim 수이며 MCP Tool 호출 수를 꾸며내지 않습니다. RCA가 investigation iteration을 임의로 증가시키지 않습니다.

성공한 branch는 재실행하지 않습니다. 미완료·retryable branch, 필요한 gap, 정책, 남은 예산을 모두 만족해야 제한 재시도합니다. canonical Evidence digest 전후 비교로 새 근거가 없으면 `NO_NEW_EVIDENCE`로 멈춥니다. 종료는 `COMPLETED`, `NO_NEW_EVIDENCE`, `BUDGET_EXHAUSTED`, `ITERATION_LIMIT`, `POLICY_DENIED`, `PAUSED`, `STOPPED`, `MANUAL_TAKEOVER`, `INCOMPLETE`로 표현합니다. 예산 소진/중단이 Incident FAILED/CLOSED를 의미하지 않으며 확보한 근거는 보존합니다.

## Harness

실제 operation 전에 현재 tenant/store/Principal/RBAC, canonical Agent와 operation allowlist, capability/freshness, 현재 config/policy, 서버 risk/approval, budget, replay/claim, control 상태를 검사합니다. Agent 출력의 scope/risk를 신뢰하지 않습니다. Capability 조회가 끝난 현재 시각을 사용해 정상 source가 미래 시각으로 오인되지 않게 합니다.

Harness 허용/거부 이유와 CLAIM/RESULT를 checkpoint와 별개로 기록합니다. 완료 결과는 재사용하고 결과가 불명확한 claim은 임의 재호출하지 않습니다. downstream RCA/CAPA/승인/내부 실행/Verification도 현재 안전 정책을 확인하며 기존 Application/Approval 경계를 대체하지 않습니다. 실제 외부 write와 MCP executor는 없습니다.

## Manifest / Safe Replay

workflow identity/version, config version, 실제 Registry/Context/Loop/Harness version, 선택된 Agent version과 실제 source bundle SHA-256을 시작 시 고정합니다. 존재하지 않는 Prompt/MCP/AI Release version은 만들지 않습니다. API에는 safe version summary만 제공합니다.

같은 Manifest와 bounded reference/branch ledger를 재사용하며 완료 effect를 다시 실행하지 않습니다. resume은 현재 authorization/config/policy/capability/control을 재검증합니다. incompatible Manifest, 위조 상태, tenant mismatch, 결과 불확실성은 fail closed입니다. Safe Replay는 production side effect 재실행 기능이 아닙니다.

## 사람 제어 / Persistence

`POST /api/v1/incidents/{id}/agent-runs/{run}/controls/{pause|resume|stop|takeover}`는 `expected_version`과 `Idempotency-Key`가 필요합니다. RUNNING→PAUSED→RUNNING, RUNNING/PAUSED→STOPPED 또는 MANUAL_TAKEOVER만 허용합니다. Stop/Takeover 이후 자동 재개하지 않습니다. Approval resume와 Agent resume는 다른 명령/Job입니다.

AgentRun row lock과 append-only CONTROL/HARNESS/CLAIM/RESULT event를 사용하고 operation 직전 및 Worker dispatch/resume에서 현재 상태를 확인합니다. 이미 진행 중인 외부 호출을 강제 취소하는 기능은 아니며 새 work 시작을 차단하는 경계입니다. 중단 이후 queued retry가 자동 작업을 다시 시작하지 못하도록 Incident automation latch를 확인합니다.

additive `020_loop_harness.sql`은 tenant/run FK, event unique identity, append-only trigger, immutable Manifest trigger를 추가합니다. 기존 migration은 수정하지 않았습니다. business trace와 LangGraph checkpoint는 분리합니다. `021_data_intake.sql`은 입력 저장소이며 checkpoint/원문 복제 테이블이 아닙니다.

## API / AX / 안전

기존 AgentRun API에 runtime 상태, 종료 이유, 사용 한도, 허용된 제어, 다음 사람 행동을 additive하게 제공합니다. cross-tenant 404, 같은 tenant store/RBAC 403, validation 및 unavailable 오류 계약을 유지합니다. 공개 임의 Agent/Prompt 실행 API는 없습니다.

UI는 “추가 근거를 찾지 못해 중단”, “자동 조사 한도 도달”, “담당자 직접 처리”를 표시하며 버튼은 서버 permission을 따릅니다. 기술 trace는 상세보기로 남깁니다. raw prompt/provider response/checkpoint/delegation/token/credential/idempotency key 원문을 반환하지 않습니다. HTTP 실패를 Mock으로 대체하지 않습니다.

## 검증 / Golden

`test_loop_harness.py`, `serviq_loop_harness_smoke.py`는 정상, 회복 가능한 재시도, no-new-evidence, 예산, pause/resume, stop/takeover race, checkpoint restart, 완료 branch 재사용, 위조 Manifest, 현재 정책 축소, append-only/immutability, tenant/store를 검증합니다. 기존 CAPA/Approval과 Verification 3개 결과 회귀를 유지합니다. 실제 Provider 호출과 external business write는 0입니다.

최종 실행 결과는 [첫 사용 가이드의 Validation](serviq_onboarding_import.md#validation)에 함께 기록합니다. 로컬 검증과 원격 Actions 상태는 PR에서 구분합니다.

## Known Limitations / Not Implemented / Next

제한된 조사 재시도이며 자유형 planner나 범용 Agent loop가 아닙니다. 새 Agent 종류, MCP, LangChain composition, Tool Registry, 실제 POS/ERP/Connector write, 외부 Action reconciliation 전체, Prompt Registry, AI Release/Canary, production OIDC/deployment는 미구현입니다. 기존 실행은 INTERNAL_RECORD_ONLY, Verification은 SIMULATED 경계를 유지합니다. 자동 CLOSED를 만들지 않습니다.

Day 29 Next는 최신 main/Drive 재확인 후 **LangChain Node Runtime + MCP + Tool AX**입니다. Day 30은 AX/AI MVP Release Candidate입니다.

위 제한은 Day 28 마감 시점의 기록입니다. 이후 구현된 좁은 read Tool/Prompt Registry·LangChain composition·private MCP adapter는 [Day 29 문서](serviq_langchain_mcp.md)를 참고하세요. 기존 Loop/Harness가 계속 실행 안전 경계입니다.
