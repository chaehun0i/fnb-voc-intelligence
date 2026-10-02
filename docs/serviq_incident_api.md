# Day 14 Incident Domain API

## 목적

Day 13 Mock Incident 화면 뒤에 deterministic Domain/Application/FastAPI Vertical Slice를 추가합니다.

## 구성

Domain은 상태 전이 규칙, Application은 Query/Command, Infrastructure는 InMemory Repository, API는 `/api/v1/incidents` 계약을 담당합니다.

## 실행 및 검증

`uv run uvicorn src.api.app:app --reload`로 API를 실행합니다. Frontend는 `VITE_API_MODE=http`, `VITE_API_BASE_URL=http://localhost:8000/api/v1`로 연결합니다.

## 제한 사항

PostgreSQL Incident persistence, Outbox, Redis/Queue/Worker, Jev, Gemini/Ollama Runtime, LangGraph, Multi-Agent, MCP는 구현하지 않습니다.

## 다음 단계

Day 15에서 실제 persistence와 Queue/Worker를 검토합니다.
