# Day 13 ServIQ Frontend

## 목적

Day 13은 ServIQ v0.4.1 전환의 첫 단계입니다. 실제 백엔드 Agent를 구현하기 전에 운영 제품의 화면 흐름과 API 계약을 먼저 확정합니다.

기존 Streamlit Dashboard는 Day 1~12의 VOC 분석, RAG, pgvector, ingestion, PostgreSQL 흐름을 계속 담당합니다. `frontend/`는 이를 대체하지 않는 별도의 React + TypeScript 운영 콘솔입니다.

## 구성

`frontend/`는 Vite 기반 React + TypeScript 애플리케이션입니다. 공통 App Shell은 Dashboard, Incidents, Reviews, Agent Trace, Integrations, Queue, Settings 메뉴를 제공합니다.

화면은 별도 Mock API 계층을 통해 데이터를 받습니다. `Incident`, `Evidence`, `RootCauseCandidate`, `CorrectiveAction`, `Approval`, `Verification`, `AgentRun`, `AgentStep`, `ToolCall`, `ControlPlaneConfig`, `QueueJob` 타입은 향후 FastAPI/Pydantic 계약과 연결하기 위한 기반입니다.

Incident 화면은 목록, 필터, 상세, 상태 타임라인, Evidence, RCA, CAPA, Verification을 제공합니다. Review Queue의 승인 가능 여부는 화면 규칙이 아니라 Mock Contract의 `allowed`, `reason` 값으로 표시합니다. Agent Trace는 Jev, LangGraph, Multi-Agent 실행 흐름을 연결할 수 있는 형태로 준비합니다.

## 실행 및 검증

프론트엔드 의존성을 설치한 뒤 `frontend` 디렉터리에서 실행합니다.

```bash
npm install
npm run lint
npm run test
npm run build
```

기존 Python 프로젝트 검증은 저장소 루트에서 실행합니다.

```bash
ruff check .
pytest
```

## 제한 사항

Day 13은 Mock API Contract만 사용합니다. FastAPI, Queue/Worker, Jev, Gemini, Ollama, LangGraph, Multi-Agent, MCP를 실제로 호출하거나 구현하지 않습니다.

Gemini는 향후 공통 LLM Gateway의 기본 Provider입니다. Ollama는 로컬 개발과 대체 Provider로 유지합니다. Agent가 특정 LLM Provider에 직접 종속되지 않도록 두 Provider는 Gateway 뒤에 배치합니다.

## 다음 단계

Day 14부터 다음 순서로 실제 기능을 연결합니다.

`Domain/API -> Queue/Worker -> Jev -> LLM Gateway -> LangGraph -> Multi-Agent -> Harness/Loop -> MCP`

첫 작업은 Mock API Adapter를 실제 FastAPI Contract로 교체하는 Domain/API Vertical Slice입니다.
