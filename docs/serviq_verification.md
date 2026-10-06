# Day 26 — Verification과 Incident Golden Closed Loop

## 목적 / 기준 main·Drive

기준 main은 `d40af046e8400e4e84f789eaf2b4917d5448fe3c`(PR #49, Day 25)입니다. Issue #50과 `codex/day-26-verification-golden` 하나에서 작업합니다. 최신 Drive 폴더는 `ServIQ_v0.5_운영안전_실행계약_통합설계`이며 더 높은 semantic version은 확인되지 않았습니다. fallback은 사용하지 않았고 Drive 원문은 수정하지 않았습니다.

00/03/07/15/24/28의 실제 내용을 대조했습니다. Drive의 Day 16 `main@c6060ae` snapshot·옛 일정/migration 번호를 현재 구현 상태로 사용하지 않습니다. GitHub main이 구현 현실, Drive 책임·안전 계약이 목표 기준입니다. 이번 실행 프롬프트의 기본 10개와 의미 있는 추가 fix 허용 정책을 적용합니다.

## Day 25 → Day 26 / 실행 범위

Day 25의 기존 v3 승인은 여전히 READY_TO_EXECUTE입니다. Day 26은 default false인 versioned 설정 `internal_execution_enabled`를 켠 **새로운 명시적 History Job**에서만 `history-verification-v4`를 선택합니다. Jev Shadow 전체를 자동 실행으로 바꾸지 않으며 v1/v2/v3 저장 이력을 재작성하지 않습니다.

```text
Incident → Jev → 명시적 History Job → History/Evidence/Sufficiency/RCA
→ CAPA Application Command → Approval Request → WAITING_APPROVAL
→ Human Review approve → persistent Resume Job → 승인 재검증
→ 내부 실행 기록(EXECUTING) → VERIFYING → Verification
→ PASS: RESOLVED / FAIL: REOPENED / INCONCLUSIVE: VERIFYING
```

반려는 실행에 진입하지 않습니다. RESOLVED와 CLOSED는 다르며 자동 CLOSED는 없습니다. 외부 POS/ERP/재고/공급사 write는 **0회**입니다.

## Execution Record / Approval 재검증

`ActionExecutionRecord`는 Tenant/Incident/AgentRun/action/Approval/digest/config/correlation/Incident version, aware 시작·완료 시각과 고정 safe summary를 갖는 불변 계약입니다. `execution_mode=INTERNAL_RECORD_ONLY`, `status=SUCCEEDED`는 **내부 기록 생성 성공**이지 외부 조치 성공이 아닙니다.

Application이 요청 시 신뢰된 운영 권한과 매장 범위를 확인하고 실행 직전 실제 Approval의 APPROVED/만료/action digest/Incident state·version/현재 approval policy를 다시 검사합니다. pinned 설정과 최신 설정의 opt-in이 모두 필요합니다. 하나의 CAPA만 지원하며 지원하지 않는 다중 실행은 거부합니다.

같은 UoW에서 Domain `EXECUTING`, execution insert, AgentRun state, Audit/Outbox를 저장합니다. 결정적 execution identity와 Tenant/run unique boundary로 중복 실행 기록을 막습니다. Audit 실패면 모두 롤백합니다. 다음 별도 Command는 실제 기록·승인·criteria·digest·expected version을 확인한 뒤 `VERIFYING`으로 전이합니다. 기존 arbitrary status PATCH 금지는 유지합니다.

## Verification Candidate / Evidence / 기준별 판정

기존 Incident Verification을 확장하며 별도 Aggregate로 대체하지 않습니다. Workflow 후보는 execution/action/Incident/config와 실제 검증 Evidence ID, criteria, 기준별 result, stable reason, aware 시각을 포함합니다. Domain/순수 규칙은 LangGraph/Provider SDK와 독립적입니다.

이번 좁은 기준은 기존 CAPA의 “담당자의 이력·절차 재검토 기록과 추가 근거 목록이 존재해야 합니다”입니다. `REVIEW_RECORD_PRESENT`와 `ADDITIONAL_EVIDENCE_LIST`를 각각 판정합니다. 임의의 현장 품질 기준을 이해하는 범용 Agent가 아닙니다.

검증 출처는 인증된 Application 내부의 `VerificationEvidence`이며 Tenant/store/run/action/execution, `internal-review:<uuid>` provenance, 관측 시각과 허용된 원본 review 참조를 검증합니다. **observation_mode=SIMULATED**만 지원합니다. Golden 검증은 명시적 `InternalReviewSimulation` 입력을 먼저 준비하고, 내부 execution 저장 후 그 execution에 묶인 합성 후속 관측 기록을 생성합니다. 준비 입력과 Evidence는 별개입니다. 원본 VOC나 LLM 답변을 조치 후 Evidence로 위장하지 않습니다.

합성 입력을 준비하는 공개 POST는 없으며 인증된 좁은 Application 경계만 있습니다. 입력을 준비하지 않으면 후속 근거가 없어 INCONCLUSIVE입니다. 미래 실제 현장 source ingest/connector로 확장하기 전에는 물리적 CAPA 효과나 실제 사람이 현장에서 검토했다는 사실을 입증하지 않습니다.

| 결과 | 판정 의미 | Domain 결과 |
| --- | --- | --- |
| PASS | 유효한 합성 내부 검토 기록과 추가 근거 참조가 기준 충족 | RESOLVED |
| FAIL | 유효한 후속 관측에서 기준 미충족이 명시됨 | REOPENED |
| INCONCLUSIVE | 후속 근거 없음/unknown/오래됨/상충/미지원 기준 | VERIFYING 유지 |

과거 History·RCA·사람의 Approval만으로 PASS를 만들지 않습니다. 시각은 execution 이후·현재 이전·pinned verification window 안이어야 합니다. 이유는 CRITERIA_MET/NOT_MET, EVIDENCE_MISSING/STALE/CONFLICTING, UNSUPPORTED_CRITERIA입니다. confidence는 이 좁은 결정적 기준의 판정 여부(1 또는 0)이며 실제 현장 효과의 통계적 확률이 아닙니다.

## Application / Domain / durable Workflow

Graph는 기존 Runtime을 확장합니다. 승인 결과 뒤 approved branch에 `internal_execution → begin_verification → verification → apply_verification → persist_result`를 추가합니다. Graph/LLM이 Incident를 직접 수정하지 않습니다. Application이 저장된 원본 Evidence와 pinned 설정으로 후보를 재생성해 비교한 뒤 기존 Domain verify/resolve/reopen invariant를 사용합니다. 후보 조작·없는 Evidence·Tenant/store mismatch는 거부합니다.

Checkpoint와 business trace 책임을 분리합니다. execution/verification effect가 UoW에 저장된 뒤 checkpoint가 실패해도 저장된 원본을 재사용하고 Incident expected version·actual Verification identity를 확인합니다. 재시작은 같은 run/workflow/config/Approval/action/digest를 유지하며 새 기록·외부 호출을 만들지 않습니다. 아직 저장하지 못한 effect는 재검증하며 Workflow 오류를 Incident FAILED로 바꾸지 않습니다.

장시간 checkpoint 대기에서 과거 PASS 후보가 복원되면 Application은 canonical 후보를 검사한 뒤 현재 시각의 근거 freshness를 다시 평가합니다. 이미 오래된 관측이면 INCONCLUSIVE/EVIDENCE_STALE로 저장해 VERIFYING을 유지합니다. 이미 적용한 Verification의 idempotent replay를 재판정/자동 취소하는 것은 아닙니다.

Job Worker의 claim/lease/heartbeat/늦은 ACK 보호를 유지합니다. 완료 Job을 lease 없는 RUNNING Job처럼 호출하지 않으며 검증에서는 실제 Worker claim과 완료 결과의 Application replay를 분리합니다. 기존 History/RCA 외부 LLM effect claim/memoization과 Data Policy/Gateway 경계도 유지합니다. Verification 자체는 결정적이며 LLM을 호출하지 않습니다.

## Persistence / Migration

기존 applied SQL은 수정하지 않았습니다.

- `017_internal_execution.sql`: Tenant/run FK·unique execution, immutable post-action Evidence.
- `018_verification_steps.sql`: Step 1..15 additive 확장, 명시적 합성 검토 입력의 Tenant/run persistence.

실행/근거는 immutable insert, 후보/Domain Verification은 AgentRun state와 Incident에 같은 UoW로 저장합니다. Step trace는 기존 append-only repository를 사용합니다. 부정합 후보는 persistence 전에 차단하고 복원된 WorkflowState도 Tenant/store/action/source lineage를 다시 검증합니다. raw prompt/response/VOC/secret은 저장하지 않습니다.

## API / Trace UI

기존 `GET /api/v1/incidents/{id}/agent-runs` 및 `/{run_id}`에 execution, verification, verification_evidence, resulting_incident_status를 additive하게 연결했습니다. Incident detail의 기존 Verification도 execution/evidence/criteria/observation mode를 제공합니다. Cross-Tenant 404, 같은 Tenant store/권한 부족 403, bounded query와 stable error 경계를 유지합니다. raw checkpoint/위임 권한/idempotency key는 반환하지 않습니다. arbitrary Agent 실행 POST도 없습니다.

기존 한국어 History Trace와 Review를 재사용합니다. 내부 실행 기록/SIMULATED 경고, 기준별 PASS/FAIL/INCONCLUSIVE, safe provenance, 설정/시각과 RESOLVED/REOPENED/VERIFYING을 서버 결과 그대로 표시합니다. 승인 대기와 내부 기록 완료를 구분하며 “외부 조치 실행 완료”로 표시하지 않습니다. loading/empty/error/manual refresh와 HTTP 실패 시 Mock fallback 금지를 유지합니다.

기존 Incident CAPA 탭도 EXECUTED를 “실행 기록 있음”으로 표시하고 외부 변경과 구분합니다. 검증 탭은 서버의 SIMULATED와 criteria/evidence reference를 표시합니다. Trace를 열기 전에도 실제 외부 조치 성공으로 오해하지 않도록 했습니다.

## Golden fixture / 실행법

`data/golden/verification_closed_loop.json`은 verification_pass/fail/inconclusive 3종의 synthetic case, 필요한 근거, acceptable RCA, approval과 최종 상태를 명시합니다. Day 29 범용 Evaluation Framework가 아니라 좁은 fixture+smoke입니다.

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest
# SERVIQ_TEST_DATABASE_URL은 운영 DB가 아닌 명시적 검증 전용 DB
uv run --extra dev python -m scripts.serviq_verification_smoke
```

nginx 검증에서는 worker를 잠시 중지해 `--seed-http PASS|FAIL|INCONCLUSIVE` Application fixture를 준비하고 실제 worker를 다시 시작합니다. fixture JSON을 `SERVIQ_VERIFICATION_HTTP_FIXTURE`에 전달해 기존 HTTP smoke의 후속 전용 모드를 실행합니다. 기존 전체 HTTP 및 CAPA smoke는 선행 단계에서 각각 유지합니다. 이 분리로 concurrent Golden RCA 생성이 기존 Dashboard의 정확한 +1 assertion을 오염시키지 않습니다.

## Failure / Security / Data Governance

승인 없는 실행·만료·stale digest/version·변경된 policy·권한 없는 source·fabricated Evidence·unsupported criteria는 fail closed입니다. FAIL/INCONCLUSIVE가 RESOLVED로 들어가지 않으며 반려가 실행으로 연결되지 않습니다. DB/Audit/checkpoint failure, 같은 Job/Approval replay, 재시작을 회귀로 고정합니다. 단일 실행 lease와 Tenant scoped repository가 중복/격리 경계입니다.

raw VOC/prompt/response/credential/불필요 PII·delegation token을 Trace/API/Checkpoint에 넣지 않습니다. 실제 Gemini/Ollama 네트워크 호출은 PR 테스트와 Golden smoke에서 0회이며 Fake/결정적 경계를 사용합니다. 사용자 개발 DB/volume은 보존하고 같은 고정 `serviq` Compose 안의 검증 DB만 사용합니다.

## Validation

2026-10-06 로컬 최종 검증 결과입니다.

| 영역 | 실제 결과 |
| --- | --- |
| Python | `ruff check .` 통과, 기능 중심 구조 회귀 6개 포함 전체 `pytest` **651 passed** |
| Backend | `uv sync --locked`, UTF-8 환경의 `fastapi run --help`, locked app import 통과 |
| Frontend | Node 24.19 / `npm ci` 통과(취약점 0), lint·전체 **28 files / 173 passed**·TypeScript/Vite build 통과 |
| PostgreSQL | postgres/security/queue/dashboard/settings/jev/llm_gateway/langgraph 기존 8종 및 verification smoke 모두 최신 API 이미지에서 통과 |
| Golden | 실제 PG/Checkpoint 재시작 및 nginx/Review/Worker 경로에서 PASS→RESOLVED, FAIL→REOPENED, INCONCLUSIVE→VERIFYING 통과 |
| HTTP | 기존 전체 Incident/Review/Queue/Dashboard/Settings/Jev 조회와 CAPA approval/resume smoke 통과 |
| Docker/Compose | `scripts/compose_smoke.ps1`, 최신 API/frontend/worker 이미지 build·migration·health, 네트워크 없는 FastAPI/RAG import·nginx 설정 검증 통과 |
| 외부 효과 | Golden/PR 회귀에서 실제 Gemini/Ollama 호출 0회, external write 0회 |

검증 중 frontend 전체 테스트와 Docker/DB 작업을 동시에 실행한 첫 시도에서는 worker 시작 timeout이 발생했습니다. timeout이나 assertion을 바꾸지 않고 작업을 직렬화한 뒤 전체 suite를 다시 실행해 통과했으며, 마지막 UI 수정 후에도 전체 173개를 재검증했습니다. PostgreSQL smoke도 Golden 데이터가 섞인 DB에서 시작하지 않고 깨끗한 격리 DB에서 기존 정확한 assertion을 유지해 실행했습니다.

추가 수정은 복원된 근거의 Tenant/store/source 검증, checkpoint 대기 후 현재 freshness 재검증, 기존 Incident 화면의 내부 기록/외부 실행 구분입니다. 기본 구현·테스트·문서 10개에 이 3개 fix를 더했습니다. 이후 사용자 요청의 1차 구조 정리 6개, 기능 중심 `agents`/`routing`/`llm` 통합과 최종 문서 4개를 더해 총 23개입니다. [현재 프로젝트 구조](serviq_structure.md)에 실제 파일 책임과 import 경계를 기록했습니다. 커밋 수를 맞추기 위한 변경이나 빈 커밋은 없습니다.

검증은 기존 고정 `serviq` 프로젝트와 `serviq_postgres_data` 볼륨을 사용하되 task 전용 DB 세 개로 격리했습니다. 기존 `fnb_voc` DB/볼륨은 보존합니다. 원격 GitHub Actions 결과는 PR의 최신 check가 source of truth이며, 로컬 성공만으로 원격 CI 통과를 선언하지 않습니다. PR을 자동 merge하지 않습니다.

## Known Limitations / Not Implemented / Next

내부 단일 MANUAL_HISTORY_REVIEW CAPA와 합성 후속 source만 지원합니다. 물리적 현장 개선 효과 검증, 검증 후 추가 근거를 수집하는 자동 재조사 loop, 범용 verification criteria 해석·복구 UI·실제 source collector는 미구현입니다. 기존 수동 Incident 명령은 호환을 유지하며 v4의 엄격한 자동 검증 경계와 구분합니다. trusted delegation은 기존 권한 snapshot이며 production IdP 권한 철회 연동은 아닙니다.

외부 POS/ERP/Connector write, Harness/MCP, Multi-Agent, automatic CLOSED, production OIDC/deployment는 구현하지 않았습니다. Day 26은 Production Release나 실제 Gemini production 품질 검증 완료가 아닙니다.

Day 27 후보는 최신 main/Drive를 다시 확인한 뒤 History + 1~2개 독립 read-only Investigation Agent의 최소 fan-out/fan-in입니다. Day 28 좁은 Harness/MCP, Day 29 Golden Evaluation/Hardening, Day 30 MVP Release Candidate 경로를 유지합니다. 실제 Golden E2E·provenance·Approval·Verification·Tenant/RBAC/Audit/Idempotency·Trace·Compose 재현성은 축소하지 않습니다.
