# Day 30 — AX/AI MVP Release Candidate와 Golden Evaluation

## 목적과 기준

Day 30은 새로운 Agent가 아니라 기존 Closed Loop를 사용자의 과업으로 묶는 **AX/AI MVP Release Candidate**입니다. Production Ready가 아닙니다.

- 기준 main: `8af6c8e0dcc6d04781c88b126fdfe68641640c56` (Day 29 PR #59)
- Drive 정본: `ServIQ_v0.6_AX_AI_Runtime_MVP_통합설계`. 최신 semantic version과 실제 문서 20/21/25/26/27/28/38/39를 다시 확인했습니다. fallback 없음, Drive 수정 없음.
- Current → Target: 개별 Runtime/Technical Trace → Incident 단위 AI Brief·업무 Progress·Evidence Coverage·사람 행동·다음 행동·Golden RC 검증.

## 처음 사용하는 방법

1. [첫 사용 가이드](serviq_onboarding_import.md)에 따라 로그인하고 매장 범위를 확인합니다.
2. 샘플 데이터를 추가하거나 Excel Template → 컬럼 매핑 → 검증/미리보기 → 확인 Import를 진행합니다. 샘플은 실제 POS/ERP 데이터가 아닙니다.
3. 시작 체크리스트에서 Incident를 열고 실제 지원되는 조사 시작 동작을 수행합니다.
4. Incident 상세의 AI Brief, 업무 진행, 확보/부족/상충 근거와 다음 행동을 확인합니다.
5. 승인 요청은 기존 Review에서 처리합니다. 승인과 실행은 다릅니다.
6. 재개 후 내부 실행 기록과 Verification 결과를 확인합니다. PASS → RESOLVED, FAIL → REOPENED, INCONCLUSIVE → VERIFYING이며 자동 CLOSED는 없습니다.

실제 서버 연결에는 frontend `VITE_API_MODE=http`를 사용합니다. 기본 Mock 모드는 별도 데모이며 HTTP 실패 시 Mock으로 전환하지 않습니다. 데이터나 권한이 없으면 서버 결과에 따라 빈 상태/차단 사유를 표시합니다.

## Architecture와 AX Projection

Decision / Intelligence / Workflow / Execution / AX의 다섯 책임을 유지합니다. `backend/src/ai/ax/`의 `models.py`, `projector.py`, `actions.py`, `explanations.py`, `service.py`가 기존 Incident/Jev/AgentRun/branch ledger/Evidence/RCA/CAPA/Approval/Execution/Verification/Loop를 읽어 projection합니다. Domain 상태를 변경하거나 Provider를 호출하지 않습니다.

`GET /api/v1/incidents/{incident_id}/ax`는 canonical IncidentAX를 제공합니다. 주요 정보는 AIBrief, current_phase, bounded confidence, EvidenceCoverage, uncertainties, HumanActionRequired, NextBestAction, 업무 Agent Progress, execution/verification, source run/manifest digest, updated_at입니다. confidence는 범주이며 임의 확률을 만들지 않습니다. 없는 데이터와 저장소 장애를 구분합니다. 기존 API는 유지합니다.

Human Action / Next Best Action은 서버 소유입니다. 기존 Review permission·현재 Approval과 Agent control permission을 읽습니다. 승인 대기는 Review, 근거 부족은 추가 근거, 예산 종료는 범위 검토, Stop/Takeover는 수동 처리로 안내합니다. OUTCOME_UNKNOWN은 확인/조정 대상으로 표시하고 자동 재실행 CTA를 제공하지 않습니다. 승인 완료를 실행 완료로 표현하지 않습니다.

설명은 deterministic합니다. Level 1은 업무 Brief, Level 2는 지지/반대/부족 근거·assumption·cannot_verify, Level 3은 기존 Technical Trace입니다. Chain-of-Thought를 생성하거나 저장하지 않습니다.

## UI와 제어권

`frontend/src/features/ai/IncidentAXPanel.tsx`와 `ax.ts`를 기존 Incident 상세에 연결했습니다. Brief → 사람 행동 → 다음 행동 → 업무 Progress/근거/불확실성 → 단계형 설명 순서입니다. 기존 RCA/CAPA/Verification/Trace 화면과 Review를 재사용합니다. loading/partial/empty/error 및 수동 재조회가 있으며 fallback은 없습니다.

기존 RuntimeControls와 Agent Control API를 그대로 사용하여 Pause/Resume/Stop/Manual Takeover를 제공합니다. 서버 permissions와 control version을 사용하며 프론트가 RBAC/업무 상태를 다시 계산하지 않습니다. 완료 Evidence/Manifest는 보존합니다. 새 branch retry subsystem은 추가하지 않았습니다.

## RC Manifest와 Golden 비교

`ai/ax/releases.py`는 기존 AgentRunManifest와 Config/Jev/Prompt/Tool lineage를 재사용하는 per-run candidate snapshot을 제공합니다. 실제 git SHA, workflow/Agent/context/loop/harness/prompt/tool bundle, model routing digest, config, Jev ruleset, Golden scenario version을 묶습니다. candidate는 production active release가 아닙니다.

GoldenComparison은 baseline/reference, candidate, required cases, safety/completion/AX 결과, metric availability와 blocker를 구조화합니다. 필수 case 누락 또는 critical blocker 하나라도 있으면 PASS가 아닙니다. 전역 영속 Release Registry, 전체 baseline 품질 점수 비교, activation/rollback/Shadow/Canary 자동화는 미구현입니다.

## Feedback, Product Event, Metrics

`POST /api/v1/incidents/{incident_id}/ax/events`는 제한된 event_type만 받습니다. Brief/evidence/explanation 조회와 recommendation accept/edit/reject 의견을 기록합니다. 의견은 Approval이나 Domain Command가 아니며 RAW feedback입니다. RAW → REVIEWED → GOLDEN_CANDIDATE → GOLDEN_APPROVED는 계약이며 전체 curation workflow는 구현하지 않았습니다.

additive `022_ax_product_events.sql`은 content-free append-only 이벤트를 저장합니다. tenant/run lineage와 기존 영속 idempotency/UoW를 사용합니다. Audit는 업무 변경 감사이고 ProductEvent는 UX 행동 측정으로 분리합니다. 원본 파일·본문·자유 입력 의견·prompt·PII·Idempotency-Key 원문은 이벤트에 넣지 않습니다.

| 지표 | 실제 기준 / 제한 |
| --- | --- |
| End-to-end completion | 완료 Run에 Verification 결과 존재; PASS만을 의미하지 않음 |
| Time to first useful evidence | Incident 생성 → Evidence reference를 가진 첫 완료 Step |
| Time to decision | Incident 생성 → 실제 Approval 결정 시각 |
| Human intervention | 현재 control/Approval 기록 기반 PARTIAL |
| Manual takeover / Loop abort | 실제 제어·종료 기록 |
| Cost per completed incident | 최신 완료 Run의 estimated cost, PARTIAL; 청구서/전체 이력 비용 아님 |

source timestamp/usage가 없으면 unavailable/partial로 표시하며 0으로 꾸미지 않습니다. 현재 UI의 핵심 이벤트만 계측하며 모든 사용자 행동을 포괄하지 않습니다.

## Security와 Failure/Recovery

Tenant 격리, store/RBAC, 기존 Approval separation, Audit/Idempotency/Outbox/Job, durable checkpoint, Harness, LLM Gateway를 보존합니다. cross-tenant는 404, 동일 Tenant의 store/role 거부는 403입니다. 시스템 장애는 명시적 오류이며 Demo fallback이 없습니다.

AX는 safe reference만 반환하며 raw checkpoint/prompt/provider response/credential/delegation token을 반환하지 않습니다. Feedback에는 실제 RCA와 operate 권한이 필요합니다. Stop/Takeover 및 OUTCOME_UNKNOWN의 기존 effect fence를 유지합니다. 실행은 INTERNAL_RECORD_ONLY, 검증 근거는 SIMULATED이며 현장 개선을 증명하지 않습니다.

## Golden와 검증 결과

`scripts.serviq_ax_rc_smoke`는 실제 PostgreSQL·Job Worker·Day 27~29 Tool/Multi-Agent/Loop/Harness·checkpoint·Approval resume 경로를 사용합니다. 새 PG case는 PASS, FAIL, INCONCLUSIVE, approval reject, branch partial failure, missing evidence의 6개입니다. pause/resume/stop/takeover, loop 종료, tenant/Tool 정책, OUTCOME_UNKNOWN duplicate fence는 기존 smoke와 추가 Golden pytest가 보완합니다. 열 가지를 모두 새로운 PG case로 구현했다고 주장하지 않습니다.

필수 환경은 격리된 `SERVIQ_TEST_DATABASE_URL`과 실제 40자리 `SERVIQ_RC_CODE_SHA`입니다. 비교 결과는 모델과 smoke assertion으로 검증하며 별도 영속 release report 서비스는 없습니다.

- `uv run --extra dev ruff check .`: PASS
- `uv run --extra dev pytest -q`: **793 passed**
- backend `uv sync --locked`, `uv run --locked fastapi run --help`: PASS (Windows help 출력은 UTF-8 환경으로 검증)
- frontend `npm ci`: PASS, audit 0 vulnerabilities
- frontend lint, `npm test -- --run`: **31 files / 198 passed**, HTTP-mode build PASS
- PostgreSQL smoke 14개: postgres/security/queue/dashboard/settings/jev/llm_gateway/langgraph/verification/multi_agent/loop_harness/onboarding_import/tool_runtime/ax_rc 모두 PASS
- 직접 HTTP API + 독립 Worker: 기존 업무/Review/Queue/Settings/Jev/온보딩과 새 AX/events, Verification 3경로 PASS. 로컬 검증은 nginx를 거치지 않았습니다.
- Compose default/profile config: PASS. 로컬 image build/Compose smoke는 디스크 여유 부족과 기존 개발 stack 보존 때문에 실행하지 않았습니다. 원격 CI는 image/Compose/nginx/Worker 검증을 유지하며 최종 결과는 PR Validation/Remote CI에 기록합니다.
- 첫 frontend 전체 실행은 worker startup 및 기존 Settings timeout으로 실패했습니다. 테스트/timeout 변경 없이 새 프로세스로 전체 재실행하여 위 결과를 얻었습니다.
- 첫 PG 시도에서 nonempty DB를 basic smoke에 재사용하여 전용 DB prerequisite 오류가 났습니다. 새 격리 DB에서 전체 14개를 다시 실행해 통과했습니다. 실패를 성공으로 취급하지 않았습니다.
- 실제 Gemini/Ollama 호출 0, external business write 0. 기존 테스트 삭제/skip/xfail/assertion 약화 없음.

## Production NOT READY와 이후 방향

이 결과는 AX/AI MVP RC이며 Production Ready/Complete가 아닙니다. 실제 POS/ERP Connector/write, public production MCP, production OIDC/SSO, 전체 Data Governance, Object Storage, OTel/alerts, IaC/Secrets, backup/restore drill, staging/prod release evidence는 남아 있습니다. generic SQL/shell/HTTP Tool은 없습니다.

후속은 새 Agent 확장이 아니라 synthetic tenant/demo-staging, 실제 사용자 3~5명의 설명 없는 Incident 처리 관찰 → AX friction 측정 → 가장 큰 문제 수정 → Golden/Evaluation → 재검증입니다. 필요한 Connector 1~2개, feedback curation/offline evaluation 및 Release Active/Rollback/Shadow/Canary lifecycle은 별도 Productionization backlog로 관리합니다.
