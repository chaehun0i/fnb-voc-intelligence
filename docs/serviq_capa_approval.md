# Day 25 — CAPA Proposal과 Human Approval Interrupt/Resume

## 목적과 기준

Day 24의 근거 기반 RCA에서 검증 기준을 포함한 CAPA 제안을 만들고, 기존 Incident Application Command와 실제 Approval을 거쳐 사람의 결정까지 durable workflow로 연결합니다. 승인과 실행은 다릅니다. 이번 Day에는 외부 Action을 실행하지 않습니다.

- main: `011cab2f8db40cf0a691b129f6dc6b0337fcb4f0` (PR #47, Day 24).
- 정본: `ServIQ_v0.5_운영안전_실행계약_통합설계`, 실제 문서 확인, fallback 미사용.
- [Issue #48](https://github.com/chaehun0i/fnb-voc-intelligence/issues/48), branch `codex/day-25-capa-approval`.
- Drive 일부 구현현황은 Day 16 스냅샷입니다. 현재 구현은 최신 main과 대조하고 목표 책임/안전 규칙은 Drive 03/07/08/24 등을 사용했습니다. Drive 원문은 수정하지 않았습니다.

## Day 24 → Day 25 / Contract

기존 History/Evidence/Sufficiency/RCA, Tenant-safe 검색, Gateway/Data Policy, Job lease/effect claim/Checkpoint를 재사용합니다. 명시적으로 허가된 Job과 `auto_capa_draft` 설정에만 `history-capa-v3`를 적용합니다. 기존 v1/v2 실행 의미와 Jev Shadow는 보존합니다.

```text
History → Evidence → SUFFICIENT → RCA → CAPA Proposal
→ Application 반영 → Approval Request → interrupt / WAITING_APPROVAL
→ 기존 Review 승인 또는 반려 → persistent resume Job
→ Checkpoint 복원 / 재검증 → READY_TO_EXECUTE 또는 REJECTED → Trace
```

immutable CAPAProposal은 Tenant/store/Incident/run/RCA, 실제 supporting Evidence, Config/Jev 참조, summary/expected effect/필수 verification criteria, risk, action type/target, assumptions/uncertainties, PROPOSED/APPLIED를 표현합니다. 제안은 최대 3개이며 `MANUAL_HISTORY_REVIEW`라는 좁은 내부 검토만 지원합니다. 임의 외부 Tool/target은 생성하지 않습니다.

SUFFICIENT·유효한 RCA·지지 근거가 모두 있어야 제안합니다. INSUFFICIENT/CONFLICTING은 생성하지 않습니다. 현재 CAPA는 결정적 템플릿으로 충분해 별도 LLM을 호출하지 않습니다. 기존 History/RCA의 선택적 LLM은 Gateway/Data Policy를 그대로 사용합니다. 서버가 Incident/Workflow/Proposal risk의 최댓값과 MEDIUM 하한을 적용하여 Agent 출력으로 승인을 우회하지 못하게 합니다.

## Application / CorrectiveAction / Approval Policy

CAPA Node는 Incident를 직접 저장하지 않습니다. CAPACommands가 원래 요청자의 trusted delegation, Tenant/store, 고정 Config/Jev, 실제 저장된 RCA/Evidence, initial expected_version을 검증한 뒤 기존 IncidentService/Domain command를 호출합니다. 조사/근거/RCA를 반영하고 `RCA_READY → ACTION_PROPOSED`로 실제 CorrectiveAction을 저장합니다. AgentRun 결과/Audit/기존 Domain Outbox는 같은 UoW에 있습니다. deterministic ID와 APPLIED 결과 재사용으로 중복을 차단합니다.

기존 ApprovalService/영속 Approval을 재사용합니다. 고정 Config와 현재 Approval policy의 호환성, 실제 action risk, required roles, separation of duties를 검사합니다. workflow 승인은 항상 요구하며 기존 일반 수동 Review 계약은 유지합니다. Agent system actor에 더 넓은 권한을 새로 부여하지 않습니다.

Action digest는 정규화된 조치 내용/type/target/risk/검증 기준으로 계산하며 timestamp/request ID/변하는 승인 상태는 제외합니다. 새 optional 필드가 None인 legacy 조치는 기존 digest와 호환됩니다. Approval은 run/config/policy digest에 연결되며 동일 run의 요청은 중복되지 않습니다.

CRITICAL 2인 승인은 미지원입니다. 필요한 정책을 1인 승인으로 낮추지 않고 `APPROVAL_POLICY_UNSUPPORTED`로 차단합니다. 기존 Review가 지원하지 않는 REQUEST_MORE_EVIDENCE도 가짜 resume 신호로 구현하지 않습니다.

## LangGraph Interrupt / Human Decision / Resume

실제 `interrupt()` 전에 CAPA와 Approval을 idempotent Application 경계에서 저장합니다. AgentRun은 WAITING_APPROVAL이며 실패나 실행 완료가 아닙니다. 원래 History Job은 대기 도달 후 완료되고 사람의 결정이 별도 resume Job을 생성합니다. Worker를 점유한 채 기다리지 않습니다.

Checkpoint에는 normalized state와 Approval/action/digest/config/workflow safe 참조만 있습니다. JSON serializer는 고정된 LangGraph Interrupt 형식만 허용하며 임의 SDK 객체/pickle을 복원하지 않습니다. 새 repository/Saver로 동일 대기를 복원합니다.

기존 Review Command가 auth/Tenant/RBAC/Idempotency를 검사하고 실제 Approval을 결정합니다. 결정/Audit/Outbox/resume Job 생성은 같은 transaction입니다. HTTP 요청자가 arbitrary Graph state를 제출하는 endpoint는 없습니다.

재개 시 실제 Approval의 Tenant/run/action identity, digest, Incident 상태/버전, 만료, 현재 policy 호환성을 다시 검사합니다. APPROVE는 READY_TO_EXECUTE, REJECT는 REJECTED입니다. 승인 후 CorrectiveAction은 APPROVED이지 EXECUTED가 아닙니다. Incident를 자동 실행/종결하지 않습니다. 동일 결정 replay와 resume Job 재전달은 새 run/Approval/조치를 만들지 않습니다.

## Persistence / Migration

기존 AgentRun/append-only Step JSON과 Tenant/run FK를 유지합니다. additive `015_workflow_approval.sql`은 Approval/run lineage·중복 방지를, `016_approval_steps.sql`은 Step 1..11을 추가합니다. 기존 migration 원문은 수정하지 않았습니다.

과거 SQL을 매번 실행하면 옛 Step 상한이 새 이력에 재적용되어 재시작에 실패했습니다. 적용 ledger/checksum 및 transaction advisory lock으로 적용한 migration은 재실행하지 않습니다. legacy DB는 Day 24 runner가 001..014를 원자적으로 완료했다는 전제에서 마지막 RCA effects 테이블을 확인해 기준선을 채택하고 015부터 적용합니다. 임의 부분 수동 적용 DB의 복구 도구는 아닙니다. 실제 Step 9 이후 migration 재실행/재시작을 검증했습니다.

## API / AgentRun Trace / Review UI

기존 list/detail을 additive하게 확장합니다.

- `GET /api/v1/incidents/{id}/agent-runs`
- `GET /api/v1/incidents/{id}/agent-runs/{run_id}`

CAPA/RCA/Evidence, risk/verification, Approval/digest/config, waiting/resume 시각, safe actor와 결정 reason code, branch/correlation을 제공합니다. raw checkpoint/권한 위임 내부 정보/idempotency key는 반환하지 않습니다. Approval 결정은 Worker 재개 전에도 조회하되 durable run phase와 구분합니다.

한국어 실제 Trace에서 제안/근거/검증 기준/승인 대기를 보여주고 기존 Review로 연결합니다. 서버 permission을 사용하며 승인 후 “승인 완료 — 실행 단계 대기”, 반려는 “조치안 반려”로 표시합니다. loading/empty/error/manual refresh를 유지하고 HTTP 실패에 Mock을 섞지 않습니다. 새 Approval 화면이나 arbitrary Agent 실행 POST는 없습니다.

## Failure / Security / Data Governance

Cross-Tenant는 기존 404, 같은 Tenant의 store/역할 부족은 403, stale version/digest/policy는 conflict 경계를 사용합니다. replay 전에도 권한을 확인합니다. 현재 policy가 바뀌면 예전 snapshot만 믿고 재개하지 않습니다. 관련 없는 budget 변경은 기존 run config를 바꾸지 않습니다.

Checkpoint 실패 뒤 저장된 APPLIED CAPA/Approval을 재사용합니다. 불확실한 기존 History/RCA 외부 효과는 자동 재호출하지 않는 fail-closed 경계를 유지합니다. Workflow 장애가 Incident를 FAILED로 오염시키지는 않지만 이미 성공한 업무 Command를 무조건 되돌린다고 주장하지 않습니다. 정책 차단 등으로 ACTION_PROPOSED에 남으면 운영 복구가 필요할 수 있습니다.

raw VOC/prompt/Provider response/credential/secret/불필요 PII를 새 Trace/Checkpoint/API에 저장하지 않습니다. trusted delegation은 요청 시 권한 snapshot이며 production IdP 권한 철회 재조회까지 구현한 것은 아닙니다. 기존 Tenant/store/RBAC/Audit/Idempotency/Gateway 정책은 우회하지 않습니다.

## Validation

| 실제 로컬 검증 | 결과 |
| --- | --- |
| root ruff / 전체 pytest | 통과 / 599 passed, skip·xfail 우회 없음 |
| backend uv sync --locked / FastAPI run --help | 통과, Windows 출력은 PYTHONUTF8=1로 검증 |
| frontend npm ci / lint | 통과, Node 24.19.0, audit 0 vulnerabilities |
| frontend 전체 test / build | 26 files / 163 passed, 빌드 통과 |
| PostgreSQL/security/queue/dashboard/settings/Jev/LLM Gateway smoke | 각각 격리 DB에서 API 이미지로 통과 |
| 확장 LangGraph smoke | 기존 History/RCA, CAPA/Approval/interrupt, 대기 중 재시작, 승인·반려 resume, 중복 방지, migration 반복, Tenant/store 격리 통과 |
| compose_smoke.ps1 / ServIQ build·up·health | pgvector/CLI 연결과 API/frontend/Worker 기동 통과 |
| HTTP/nginx smoke | 기존 API 전체 회귀 및 CAPA→Review 승인→persistent resume Job→Worker checkpoint 재개 통과 |

개발 DB와 분리한 검증 DB를 사용했습니다. 초기 호스트 smoke는 남은 검증 데이터와 Compose DB 재시작으로 중단되어 성공으로 기록하지 않았으며, 별도 DB를 이용한 API 이미지의 전체 smoke로 다시 검증했습니다. 실제 Gemini/Ollama 호출은 0회입니다. CI에 동일 CAPA PostgreSQL/nginx 경로를 추가했고 원격 상태는 PR에서 로컬 결과와 구분합니다.

## Known Limitations / Not Implemented / Next

CAPA는 반복 이력의 추가 검토라는 좁은 제안이며 범용 조치 품질 검증이 아닙니다. CRITICAL 다중 승인, 추가 근거 요청/revision loop, 실패 수동 복구 UI, production 권한 철회 연동은 미완료입니다.

실제 외부 Action/Connector write, Verification, 자동 Resolve, Multi-Agent, Harness, MCP, production OIDC/SSO/deployment는 구현하지 않았습니다. Approval 완료는 Action 실행 완료가 아닙니다.

Day 26 후보는 **안전한 실행 기록/시뮬레이션 + Verification + Incident Golden Workflow E2E**입니다. 최신 main/설계를 다시 확인하며 Day 27 최소 fan-out, Day 28 최소 Harness/MCP, Day 29 Evaluation/Hardening, Day 30 MVP Release Candidate 경로를 유지합니다.
