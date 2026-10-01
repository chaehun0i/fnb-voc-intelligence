# Day 13: ServIQ v0.4.1 프론트엔드 기반

## 제품 범위

ServIQ는 VOC 분석 프로젝트에서 Incident 조사, 근본 원인 분석(RCA), 시정·예방 조치(CAPA), 사람의 승인, 검증을 지원하는 운영 제품으로 확장됩니다. Day 13에서는 백엔드 Agent나 LLM 호출을 구현하지 않고, 제품 화면과 계약을 먼저 고정합니다.

기존 Streamlit Dashboard는 Day 1~12의 VOC, RAG, pgvector, ingestion, PostgreSQL 분석 흐름을 계속 담당합니다. `frontend/`는 별도의 React + TypeScript 기반 데스크톱 운영 콘솔입니다.

## Frontend-first, Contract-first

프론트엔드는 향후 FastAPI/Pydantic 모델과 맞추기 위해 `Incident`, `Evidence`, `RootCauseCandidate`, `CorrectiveAction`, `Approval`, `Verification`, `AgentRun`, `AgentStep`, `ToolCall`, `ControlPlaneConfig`, `QueueJob` 계약을 사용합니다.

화면은 별도 Mock API를 통해 데이터를 받습니다. 승인 버튼 같은 정책 결과는 클라이언트가 임의로 판단하지 않고 `allowed`, `reason` 계약 값으로 표시합니다.

## Day 13 구현 범위

- Dashboard, Incidents, Reviews, Agent Trace, Integrations, Queue, Settings 운영 셸
- Incident 목록·상세, 상태 타임라인, Evidence, RCA, CAPA, Verification
- 계약 기반 권한 정보를 표시하는 Human Review Queue
- Jev, LangGraph, Multi-Agent 실행 정보를 연결할 수 있는 Agent Trace
- 설정 버전 관점을 고려한 Control Plane 설정 화면

## Provider와 Agent 경계

Gemini는 기본 Provider이며 Ollama는 로컬 개발과 대체 Provider로 유지합니다. Agent가 특정 Provider를 직접 호출하지 않으며, 두 Provider는 향후 공통 LLM Gateway 뒤에 배치됩니다. Day 13에서는 Jev, Gemini, Ollama, LangGraph를 실제 호출하지 않습니다.

## 다음 개발 순서

`Domain/API -> Queue/Worker -> Jev -> LLM Gateway -> LangGraph -> Multi-Agent -> Harness/Loop -> MCP`

Day 14에서는 Mock API Adapter를 실제 FastAPI Contract로 교체하되, 프론트엔드 컴포넌트 인터페이스는 유지합니다.

## 실행 및 검증

프론트엔드 의존성 설치 후 `frontend` 디렉터리에서 다음 명령을 실행합니다.

```bash
npm run lint
npm run test
npm run build
```

기존 Python 프로젝트 검증은 저장소 루트에서 실행합니다.

```bash
ruff check .
pytest
```
