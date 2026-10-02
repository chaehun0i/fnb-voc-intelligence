# ServIQ 프론트엔드

## 목적

ServIQ v0.4.1의 운영 콘솔입니다. Frontend-first → Contract-first → Domain/API 순서로 개발하며 기존 Streamlit 분석 대시보드를 대체하지 않습니다.

## 구성

- `src/api/fixtures.ts`, `mockApi.ts`: 화면 검토용 데이터와 세션 내 Mock Action을 제공합니다.
- `src/api/incidents/`: 같은 Incident Contract를 사용하는 Mock/HTTP 경계입니다.
- `src/features/`: 대시보드, 인시던트, 검토, 실행 추적, 연동, 대기열, 운영 설정입니다.
- Tailwind CSS, Radix Select/Dialog/Tabs, Framer Motion, lucide-react로 화면·키보드 조작·상태를 구성합니다.
- 인시던트 팝업은 진행 이력·증거·RCA·CAPA·담당 작업·검증·추적의 7개 탭과 서버 Permission에 따른 운영 명령을 제공합니다.
- 메뉴별 `#/incidents`, `#/reviews` 등의 주소를 유지해 새로고침·뒤로가기와 화면 공유를 지원합니다. `#/incidents?incident=inc-1`로 상세를 직접 열 수 있습니다. 페이지 코드는 필요할 때 지연 로딩합니다.

## 실행 및 검증

이 디렉터리에서 실행합니다. Node.js 24 LTS를 사용합니다.

```bash
npm ci
npm run dev
npm run lint
npm run test
npm run build
```

`.env.example`을 `.env.local`로 복사하면 기본 Mock 모드로 실행합니다. 실제 API는 `backend/`에서 `uv run fastapi run`으로 시작한 뒤 다음과 같이 설정하고 Vite를 재시작합니다.

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

HTTP 모드에서는 Incident 접수·조회·조사·증거/RCA/CAPA 등록·승인·수동 실행 기록·검증·종결을 API에 요청합니다. 화면은 다음 상태를 계산하지 않으며 서버가 반환한 `workspace.commands`의 `allowed`, `reason`을 표시합니다. 데이터 버전을 함께 전송해 충돌을 감지합니다.

API Adapter는 조회뿐 아니라 등록·명령 응답의 필수 필드, 날짜, 증거·작업 목록, Permission 형식도 확인합니다. 잘못된 응답은 화면에 전달하지 않고 `CONTRACT_ERROR`로 안내합니다. 연결 실패는 `NETWORK_ERROR`, 입력 오류는 `VALIDATION_ERROR` 등 안정적인 오류 코드로 구분하며, 서버의 요청 ID가 있으면 안내에 함께 표시합니다.

다른 담당자가 먼저 수정해 `CONFLICT`가 발생하면 운영 명령을 자동으로 재실행하지 않습니다. 팝업의 `최신 정보 다시 불러오기`로 현재 상태와 Permission을 확인한 후 다시 요청하세요. Mock 모드에서는 실제 등록·운영 명령이 비활성화되며, 화면에 보이는 예시 상태로 업무 규칙을 대신 판단하지 않습니다.

## 제한 사항

검토 대기함·연동·대기열·Agent Trace·설정 변경은 Mock입니다. 새로고침하면 초기화되고 실제 Worker/API 운영 상태와 연결되지 않습니다. HTTP Incident와 예시 집계를 혼동하지 않도록 미리보기 안내를 표시합니다. 날짜가 없는 검증은 `기록 없음`으로 표시합니다.

Jev·Gemini/Ollama Runtime·LangGraph·Multi-Agent·MCP는 아직 호출하지 않습니다. 향후 Agent는 Provider에 직접 의존하지 않고 공통 LLM Gateway 뒤의 Gemini(기본), Ollama(로컬·대체)를 사용합니다.

## 다음 단계

영속 Incident/Outbox 위에 인증·승인자 감사·멱등성과 실제 운영 Query를 추가하고, 이후 Jev → LLM Gateway → LangGraph → Multi-Agent → Harness/Loop → MCP 순서로 연결합니다. 실행·배포는 [배포 문서](../docs/serviq_delivery.md), 구조는 [실행 구조 문서](../docs/serviq_structure.md)를 참고하세요.
