# Day 14 Incident Domain API

## 목적

Day 13 Mock Incident 화면 뒤에 deterministic Domain/Application/FastAPI Vertical Slice를 추가합니다. 프론트엔드에서 정한 계약을 유지하면서, 인시던트 조회와 사람의 수동 운영 명령을 실제 HTTP로 연결합니다.

## 구성

Domain은 상태 전이 규칙과 업무 모델을, Application은 Query/Command의 실행과 저장을 담당합니다. Infrastructure는 Repository Port의 저장 구현을, API는 입력 검증과 HTTP 응답을 담당합니다. Domain은 FastAPI 또는 LLM에 의존하지 않습니다.

상태를 마음대로 바꾸는 `PATCH` 대신 `triage`, `investigate`, `approve`, `verify`처럼 목적이 분명한 명령을 제공합니다. 성공한 응답은 기존 프론트엔드가 사용하던 snake_case `Incident` 계약을 유지하며, 증거·원인 후보·조치·검증·타임라인을 함께 반환합니다.

| 메서드 | Endpoint | 역할 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | HTTP 서비스 상태 확인 |
| `GET` | `/api/v1/incidents` | 목록과 `status`, `severity`, `store` 필터 |
| `POST` | `/api/v1/incidents` | 새 인시던트 접수 |
| `GET` | `/api/v1/incidents/{id}` | 전체 상세 조회 |
| `GET` | `/api/v1/incidents/{id}/workspace` | 서버가 판단한 동작 권한과 사유 |
| `POST` | `/api/v1/incidents/{id}/triage` | 심각도 초기 분류 |
| `POST` | `/api/v1/incidents/{id}/investigate` | 조사 시작 또는 재조사 |
| `POST` | `/api/v1/incidents/{id}/evidence` | 조사 증거 등록 |
| `POST` | `/api/v1/incidents/{id}/rca` | 근거를 참조한 원인 후보 확정 |
| `POST` | `/api/v1/incidents/{id}/actions` | 시정·예방 조치안 제안 |
| `POST` | `/api/v1/incidents/{id}/request-approval` | 사람의 승인 요청 |
| `POST` | `/api/v1/incidents/{id}/approve` | 조치 승인 |
| `POST` | `/api/v1/incidents/{id}/reject` | 조치 반려 후 제안 단계로 복귀 |
| `POST` | `/api/v1/incidents/{id}/execute` | 수동 실행 기록과 검증 단계 진입 |
| `POST` | `/api/v1/incidents/{id}/verify` | 검증 결과 등록 |
| `POST` | `/api/v1/incidents/{id}/close` | 해결 확인 후 종료 |
| `POST` | `/api/v1/incidents/{id}/reopen` | 해결 이후 재발 사유로 재조사 |

명령은 선택적으로 `expected_version`을 받아 오래된 화면에서 덮어쓰는 요청을 거절합니다. 저장소도 읽은 버전과 현재 버전을 비교하고, 성공할 때만 버전을 증가시킵니다. 동작 가능 여부는 서버의 `allowed`, `reason` 계약을 표시하며, React에서 상태 전이 규칙을 만들지 않습니다.

입력 오류는 `VALIDATION_ERROR`(422), 없는 인시던트는 `NOT_FOUND`(404), 업무 조건 위반은 `DOMAIN_RULE_VIOLATION`(409), 버전 충돌은 `CONFLICT`(409)로 구분합니다. 응답 예시는 다음과 같습니다.

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "최신 정보를 다시 불러와 주세요.",
    "details": []
  },
  "request_id": "incident-request-001"
}
```

모든 HTTP 응답에는 `X-Request-ID`가 있습니다. 도메인 예외의 내부 메시지나 잘못 입력한 전체 요청 본문은 외부 오류 응답에 그대로 노출하지 않습니다.

## 실행 및 검증

API 전용 실행 폴더에서 시작합니다.

```bash
cd backend
uv run fastapi run
```

개발용 자동 재시작은 `uv run fastapi dev`를 사용합니다. 로컬 접근만 허용하려면 `--host 127.0.0.1`을 지정합니다. 기존 저장소 루트의 실행 방법도 유지합니다.

```bash
uv run uvicorn src.api.app:app --reload --host 127.0.0.1 --port 8000
```

Frontend의 `.env.local`에 연결 모드를 지정합니다.

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

```bash
cd frontend
npm ci
npm run dev
```

기존 Mock 화면을 확인하려면 `VITE_API_MODE=mock`을 사용합니다. HTTP 개발 CORS는 `http://localhost:5173`, `http://127.0.0.1:5173`만 허용합니다. 배포에서는 같은 출처의 프록시 경로를 사용하는 구성이 적합합니다.

기본 메모리 앱은 빈 저장소로 시작합니다. 개발 예시는 `SERVIQ_SEED_DEMO=true` 또는 테스트의 `create_app(seed_demo=True)`로 명시적으로 활성화합니다. 영속 저장은 `SERVIQ_REPOSITORY=postgres`, `SERVIQ_DATABASE_URL`로 선택하고 스키마를 먼저 준비합니다. DB 관련 배포/SQL 파일은 `db/` 경로에서 관리합니다. 테스트는 저장소·시계·ID 생성기를 주입하므로 외부 네트워크나 현재 날짜에 의존하지 않습니다.

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest
uv run --extra dev pytest backend/tests/test_api_app.py backend/tests/test_incident_domain.py backend/tests/test_incident_application.py
```

Frontend 디렉터리에서는 `npm run lint`, `npm run test`, `npm run build`로 확인합니다. 상세한 수동 업무 흐름은 [도메인 업무 흐름 문서](serviq_domain_workflow.md)를 참고하세요.

## 제한 사항

Day 14의 첫 구현은 InMemory Repository를 사용했습니다. 메모리 구현은 재시작하면 데이터가 사라지며 여러 프로세스 간 데이터를 공유하지 않습니다. 영속 저장 및 운영 구성은 해당 후속 문서와 설정을 함께 확인해야 합니다.

수동 `execute`는 외부 재고·거래·발주 시스템을 변경하지 않고 실행 사실과 상태만 기록합니다. 이번 Domain/Application/API 계층은 사람의 명령을 결정적으로 검증하는 기반입니다. Jev, Gemini/Ollama Runtime, LangGraph, Multi-Agent, MCP는 이 계층의 필수 의존성이 아닙니다.

사용자 인증과 역할 기반 권한은 아직 연결하지 않았으므로 인터넷에 직접 노출하는 운영 서비스로 사용하지 않습니다. 여기서 반환하는 Permission은 현재 상태의 업무 동작 가능 여부이며, 사용자 신원에 대한 접근 권한 검사가 아닙니다. 영속적인 요청 멱등 키와 승인자 감사 기록도 후속 구현 대상입니다.

## 다음 단계

영속 Repository와 Outbox에 동일한 Port와 버전 충돌 계약을 적용하고, 인증·승인자 감사·명령 멱등성을 보강합니다. 이후 Queue/Worker, Jev, LLM Gateway, LangGraph, Multi-Agent, Harness/Loop, MCP를 순서대로 연결합니다.
