# Day 23 LangGraph History Investigation

## 목적

Day 22 Gateway 다음에 단일 History 조사 실행 경계를 연결합니다. Day 30 MVP를 위해 Agent 종류 확대보다 실제 Incident의 재시작 가능한 조사와 근거 출처를 우선합니다.

## 구성

- AgentRun은 운영 실행 이력, Checkpoint는 Graph 복구 상태입니다. 서로 다른 저장 책임을 갖습니다.
- WorkflowState는 참조와 정규화 Finding/EvidenceCandidate/EvidenceGap만 보관합니다.
- 원문 VOC, prompt/response, credential, 개인정보는 실행 상태에 저장하지 않습니다.
- `011_agent_runs.sql`은 실행 원본/설정/Job 참조와 추가 전용 단계 이력을 영속화합니다. 동일 조직/Job에는 실행 한 건만 생성합니다.
- 실제 LangGraph는 `validate_context → history_investigation → persist_result`를 실행합니다. `durability="sync"`와 JSON 전용 serializer를 사용하고, PostgreSQL Checkpoint는 공식 PostgresSaver로 복구합니다.
- History는 기존 SearchService/hybrid/pgvector 경계를 재사용합니다. `012_history_sources.sql`의 조직/매장 출처 연결이 없는 전역 VOC는 검색하지 않습니다. 검색 원문은 Checkpoint에 넣지 않고 원본 review 참조만 증거 후보로 보존합니다.
- LLM은 Jev가 요구하고 검색 근거가 있을 때만 기존 Gateway를 통해 정규화 보조 판정을 요청합니다. 원문은 전송하지 않으며 생성 답변을 증거로 취급하지 않습니다.
- 실행은 내부 `HistoryWorkflows.enqueue(RequestContext, incident_id, decision_id)`로 명시적으로 요청합니다. `auto_investigation`, `jev_enabled`, HISTORY 선택, `voc.search` 허용, 조사 가능한 상태를 모두 확인합니다. AgentRun은 시작 시 선택한 과거 Config Version을 계속 사용합니다. Shadow 전체를 자동 실행으로 바꾸지 않습니다.
- 기존 JobWorker가 `incident.history_investigation`을 인수하여 Graph invoke/resume과 Trace를 실행합니다. PostgreSQL 실행 잠금과 heartbeat로 중복·late Worker를 차단합니다. 검색 결과는 노드 완료와 별도로 영속 메모화하여 Checkpoint 재저장 시 재검색/재호출하지 않습니다.
- LLM 경계는 `013_history_effects.sql`에 호출 전 claim을 기록합니다. 호출 직후 crash로 결과가 불확실한 경우 자동 재호출하지 않고 실패 이력으로 남깁니다. 이 제한은 외부 Provider의 exactly-once 보장을 주장하지 않기 위한 안전 경계입니다.

## 실행/검증

구현 단계별 관련 테스트를 실행하고 최종 전체 검증 결과를 이 문서에 기록합니다.

## 제한 사항

이번 Day는 History 하나만 대상으로 하며 Multi-Agent, RCA/CAPA, Approval interrupt, Verification, Harness/MCP를 구현하지 않습니다.

## 다음 단계

Day 24 Evidence Fan-in / Sufficiency / RCA Draft를 이어갑니다.
