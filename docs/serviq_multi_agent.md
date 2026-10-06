# Day 27 — Capability-aware 최소 Multi-Agent Investigation

## 목적 / 기준

기준 main은 `b02b0802ca4fd5e4f4cdf24a1eccd71ca444cb9f`(PR #53 Architecture Simplification)입니다. 기능 완료 기준은 Day 26(PR #51)이며 리팩토링을 새 Day로 계산하지 않습니다. Issue #54, `codex/day-27-multi-agent-investigation` 하나에서 작업합니다.

최신 Drive는 `ServIQ_v0.6_AX_AI_Runtime_MVP_통합설계`입니다. 실제 00/07/08/20/21/25/28/38/39를 읽었고 더 높은 semantic version은 확인되지 않았습니다. fallback과 Drive 원문 수정은 없습니다. 오래된 구현현황 snapshot 대신 실제 main을 구현 기준으로 사용합니다.

## Day 26 → Day 27 / 실행 경계

기존 v1~v4 단일 History workflow를 유지합니다. default false인 versioned `multi_agent_enabled`를 켠 **명시적 Application History Job**만 `multi-investigation-v5`를 선택합니다. Jev Shadow를 자동 Agent 실행으로 바꾸거나 공개 Agent/prompt POST를 추가하지 않았습니다.

```text
Incident + Jev + pinned Runtime Config
→ Registry ∩ Jev 후보 ∩ 현재 tenant/store capability ∩ allowed agent/tool
→ 최소 Context Pack
→ HISTORY / TRANSACTION / INVENTORY (최대 3개 독립 read-only branch)
→ branch 기록 → deterministic Evidence fan-in
→ 기존 Sufficiency → RCA → 선택적 CAPA / Human Approval
→ 기존 내부 실행 / Verification
```

Decision / Intelligence / Workflow / Execution / AX의 다섯 책임 영역을 유지합니다. Agent별 package, 별도 Multi-Agent framework, 새 dependency/Queue/DI framework는 추가하지 않습니다.

## Registry / Tenant Capability

`ai/workflow/models.py`의 불변 계약과 `policy.py`의 고정 Registry가 Agent version/purpose/business label/schema/budget/parallel-safe/enabled를 정의합니다. 정적 Registry는 DB/HTTP/SDK에 의존하지 않습니다.

실제 선택은 Jev 후보와 Registry, versioned allowlist, tenant/store의 capability intersection입니다. Capability는 source/health/freshness/확인 시각을 포함합니다. unavailable·stale·미지원·허용되지 않은 Agent는 실행하지 않고 제외 이유를 gap으로 남깁니다. 조직/매장 불일치는 fail closed합니다.

운영 adapter는 `infrastructure/investigation_source.py` 하나입니다. HISTORY capability는 `serviq_history_sources`의 현재 tenant/store 허용 자료 존재 여부에서 확인합니다. 거래·재고는 실제로 저장된 **합성 운영 관측 자료**의 존재 및 24시간 freshness를 확인합니다. DB 연결/조회는 각각 5초 상한입니다. 실제 POS/ERP Connector가 아닙니다.

## Context Engineering

Context는 agent/tenant/incident/store/category/severity/고정 objective/reference-only 정책/time window와 source reference만 담습니다. 원문 Incident JSON, VOC 본문, prompt/credential을 넣지 않습니다. Agent별 source prefix를 제한하고 순서 독립 canonical JSON SHA-256 digest를 검증합니다.

Context는 최대 20 refs, 기본 4,096 bytes 및 실행 token budget 안에서 결정적으로 줄입니다. 최소 metadata조차 담을 수 없으면 거부합니다. unknown/stale/future source 시각을 구분합니다. Runtime 초기 Context는 reference-only 검색 조건이며 검색된 provenance/source 시각은 branch result에 기록됩니다. product/context enrichment와 원문 요약은 구현하지 않았습니다.

## 독립 조사 / fan-out·fan-in

HISTORY는 기존 tenant-safe lexical/hybrid/pgvector 검색 Port를 재사용합니다. TRANSACTION은 refund/cancel, INVENTORY는 shortage/adjustment 관측만 읽습니다. lookup/normalization에는 LLM이 필요 없어 호출하지 않습니다. 생성 문장은 source Evidence가 아닙니다.

기존 `ai/workflow/graph.py`에 LangGraph `Send` branch를 추가하며 max concurrency는 pinned parallelism과 최대 3을 따릅니다. 독립 branch는 stable run/agent UUID identity를 가집니다. 순서와 무관한 reducer와 fan-in이 결과를 정규화합니다. SDK/repository 구현체/실행 transport를 Node에서 직접 import하지 않습니다.

Evidence는 tenant/store/source reference 단위로 dedupe하며 rank/provenance/source timestamp/관측 stance/contributing agent를 보존합니다. 상충 관측은 삭제하지 않고 CONTRADICTING과 원래 stance로 남깁니다. canonical Evidence는 기존 20건 상한을 유지합니다. 서로 다른 source의 같은 실제 사건을 의미적으로 판별하는 Entity Resolution은 미구현입니다.

## 실패 / Sufficiency·RCA

SOURCE_UNAVAILABLE, SOURCE_STALE, BRANCH_FAILED, NO_EVIDENCE_FOUND, BRANCH_BUDGET_EXHAUSTED, CAPABILITY_UNAVAILABLE를 구분합니다. 원본 예외 문자열은 기록하지 않습니다. adapter 장애/timeout/branch runtime 실패는 안전한 gap으로 표현하고 성공 branch Evidence는 유지합니다. tenant/store 위조, Context/결과 corruption, 공통 prerequisite, checkpoint 장애는 전체 실행을 fail closed합니다.

`retryable`은 재시도 가능성 metadata이지 현재 branch 자동 loop 실행을 의미하지 않습니다. 결과를 영속화한 branch는 같은 run에서 변경/재실행하지 않습니다. 새로운 조사 요청이나 후속 제한된 Loop 정책이 필요합니다.

기존 `history-support-v1` Sufficiency/RCA 계약을 재사용합니다. 두 독립 supporting VOC 이력은 **반복 이력 가설**의 기준이며 거래/재고 관측만으로 물리적 원인을 확정하지 않습니다. operational 관측은 보조 근거이고 CONTRADICTING은 기존 CONFLICTING gate에 들어갑니다. 필수 source가 부족하면 INSUFFICIENT로 RCA를 생성하지 않습니다. CAPA/Approval/Execution/Verification 전용 대체 모델은 없습니다.

## 영속화 / 복구 / 안전성

additive `019_multi_agent.sql`은 합성 운영 관측과 append-only `serviq_investigation_branches`를 추가합니다. 기존 001~018은 수정하지 않습니다. branch는 tenant/run 복합 FK와 run/agent unique boundary를 갖습니다. selection/capability snapshot/context digest와 version은 AgentRun state에 pin합니다.

branch 결과는 checkpoint 완료 전에 별도 UoW로 기록합니다. checkpoint 실패 후 동일 run 재시작은 이미 기록된 branch를 재사용하며 조회/외부 호출을 반복하지 않습니다. AgentRun/business trace와 LangGraph checkpoint는 별개입니다. serializer는 검증된 고정 `investigate_branch` Send만 허용하고 임의 class/pickle/tool target을 거부합니다.

resume 시 현재 opt-in/agent/tool/category allowlist와 delegated tenant/store 권한을 다시 검사합니다. LLM이 필요한 downstream은 기존 Gateway/Data Policy를 사용하며 현재 hosted/provider 제한을 우회하지 않습니다. 승인과 실행 직전의 기존 digest/expiry/version/current approval policy 재검증을 유지합니다. 승인 없이 실행하거나 Graph가 Incident 상태를 직접 변경하지 않습니다.

## API / AX

기존 AgentRun list/detail API에 optional `investigation` projection을 추가합니다. 서버가 selected/excluded Agent의 업무 상태, canonical Evidence count/coverage/gap와 불확실성·갱신 시각을 계산합니다. branch 진행 중에도 영속 결과에서 조회합니다. cross-tenant는 404, 매장/권한 부족은 403, bounded query는 기존 계약을 유지합니다.

`frontend/src/features/ai/HistoryTrace.tsx`는 과거 사례/거래 내역/재고 조사 완료·진행·실패·데이터 부족을 보여줍니다. 합성 운영 관측을 실제 POS/ERP로 표현하지 않습니다. 기술 상세는 progressive disclosure이며 기본 업무 상태를 frontend가 재계산하지 않습니다. 기존 loading/empty/error/manual refresh와 HTTP 실패 시 Mock fallback 금지를 유지합니다.

raw Context/checkpoint/prompt/provider response, credential, 권한 위임 정보와 VOC/PII 본문은 API/AX에 노출하지 않습니다. 기존 simulated/internal execution와 RESOLVED≠CLOSED 의미도 유지합니다.

## Golden / 검증

`backend/tests/test_multi_agent.py`와 `scripts.serviq_multi_agent_smoke`가 다음을 검증합니다.

- A: 세 capability가 존재하는 실제 read-only fan-out / fan-in / Sufficiency / RCA.
- B: 재고 source 장애에서도 성공한 이력·거래 Evidence 보존과 gap.
- C: Jev 후보 Inventory라도 실제 capability 없으면 실행 제외, 가짜 Evidence 없음.
- D: checkpoint fault → 새 saver/processor/connection 복구, History 조회 1회, branch append 중복 없음.
- E: tenant/store/위조 결과/digest/Send target 차단, scoped API 404/403, 민감 원문 없음.
- Multi-Agent 결과 → 기존 Approval interrupt → 사람 승인 → 새 Worker/checkpoint resume → 내부 실행 → PASS/FAIL/INCONCLUSIVE.

Golden fixture는 명시적인 canonical GENERAL category/data availability를 실제 Jev pure engine에 입력합니다. 기존 Incident에 정식 category field가 없어 자동 Shadow context가 모든 상황에서 세 후보를 선택한다고 주장하지 않습니다. 기존 category-specific 후보 선택은 그대로입니다.

최종 로컬 검증 결과:

| 검증 | 결과 |
| --- | --- |
| Root `uv run --extra dev ruff check .` | 통과 |
| Root 전체 pytest | **689 passed** |
| Backend `uv sync --locked` / `fastapi run --help` | 통과 |
| Frontend `npm ci` / lint / test / build | 통과, **28 files / 176 passed**, 설치 취약점 0 |
| 실제 PostgreSQL smoke | postgres/security/queue/dashboard/settings/jev/llm_gateway/langgraph/verification/multi_agent 모두 통과 |
| 최종 Compose API 이미지의 PostgreSQL smoke | LangGraph·Evidence/RCA/CAPA·Approval, Verification 3 cases, Multi-Agent 4 cases 및 Closed Loop 3 cases 통과 |
| 기존 `scripts/compose_smoke.ps1` | Python image / PostgreSQL / pgvector / health 통과 |
| ServIQ profile build/up/migration/health | API / nginx / Worker / DB 통과 |
| nginx HTTP 전체 회귀 | Incident / Review / Queue / Dashboard / Settings / Jev / 읽기 전용 LLM·AgentRun 경계 통과 |
| nginx CAPA 및 Golden HTTP | 실제 Review 승인 / persistent resume / PASS→RESOLVED / FAIL→REOPENED / INCONCLUSIVE→VERIFYING 통과 |
| nginx Multi-Agent HTTP | 실제 Worker / 3개 독립 조사 / Evidence fan-in·RCA / 업무 AX 통과 |

장애 주입 로그의 `WORKFLOW_FAILED`는 checkpoint 복구 시나리오에서 의도한 실패이며 재시작·멱등성 assertion까지 통과했습니다. 실패를 skip/xfail/Mock fallback으로 숨기지 않았습니다. 모든 Provider는 Fake/Mock/결정적 경계를 사용하여 실제 Gemini/Ollama 호출과 외부 업무 데이터 변경은 **0회**입니다.

검증에는 개발 `fnb_voc`와 분리한 DB를 사용했습니다. 개발 DB와 `serviq_postgres_data` volume을 보존하며 검증 후 생성한 검증 DB만 제거합니다. 원격 GitHub Actions는 PR에서 별도 확인하며 이 표는 **실제 로컬 실행 결과**입니다.

## Known Limitations / Day 28 Next

정적 Registry와 세 read-only Agent만 지원합니다. 거래/재고는 합성 fixture이며 실제 connector/연속 운영 수집은 없습니다. capability source의 의미/건강은 좁은 DB 존재·freshness 기준입니다. Context에는 제품별 고급 enrichment나 원문이 없습니다. operational 증거만으로 새 RCA taxonomy를 생성하지 않습니다. branch 자동 재시도 loop, 원격 plugin discovery, Agent 자유 대화/자율 planner, 범용 Context framework는 미구현입니다.

Harness/MCP/LangChain 신규 composition, 범용 Loop, 외부 write/reconciliation 전체, production OIDC/SSO/deployment/AI release도 구현하지 않았습니다. 외부 Provider 네트워크 호출 및 external write는 검증에서 0회입니다.

v0.6 MVP 순서에 따라 Day 28은 **최소 Loop/Harness**입니다. Day 29 LangChain/MCP/Tool AX, Day 30 AX/AI MVP Release Candidate는 이번 PR에 포함하지 않습니다. 다음 실행에서도 실제 main/최신 Drive를 다시 확인합니다.
