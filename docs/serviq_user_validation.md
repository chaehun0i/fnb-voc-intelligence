# Day 31 — User Validation Readiness + AX Friction Evaluation

## 목적과 기준

**실제 사용자 검증을 수행하고 AX friction을 측정할 수 있는 기반**을 제공합니다. 사용자 검증 자체가 완료된 것은 아닙니다. Day 30의 AX/AI MVP Release Candidate를 유지하며 Production Ready를 선언하지 않습니다.

- 기준 main: `096f7e305c8031c67d8131ed0f36100d52c423a6` (Day 30 PR #61, Issue #60 completed).
- Drive 정본: `ServIQ_v0.6_AX_AI_Runtime_MVP_통합설계`. 프로젝트 루트의 semantic version과 실제 문서 20/21/25/38/39를 재확인했습니다. 상위 버전 없음, fallback 없음, Drive 수정 없음.
- Drive의 과거 Day 25 구현 snapshot보다 GitHub 실제 구현 상태를 우선합니다.
- Current → Target: 개별 AX/Runtime 결과 → 사용자 업무 과업·관측 Journey·마찰 신호·RAW 의견·실측 지표.
- 이후 순서: 사용자 과업 → 관찰 → friction 측정 → 가장 큰 문제 수정 → Golden 재검증. 새 Agent/Provider/framework를 추가하지 않습니다.

## 처음 관찰을 시작하는 방법

1. 기존 [첫 사용 가이드](serviq_onboarding_import.md)로 API/frontend/Worker/PostgreSQL을 준비합니다. HTTP 모드에서 실제 권한과 매장을 확인하세요. 현재 로컬 호환 인증은 production OIDC가 아닙니다.
2. 매장을 먼저 등록/확인합니다. **사용자 과업 검증 참여**에서 매장과 관찰 과업을 선택하고 제한된 행동 수집에 동의합니다. 참여하지 않으면 기존 운영 흐름을 그대로 사용합니다.
3. 샘플 또는 Excel Template → 컬럼 확인 → 검증/미리보기 → 확인 Import로 데이터를 준비합니다. 샘플은 실제 POS/ERP 데이터가 아닙니다.
4. 기존 Incident를 열어 조사를 실행하고 AI Brief·근거·불확실성·사람 행동·다음 행동을 스스로 검토합니다. 안내는 업무 목표만 제시하며 정답이나 클릭 순서를 계속 알려주는 Tour가 아닙니다.
5. 필요한 업무 명령은 기존 Review/Agent Control에서 처리합니다. 승인 분리 정책을 지키며 별도 검토자가 필요한 경우 실제 Reviewer가 결정합니다.
6. 실제 제공되는 Verification과 최종 상태를 확인하고 선택형 의견을 남긴 뒤 **과업 완료 확인**을 누릅니다. 서버가 실제 조건을 확인합니다. 부족한 조건은 409이며 클릭만으로 완료하지 않습니다.
7. 막히면 **다음 행동이 불명확함**, 그만두면 **과업 중단**을 사용합니다. 기존 Evidence/Incident/Trace를 삭제하지 않습니다.
8. 관리자는 Dashboard의 **사용자 검증 지표 조회**에서 허용된 매장과 **사용자 참여 관찰 / Synthetic 검증**을 별도로 조회합니다.

새로고침 시 sessionStorage에는 Session UUID locator만 보관합니다. 완료 여부·데이터 존재 여부·권한은 서버에서 다시 읽습니다. HTTP 오류를 Mock으로 바꾸지 않습니다. 다른 계정의 Session은 이어받을 수 없습니다.

## 계약과 책임

Decision / Intelligence / Workflow / Execution / AX 책임을 유지합니다. `ai/ax/validation.py`는 순수 계약/Journey, 기존 `ai/ax/measurement.py`는 지표, `application/user_validation.py`는 권한·멱등성·canonical source 연결, `api/routes/user_validation.py`는 HTTP 경계입니다. 별도 Analytics framework나 Incident 상태 머신을 만들지 않습니다.

ValidationTask `incident-understanding@1`의 목표는 “이 사건의 가장 가능성 높은 원인과 다음 조치를 판단하고 최종 상태를 확인”하는 것입니다. 성공 기준은 근거 검토·실제 필요한 판단·검증/최종 상태 확인·의견입니다. Scenario별 terminal은 RESOLVED, REOPENED, MORE_EVIDENCE_REQUIRED, MANUAL_TAKEOVER, ABANDONED입니다. 이는 업무 과업 기준이며 새 Domain status가 아닙니다.

ValidationSession에는 session/tenant/store/scenario, server-generated opaque participant UUID, task version, entry point, incident/run 참조, status, 동의 범위, timezone-aware timestamp가 있습니다. ACTIVE / COMPLETED / ABANDONED와 서버 완료 시점의 실제 Incident phase를 보존합니다. participant UUID는 Session마다 발급되므로 Session N은 고유 인간 참가자 수가 아닙니다. 이름·이메일을 받지 않습니다. `release_candidate_id`는 선택 계약이며 전역 Release Registry를 꾸며 채우지 않습니다. 실제 이벤트에는 run Manifest digest를 연결합니다.

Audit ≠ ProductEvent, AgentRun Trace ≠ User Journey, Feedback ≠ Golden 정답, Synthetic ≠ Real User, Page View ≠ Task Success, AI Output ≠ Verified Evidence, unavailable ≠ 0입니다.

## Journey와 실제 업무 상태

Milestone은 ONBOARDING_STARTED, DATA_READY, INCIDENT_OPENED, AI_BRIEF_VIEWED, EVIDENCE_REVIEWED, HUMAN_ACTION_PRESENTED, REVIEW_OPENED, DECISION_SUBMITTED, VERIFICATION_VIEWED, FINAL_STATUS_VIEWED, FEEDBACK_SUBMITTED입니다.

- 조회/열람은 제한된 관찰 신호일 뿐 이해도를 증명하지 않습니다. Evidence/Brief/Review/Verification은 실제 해당 자료가 존재해야 기록됩니다.
- DATA_READY는 해당 매장의 실제 Import/Incident와 연결합니다.
- DECISION_SUBMITTED는 클릭 이벤트가 아니라 고정된 Run에 대한 실제 Approval 결정 시각입니다. 별도 Reviewer의 업무 결정도 포함하며 참가자 본인이 승인했다고 주장하지 않습니다.
- Happy/Reopen 완료는 실제 PASS→RESOLVED 또는 FAIL→REOPENED와 Brief/근거/결정/검증/최종 상태/RAW 의견 관찰을 요구합니다.
- More Evidence는 실제 AX의 MORE_EVIDENCE_REQUIRED와 해당 의견, Takeover는 실제 Runtime 제어 상태를 요구합니다.
- INCONCLUSIVE→VERIFYING 의미는 그대로 유지하지만 Happy 과업 완료로 계산하지 않습니다. Abandon은 성공이 아닙니다.
- 중복/순서가 바뀐 이벤트는 milestone별 최초 시각으로 projection합니다. 실제 완료 receipt는 이후 Incident 변경으로 취소하지 않습니다. 다른 Run이 최신이 되면 과거 관찰을 그 Run에 잘못 귀속하지 않습니다.

서버 상태를 결합해도 사용자가 정말 내용을 이해했는지는 자동 증명할 수 없습니다. 실제 관찰·질문과 함께 해석해야 합니다.

## Friction, Feedback와 Privacy

기존 append-only ProductEvent를 확장합니다. bounded taxonomy는 BACKTRACK, REPEATED_ACTION, HELP_OPENED, EXPLANATION_EXPANDED, MANUAL_TAKEOVER, ACTION_REJECTED, REQUEST_MORE_EVIDENCE, TASK_ABANDONED, ERROR_RECOVERED, NO_CLEAR_NEXT_ACTION입니다. 현재 UI의 설명 펼침·불명확함·의견·중단을 연결하며 모든 가능한 행동을 자동 계측했다고 주장하지 않습니다. 설명/도움말은 탐색 신호이지 그 자체로 실패가 아닙니다.

Payload는 Session/task/incident/run, 제한된 surface/milestone/reason code, 서버 timestamp와 Manifest digest뿐입니다. POST body는 stream 기준 4 KiB, Session 이벤트는 500개 상한입니다. 자유 입력·raw VOC/prompt/provider response/checkpoint/credential/token/Idempotency-Key 원문을 저장하지 않습니다. 추가 필드·위조 Session 종류/Run/actor/scope·큰 payload는 거부합니다. 예외 응답에 원문 입력을 반사하지 않습니다.

Feedback decision은 ACCEPT / EDIT / REJECT / REQUEST_MORE_EVIDENCE / MANUAL_TAKEOVER입니다. 현재 AX 권한/상태를 확인하며 RCA/CAPA artifact ID는 서버가 실제 Run 결과에서 선택합니다. `session_id → task_id → incident_id → agent_run_id → run_manifest_ref → artifact_type/id` lineage를 기록합니다. Opinion은 실제 Approval/수정 Command가 아닙니다. **RAW만 저장**하며 REVIEWED/GOLDEN_CANDIDATE/GOLDEN_APPROVED 전환·자동 학습·Prompt 변경은 미구현입니다. 선택형 reason만 사용하고 자유 입력을 받지 않습니다.

## API, Persistence와 Security

| API | 의미 |
| --- | --- |
| POST `/api/v1/validation/sessions` | store/scenario/명시적 consent로 참여 시작 |
| GET `/api/v1/validation/sessions/{id}` | 소유 Session·Task·실제 Journey |
| POST `/api/v1/validation/sessions/{id}/events` | 제한된 관찰/의견/중단 |
| POST `/api/v1/validation/sessions/{id}/complete` | 실제 과업 조건 검증 후 완료 receipt |
| GET `/api/v1/validation/summary?store=...&kind=USER_OBSERVATION` | 관리자 요약; SYNTHETIC 별도 |

쓰기에는 기존 Idempotency-Key/UoW를 사용합니다. 동일 key/동일 내용은 replay, 다른 내용은 conflict입니다. Session lock과 append-only 이벤트·멱등성 결과를 같은 transaction에서 처리하며 실패 시 rollback합니다. 완료/중단 후 새 이벤트는 409입니다. 단 같은 성공 요청의 replay는 기존 결과를 반환합니다.

기존 ProductEvent repository와 AccessUnitOfWork를 확장하고 additive `023_user_validation.sql`로 tenant-scoped Session 및 ProductEvent Session FK/index를 추가합니다. 이전 migration은 수정하지 않습니다. raw 데이터나 checkpoint를 새 테이블에 복제하지 않습니다.

Session read/write는 현재 Principal/tenant/store/role과 owner hash를 확인합니다. cross-tenant는 404, 동일 tenant의 다른 소유자/store/role 거부는 403입니다. Summary는 해당 매장 admin 권한이 필요하며 참가자 식별/원문은 반환하지 않습니다. 저장소 장애는 stable 503이며 데이터 없음과 구분합니다. 기존 Approval separation, Audit, Outbox, Job, Harness, Gateway와 Domain 전이는 그대로입니다.

## Metrics와 Availability

Summary window는 **최근 7일에 시작한 Session**입니다. 최대 최근 100 Session / 각 500 Event를 조회하고 한도 도달 시 `truncated`와 PARTIAL을 표시합니다. Synthetic과 USER_OBSERVATION을 합산하지 않습니다. N은 지표별 실제 관측 표본 수입니다. duration 지표는 관측 가능한 값의 중앙값, rate는 해당 분모의 평균입니다.

| 지표 | 실제 분모 / source |
| --- | --- |
| Task Completion Rate | 해당 Session 전체; ACTIVE/ABANDONED는 미완료 |
| Median Task Duration | 실제 완료 Session의 started→completed |
| Time to First Useful Evidence | Session 시작 이후 Evidence ref가 있는 최초 완료 Step |
| Time to Human Action | Session 시작→실제 사람 행동이 있는 AX 안내 관찰 |
| Time to Decision | Session 시작→고정 Run의 실제 Approval 결정 |
| Accept/Edit/Reject/Request More Evidence | 의견이 존재하는 Session의 마지막 의견; 서로 다른 outcome을 합산하지 않음 |
| Human Intervention / Manual Takeover | 고정 Run의 Session 구간 내 실제 control/결정; 참가자 행동 귀속은 PARTIAL |
| Loop Abort | 실제 고정 Run의 종료 결과가 관측 가능한 Session |
| End-to-End Completion | 기존 Run 완료+Verification 존재; FAIL/INCONCLUSIVE도 Runtime 완료일 수 있으며 과업 성공/PASS와 다름 |
| Cost per Completed Incident | 기존 완료 Run의 estimated cost; PARTIAL, 청구서나 전체 Incident 비용 아님 |

value 없음은 `null`/UNAVAILABLE이며 0으로 꾸미지 않습니다. 실제 관측값 0은 유효합니다. N<5는 INSUFFICIENT_SAMPLE, 한도/부분 귀속/추정 비용은 PARTIAL, 충분한 관측은 AVAILABLE입니다. 5라는 표시는 descriptive 표본 정책일 뿐 통계적 유의성 보장이 아닙니다. 임의 UX 종합 점수를 만들지 않습니다. 일부 Run 결과 지표는 최신 실제 projection이므로 전역 역사 warehouse가 아닙니다.

## Synthetic 시나리오와 재현

기존 Day 28 Demo/DataIntake와 Day 27/30 Golden source/Worker를 재사용합니다. 무작위 ID는 실행 격리를 위한 것이며 과업/데이터/expected outcome은 deterministic합니다. 운영 tenant에 자동 생성하지 않습니다. 명시적인 test/validation/CI 이름의 격리 DB만 허용하고 `fnb_voc`는 거부합니다. DB 이름 검사는 보조 fence이므로 반드시 본인이 만든 전용 DB를 지정하세요.

```powershell
# repository root; 반드시 별도로 만든 검증 DB URL을 사용합니다.
$env:SERVIQ_TEST_DATABASE_URL = '<isolated-test-database-url>'
uv run --extra dev python -m scripts.serviq_user_validation_smoke
```

| Scenario | 실제 검증 |
| --- | --- |
| Happy Path | Sample→조사→근거/RCA/CAPA→별도 사람 승인→Worker resume→내부 실행→PASS/RESOLVED→RAW Feedback→완료 |
| More Evidence | 실제 부족 근거→Human Action→REQUEST_MORE_EVIDENCE |
| Reopen | 실제 FAIL→REOPENED→결과 관찰 |
| Manual Takeover | 기존 control Command→MANUAL_TAKEOVER→관찰/의견 |
| Abandon | 실제 TASK_ABANDONED→ABANDONED, 성공으로 집계하지 않음 |

새 AccessPersistence/HTTP client로 다시 읽어 Session/Journey/Feedback/지표와 tenant/store/role·중복 보호를 검사합니다. 실제 LLM network를 요구하지 않습니다. HTTP fixture도 SYNTHETIC으로 생성하여 자동화를 사람 관찰로 집계하지 않습니다. 본인이 만든 전용 DB/Compose project만 정리하면 rerun 가능합니다.

## Golden/Test와 검증 결과

- root `uv run --extra dev ruff check .`: PASS.
- 전체 `uv run --extra dev pytest`: **824 passed**. 기존 793개를 유지하고 Day 31 계약/보안/지표/중복/순서/rollback/RAW/actual state 검증을 추가했습니다.
- backend `uv sync --locked`, app/migration import, `uv run --locked fastapi run --help`: PASS (Windows UTF-8 출력).
- frontend `npm ci`: PASS, audit 0 vulnerabilities. lint PASS, **33 files / 205 passed**, build PASS. dependency/lock 변경 없음.
- 실제 PostgreSQL smoke **15개**: postgres/security/queue/dashboard/settings/jev/llm_gateway/langgraph/verification/multi_agent/loop_harness/onboarding_import/tool_runtime/ax_rc/user_validation 모두 PASS.
- Synthetic 5 scenario와 fresh repository/HTTP Summary·RAW·tenant/store/role·event dedup PASS.
- 격리 Compose project에서 image build·migration·PostgreSQL/pgvector·API/frontend/nginx/Worker health와 기존 nginx HTTP 흐름 PASS. 새 nginx Session→AX/Review→실제 Worker→Verification→RAW Feedback→Metric Summary PASS. 기존 개발 DB/volume은 보존했습니다.
- CI PostgreSQL 및 Image/Compose job에 새 smoke/실제 nginx 경로를 추가했습니다. 원격 최종 상태는 PR Validation/Remote CI에 별도로 기록합니다. cancelled/skipped를 성공으로 취급하지 않습니다.
- 첫 frontend 전체 실행은 기존 테스트 파일의 Vitest worker 시작 오류로 실패했습니다. assertion/timeout 변경 없이 새 프로세스로 전체 재실행하여 위 결과를 얻었습니다.
- 첫 PG Loop smoke는 TEMPORARY_FAILURE로 실패했고 확정 원인은 확인하지 못했습니다. 동일 코드/설정의 전체 Loop smoke 재실행은 PASS입니다. 인프라 원인으로 단정하지 않습니다.
- Synthetic fixture 초기 검증에서 sample/operating source 분리 및 잘못된 simulation UUID가 거부되었습니다. fixture를 기존 안전 계약에 맞게 수정했으며 검사 자체를 완화하지 않았습니다. 테스트 DB 이름 fence의 거부는 명시적 validation DB로 다시 실행했습니다.
- 기존 테스트 삭제/skip/xfail/assertion 약화/무의미한 timeout 증가/Mock fallback 없음.
- 실제 external Provider 호출 **0**, external business write **0**.

**Synthetic Validation: PASS (자동화 시나리오/회귀).**

**Real User Validation: NOT YET PERFORMED.**

## Known Limitations / Not Implemented

- Action은 **INTERNAL_RECORD_ONLY**, Verification은 **SIMULATED**입니다. 현장 개선 효과나 실제 POS/ERP 변경을 증명하지 않습니다.
- 실제 사용자 3~5명 테스트, staging/demo 공개 배포, production OIDC/SSO와 Production Ready 선언은 하지 않았습니다.
- 전체 Data Governance/retention/deletion lifecycle, 외부 Analytics SaaS, 전역 metric warehouse/통계 검정은 미구현입니다. 계측된 동작은 제한적이며 N은 고유 사용자 수가 아닙니다.
- 첫 매장 등록 전에는 Session을 시작할 수 없습니다. 기존 온보딩을 재사용하며 등록 전 익명 행동 전체를 계측하지 않습니다.
- 참가자 이해도는 클릭/서버 상태만으로 증명하지 못합니다. 별도 Reviewer 결정은 업무 receipt이며 참가자 본인의 판단 성공을 자동 증명하지 않습니다.
- Session당 하나의 Incident/고정 Run을 관찰합니다. 새 Run으로 바뀌면 conflict로 분리하며 자동 귀속하지 않습니다. 전역 RC registry가 없어 release_candidate_id는 미지정이며 실제 Manifest digest를 사용합니다.
- 자유 입력 Feedback·curation·자동 학습·Golden 자동 승격·새 Agent/Provider/framework/실제 Connector는 추가하지 않았습니다.

## 실제 사용자 검증 방법과 다음 우선순위

1. 격리 demo/staging·synthetic tenant와 실제 역할/Reviewer를 준비합니다. 참가자는 운영 데이터와 섞이지 않는 환경을 사용합니다.
2. 실제 사용자 3~5명에게 수집 범위와 중단 방법을 설명하고 동의를 받습니다. 정답/클릭 위치 대신 “이 Incident를 이해하고 필요한 판단을 수행한 뒤 결과를 확인해 주세요”라는 업무 목표만 제시합니다.
3. Sample/Import→Incident→Brief→근거/RCA→Human Action/Review→Verification/최종 상태→의견 과정에서 막힌 지점과 판단 이유를 관찰합니다. 원문/PII를 analytics payload에 복제하지 않습니다.
4. Session 완료율·시간·선택형 의견·중단·Top Friction과 관찰 기록을 함께 해석합니다. 표본 1~2개나 Page View로 성공/품질을 과장하지 않습니다.
5. 가장 큰 blocker로 다음 작업을 정합니다. Onboarding, Evidence 해석, Next Best Action, 실제 데이터, 배포 접근성 중 무엇이 막혔는지 먼저 확인합니다. 자동으로 Day 32에 새 기술을 추가하지 않습니다.

Feedback가 충분히 누적되면 별도 검토/curation과 Offline Eval을 계획합니다. 사용자 과업→관찰→개선→Golden/Evaluation→재검증을 반복합니다.
