# Day 23 LangGraph History Investigation

## 목적

Day 22 Gateway 다음에 단일 History 조사 실행 경계를 연결합니다. Day 30 MVP를 위해 Agent 종류 확대보다 실제 Incident의 재시작 가능한 조사와 근거 출처를 우선합니다.

## 구성

- AgentRun은 운영 실행 이력, Checkpoint는 Graph 복구 상태입니다. 서로 다른 저장 책임을 갖습니다.
- WorkflowState는 참조와 정규화 Finding/EvidenceCandidate/EvidenceGap만 보관합니다.
- 원문 VOC, prompt/response, credential, 개인정보는 실행 상태에 저장하지 않습니다.
- `011_agent_runs.sql`은 실행 원본/설정/Job 참조와 추가 전용 단계 이력을 영속화합니다. 동일 조직/Job에는 실행 한 건만 생성합니다.
- 실제 LangGraph는 `validate_context → history_investigation → persist_result`를 실행합니다. `durability="sync"`와 JSON 전용 serializer를 사용하고, PostgreSQL Checkpoint는 공식 PostgresSaver로 복구합니다.

## 실행/검증

구현 단계별 관련 테스트를 실행하고 최종 전체 검증 결과를 이 문서에 기록합니다.

## 제한 사항

이번 Day는 History 하나만 대상으로 하며 Multi-Agent, RCA/CAPA, Approval interrupt, Verification, Harness/MCP를 구현하지 않습니다.

## 다음 단계

Day 24 Evidence Fan-in / Sufficiency / RCA Draft를 이어갑니다.
