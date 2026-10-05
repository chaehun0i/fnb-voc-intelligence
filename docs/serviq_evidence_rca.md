# Day 24 Evidence Sufficiency와 RCA Workflow

## 목적과 기준

Day 23의 단일 History 조사에 `Evidence 정규화 → 충분성 → 근거 기반 RCA 후보 → 영속 Trace`를 연결합니다. 근거가 없거나 상충하면 억지로 원인을 생성하지 않습니다. Agent 결과는 제안이며 Incident Domain command가 아닙니다.

기준 main은 `3d70b23c5e0ae0410d53512b074fb1c7c9f909cc`(Day 23 PR #45)입니다. 설계 정본은 [ServIQ v0.5 운영안전·실행계약 통합설계](https://drive.google.com/drive/folders/1eVwhcoTWaebKUqmJgdGMBF9xY7gXcmmJ)이며 더 높은 버전/fallback은 없습니다. 00·03·07·08·15·18·25·28의 실제 계약을 대조했습니다. Drive 일부 구현현황은 Day 16 스냅샷이므로 실제 Day 17~23 main을 현재 구현 기준으로 사용했습니다. Drive 원문은 변경하지 않았습니다.

Issue [#46](https://github.com/chaehun0i/fnb-voc-intelligence/issues/46), 브랜치 `codex/day-24-evidence-rca` 하나로 진행합니다. 자동 병합하지 않습니다.

## Day 23에서 이어받은 경계

Tenant/Principal/RBAC·Audit/Idempotency, 기존 Incident 상태머신, Job/Worker, Jev Shadow, 고정된 Config Version, LLM Gateway/Data Policy, AgentRun/Step와 LangGraph Checkpoint를 재사용합니다. 새 Runtime·Queue·Provider SDK를 추가하지 않습니다.

새 실행은 `history-evidence-v2`입니다. 이미 영속화된 `history-v1` 실행은 기존 3단계 graph로 재개하므로 진행 중 실행을 새 workflow로 바꾸지 않습니다. HTTP 신규 필드에는 이전 응답 호환 기본값이 있지만 장애 시 fixture fallback은 아닙니다.

## Evidence 계약과 정규화

기존 EvidenceCandidate/Finding/EvidenceGap/WorkflowState를 확장했습니다. 정규화 근거에는 `review:<id>`, 원본 ID, Tenant/store, AgentRun/History Step, 순위, 검색/원본 시각, lexical/vector/hybrid provenance, 관측 코드와 지지/반대/중립 성격이 있습니다. immutable 모델은 임의 raw 필드·시간대 없는 timestamp·불일치 참조를 거부합니다.

검색은 기존 SearchService/pgvector와 Tenant/store SQL 필터를 재사용합니다. 같은 원본의 lexical/vector 결과는 하나로 합치면서 검색 경로와 최상위 순위를 보존합니다. 같은 출처의 상충 관측을 조용히 덮어쓰지 않습니다. Cross-Tenant/store 후보도 정규화 단계에서 거부합니다.

검색 일치는 `RELATED_HISTORY_MATCH`라는 제한된 관측이며 물리적 원인의 증거가 아닙니다. 생성된 LLM 문장/RAG 답변을 원본으로 저장하지 않습니다. 원본 Review 날짜만 있는 경우 UTC 날짜 시작을 source timestamp로 사용하며 정확한 사건 발생 시각을 뜻하지 않습니다. 이전 참조만 있는 데이터는 NEUTRAL/REFERENCE_ONLY로 취급합니다.

## Sufficiency policy

`history-support-v1` 명시적 policy의 기본은 독립적인 관련 VOC 원본 2개와 VOC_REVIEW source coverage입니다. 이 기준은 반복 불만 **가설**의 최소 조건이지 근본 원인 확정 기준이 아닙니다. 운영 Settings에서 이 threshold를 수정하는 기능은 없습니다.

| 판정 | 조건 / 처리 |
| --- | --- |
| INSUFFICIENT | 0건, 독립 지지 출처 부족, 참조만 존재: RCA 노드 생략 |
| CONFLICTING | 반대 근거 존재: 원인 확정/후보 생성 대신 상충 결과와 공백 유지 |
| SUFFICIENT | 명시적 출처·지지 coverage 충족: RCA 정책/예산 gate로 진행 |

결과는 dimensions, 지지/반대 참조, 공백, stable reason code를 포함합니다. `NO_EVIDENCE`, `INSUFFICIENT_SOURCE_COVERAGE`, `CONFLICTING_EVIDENCE`, `SUFFICIENT_HISTORY_SUPPORT`를 사용합니다. Gateway 실패가 근거의 존재 자체를 지우지 않습니다. 충분성이 충족돼도 LLM 실패·설정 비활성·예산 제한으로 RCA가 없을 수 있습니다.

## RCA candidate

현재 지원 범위는 `REPEATED_HISTORY_SIGNAL` 하나입니다. 안전한 고정 가설은 “반복 불만 이력이 관측되어 공통 원인에 대한 추가 조사가 필요합니다.”입니다. 이를 설비·공급업체 등 특정 원인으로 확대하지 않습니다.

후보에는 stable ID, 0..1 점수, 실제 supporting/contradicting Evidence 참조, 미해결 공백, `HISTORY_HYPOTHESIS_NOT_CONFIRMED`, 생성 경계, Config/Jev/LLM request 참조가 있습니다. 근거 없는 후보·존재하지 않는 ID·지지와 반대 중복·다른 Config/Decision lineage를 검증에서 거부합니다. 점수는 검증된 원인 확률이 아닙니다.

`auto_rca_draft`와 iteration/run deadline을 검사합니다. Jev가 LLM 불필요라고 하면 결정적 가설 경로(점수 0.5)를 사용합니다. LLM 필요 시 기존 Gateway에 원문이 아닌 참조/관측 코드만 전달하고, 남은 토큰·비용·고정 run deadline을 적용합니다. schema allowlist 검증과 업무 참조 검증을 분리하며 Gateway의 bounded repair/Data Policy를 재사용합니다. History LLM 정책 거부/사용 불가는 자동으로 다른 RCA 호출을 강제하지 않습니다.

## LangGraph와 durable persistence

```text
validate_context → history_investigation → normalize_evidence
→ evaluate_sufficiency → [SUFFICIENT: rca_investigation]
→ persist_result → END
```

단일 순차 graph이며 Multi-Agent fan-in이 아닙니다. 새 결과는 기존 AgentRun JSON과 append-only Step 결과에 저장합니다. 별도 writable 업무 projection은 만들지 않았습니다. 재구성/저장 시 Evidence·Tenant/run·Config/Jev 참조를 다시 검증합니다. API는 내부 Step snapshot 전체를 공개하지 않습니다.

additive `014_rca_effects.sql`은 실행별 RCA 외부 효과 claim과 Tenant/run FK, 불변 trigger를 추가합니다. 기존 011의 Step 순서 1..3 제약은 새 migration에서 1..6으로 확장하며 기존 migration은 수정하지 않았습니다. migration 반복 실행과 실제 PostgreSQL 저장/재시작을 검증했습니다.

RCA 결과를 Run에 메모화한 뒤 Checkpoint를 저장합니다. 결과 저장 이후 Checkpoint가 실패하면 같은 실행을 복원하여 재호출하지 않습니다. 외부 효과 claim 후 성공 여부가 불확실한 중단은 자동 재호출 대신 실패 경계를 유지합니다. 외부 API exactly-once를 보장한다고 주장하지 않습니다. AgentRun 완료는 최종 Checkpoint 완료 뒤이며 Workflow 실패는 Incident 상태를 변경하지 않습니다.

## API와 운영 Trace

기존 조회 전용 경로를 확장했습니다.

- `GET /api/v1/incidents/{id}/agent-runs`
- `GET /api/v1/incidents/{id}/agent-runs/{run_id}`

정규화 Evidence, 충분성/코드/공백, RCA/근거 참조, Config/Jev/run lineage를 반환합니다. 기존 pagination과 인증/RBAC를 유지합니다. Cross-Tenant ID는 404, 같은 Tenant의 허용되지 않은 store는 403, 잘못된 query는 422, 저장소 불가는 stable 503입니다. 임의 실행 POST는 없습니다.

실제 Incident Trace와 실행 추적 페이지는 한국어 상태·출처·검색 경로·미확정 후보를 표시합니다. 지지/반대 참조를 눌러 원본 메타데이터를 펼칠 수 있습니다. loading/empty/error/수동 refresh를 유지하고 서버 계산만 표시합니다. Mock 미래 Multi-Agent는 Demo 경계이며 HTTP 장애에 섞지 않습니다.

## 보안과 실패 의미

raw VOC 전문, raw prompt/response, secret/credential/불필요 PII를 새 모델·Run·Step·Checkpoint·API에 복제하지 않습니다. 참조 ID도 Tenant/store에 따라 조회됩니다. Domain/Agent 코드의 Provider SDK 직접 import를 architecture test로 금지합니다.

근거 0건·상충은 정상적인 미확정 결과입니다. LLM 정책/출력/사용 불가, 비활성 설정, 예산 부족은 공백으로 표시하며 가짜 원인을 만들지 않습니다. Checkpoint/영속 기록 장애는 실패로 관측하고 자동 성공으로 숨기지 않습니다. 불확실한 외부 효과의 수동 복구 UI는 아직 없습니다.

## Validation

실제 실행한 로컬 검증:

| 명령 / 범위 | 결과 |
| --- | --- |
| `uv run --extra dev ruff check .` | 통과 |
| `uv run --extra dev pytest` | 567 passed, skip/xfail 우회 없음 |
| backend `uv sync --locked` / `uv run --locked fastapi run --help` | 통과 |
| frontend `npm ci` / `npm run lint` | 통과, Node 24.19.0 |
| frontend `npm run test` / `npm run build` | 24 files / 155 passed, 빌드 통과 |
| PostgreSQL / security / queue / dashboard / settings / Jev / LLM Gateway smoke | 각각 통과 |
| `scripts.serviq_langgraph_smoke` | 실제 PostgreSQL History·Evidence/RCA 결과/Checkpoint 저장, 실패 후 재시작, Config v3 고정, History/RCA 호출 각 1회, 실제 API, Tenant/store 격리 통과 |

PostgreSQL smoke는 운영 DB와 분리한 검증 DB에서 실행했습니다. 신규 runtime 회귀는 기존 v1 graph, 정책 거부/사용 불가/잘못된 structured output, 외부 효과 불확실성, 중복 Job, 고정 deadline, 동일 입력/출처 보존을 검증합니다. 모든 PR 검증의 실제 Gemini/Ollama 호출은 0회입니다. 원격 CI 결과와 로컬 검증은 구분해 PR에 기록합니다.

`./scripts/compose_smoke.ps1`의 기존 CLI/pgvector 연결 검증, ServIQ `up --build -d --wait api frontend worker`의 migration/health, `scripts.serviq_http_smoke`의 실제 nginx→Incident/Review/Queue/Dashboard/Settings/Jev/LLM/AgentRun 조회 회귀가 통과했습니다. API 컨테이너 내부에서도 확장 LangGraph smoke로 Evidence/RCA·Checkpoint 실패 후 재시작·실제 Trace API를 확인했습니다. nginx에서는 조회 라우팅/응답 경계를, PostgreSQL smoke에서는 실제 RCA 내용과 tenant isolation을 검증했습니다.

고정 Compose 프로젝트 `serviq`를 유지하고 검증 전용 DB를 사용했습니다. 종료 후 원래 `fnb_voc` 연결과 API/frontend/Worker health를 복구했으며 사용자 데이터/볼륨은 삭제하지 않았습니다. 테스트 도중 기존 Step 순서 1..3 DB 제약으로 새 단계가 실패한 원인을 확인해 additive 014에서 확장했고, 이후 전체 durable smoke를 다시 통과했습니다.

## Known limitations / Not implemented / Next

지원하는 RCA는 반복 이력의 미확정 조사 가설 하나이며 특정 물리적 근본 원인의 품질 검증이나 전체 Golden Evaluation이 아닙니다. 신뢰할 수 있는 출처 적재가 필요하며 raw 전역 VOC를 모든 Tenant에 공개하지 않습니다. 검색 결과를 자동으로 Incident RootCauseCandidate/CAPA로 반영하지 않습니다.

CAPA 자동 생성/실행, Approval interrupt/resume, Verification, Multi-Agent fan-out/fan-in, Harness, MCP, 실제 Connector/외부 write, production OIDC/SSO, production-ready release는 이번 Day에 구현하지 않았습니다. Jev Shadow 전체를 자동 Agent 실행으로 바꾸지 않았습니다.

Day 25 후보는 **CAPA Proposal + Approval Boundary**입니다. 최신 main/설계를 다시 확인하고 Day 30 MVP Golden Workflow의 Evidence provenance·Human Approval·Verification·Trace·보안·재현성을 우선합니다.
