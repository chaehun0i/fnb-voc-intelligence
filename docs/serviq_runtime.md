# Day 16 ServIQ 운영 Vertical Slice

## 목적

Day 15 이후 화면 내부 정보와 서버·DB·실행·검증 경계를 실제로 연결합니다. 기존 Data Intelligence와 Streamlit은 보존하며 React는 별도 운영 콘솔로 유지합니다. Frontend-first → Contract-first → Domain/API의 다음 단계로 사람이 운영할 수 있는 결정적 업무 흐름과 영속 이벤트 처리를 마련합니다.

참고 기준은 [ServIQ 설계 폴더](https://drive.google.com/drive/folders/1xEHjDTZMWeVGDEki9z0Mgnif5ePR2Yq3)입니다. 확인 시 v0.4.1 FrontendFirst 폴더에는 문서가 없었으므로, 사용자가 지정한 v0.4.1 개발 원칙과 v0.4 세부 설계를 함께 참고했습니다. 특히 [UI/UX](https://docs.google.com/document/d/1fO-HEVyPx2zC0Yw1ChFSMcWYfJ4Cem8fLIyozdr4jMM/edit), [Domain](https://docs.google.com/document/d/1vzNjCKraLCU17BNIIkwuMu__YtZSD-1xRmeFft9x790/edit), [API Contract](https://docs.google.com/document/d/1WLd8F3uwAK5sjB6bpQsFtut8yiGPOZOcjmExoCtR4rE/edit), [Queue/Worker](https://docs.google.com/document/d/1qNyS8pcTWnmiZ71T_ApZ77XqBeoW33PF2mYFIi-9wuY/edit), [실행·배포](https://docs.google.com/document/d/1aJgtSEifZ5xz2HKWNNY5thHTjK9hTdIgHLH0YS4sbGM/edit)를 기준으로 구현 범위를 정했습니다.

## 구성

| 영역 | 실제 구현 | 남은 경계 |
| --- | --- | --- |
| 운영 화면 | 대시보드·7개 메뉴·한글 상세·검색·Radix 탭/팝업·접근성·내부 스크롤 | 운영 집계/Review/Queue/연동/Trace/설정은 Mock |
| Incident API | 생성·분류·조사·증거·RCA·CAPA·승인·수동 실행 기록·검증·종결·재조사 | 외부 조치 실행 및 사용자별 권한은 미연결 |
| Domain | 승인·증거·Verification 조건, 건너뛰기 거부, immutable 전이 | Policy Engine/Jev·예외 상태 운영 명령은 후속 |
| Repository | 메모리와 PostgreSQL, 복사 격리, 버전 충돌, 트랜잭션 | Product/Review 스키마는 기존 구현 유지 |
| Outbox Worker | 원자 기록·SKIP LOCKED·lease 복구·bounded retry·DLQ | 기본 처리기는 이벤트 검증/로그만 수행, Agent가 아님 |
| 실행·CI/CD | backend uv/FastAPI, frontend npm, DB SQL, Compose, 회귀/실DB/이미지 CI, 수동 GHCR 게시 | 외부 운영 서버 자동 배포·계정 권한은 별도 |

상세 내용은 [화면 구성](serviq_frontend_ux.md), [실행 디렉터리](serviq_structure.md), [도메인 업무 흐름](serviq_domain_workflow.md), [Incident API](serviq_incident_api.md), [영속 저장](serviq_persistence.md), [Outbox](serviq_outbox.md), [실행과 CI/CD](serviq_delivery.md)에 기록합니다. 기능별 커밋은 코드·테스트·관련 문서를 함께 포함합니다.

## 실행 및 검증

Python은 `backend/`, npm은 `frontend/`에서 실행합니다. `backend/`에 `package.json`을 추가하지 않으며 `npm install`을 실행하지 않습니다.

```bash
cd backend
uv run fastapi run
```

위 명령의 기본 바인딩은 `0.0.0.0`입니다. 로컬로 제한하려면 `--host 127.0.0.1`을 사용합니다. API 문서는 <http://localhost:8000/docs>에서 확인합니다. 기본 메모리 모드는 비어 있으므로 HTTP 화면에서 인시던트를 등록할 수 있습니다.

별도 터미널에서 다음과 같이 실행합니다.

```bash
cd frontend
npm ci
npm run dev
```

HTTP 연결은 `frontend/.env.local`의 `VITE_API_MODE=http`, `VITE_API_BASE_URL=http://localhost:8000/api/v1`로 선택합니다. 설정 후 Vite를 다시 실행합니다. PostgreSQL 연결과 Compose 실행은 위 개별 문서를 따릅니다.

저장소 루트에서는 다음을 실행합니다.

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest
```

프론트엔드에서는 `npm run lint`, `npm run test`, `npm run build`를 실행합니다. 실제 DB 검증은 별도 전용 DB의 `SERVIQ_TEST_DATABASE_URL`을 지정하고 `uv run python -m scripts.serviq_postgres_smoke`로 실행합니다. 테스트 중 만든 UUID 자료만 정리하며 다른 DB 자료는 삭제하지 않습니다.

### Day 16 검증 기록

2026년 10월 3일 로컬 검증에서 다음 결과를 확인했습니다. 단위 테스트를 skip·xfail로 바꾸거나 기존 assertion을 약화하지 않았습니다.

| 검증 | 결과 |
| --- | --- |
| 루트 `ruff check .` | 통과 |
| 루트 `pytest` | 284개 통과, 의존성 경고 1개 |
| `backend/`의 `uv sync --locked` | 통과 |
| `backend/`의 `uv run fastapi run` | 서버 시작, health 및 `/docs` HTTP 200 |
| `frontend/`의 `npm ci` | lockfile 설치 완료, 취약점 0건 |
| `npm run lint`, `npm run test` | 통과, 프론트 테스트 63개 |
| `npm run build` | production build 및 반복 빌드 확인 |
| 실제 PostgreSQL smoke | 버전 충돌·원자적 Outbox·lease·이전 ACK 거부·재시도·DLQ 통과 |
| 실제 Compose HTTP smoke | nginx 프록시의 생성부터 종결까지 수동 흐름·Permission·오류 계약 통과 |
| 실제 Worker 처리 | 수동 흐름에서 생성한 상태 이벤트 9건 완료 |
| API 재시작 | 동일 Incident의 `CLOSED`, `version=11`, 증거 및 Verification PASS 유지 |
| 브라우저 화면 확인 | 팝업·7개 상세 탭·운영 메뉴·본문/선택 목록 스크롤 및 콘솔 오류 없음 확인 |

로컬 `npm ci`의 첫 실행은 Vite가 사용 중인 Tailwind 바이너리 잠금으로 `EPERM`이 발생했습니다. 해당 개발 서버를 중지한 뒤 재설치하여 해결했습니다. 로컬 Node.js `24.12.0`에는 일부 테스트 의존성의 `EBADENGINE` 경고가 있었지만 위 검증은 실제로 통과했습니다. 새 환경은 Node.js 24 LTS의 `24.15.0` 이상을 사용합니다. Python 경고는 Starlette TestClient의 httpx 사용 안내이며 실패를 숨기기 위해 필터링하지 않았습니다.

Windows의 출력 리다이렉션에서 FastAPI 도움말의 이모지를 CP949로 출력하면 인코딩 오류가 날 수 있습니다. 실제 터미널의 서버 실행은 정상 확인했고, 자동 검증 셸에서는 `PYTHONIOENCODING=utf-8`을 지정해 도움말도 확인했습니다. GitHub CI는 별도로 PR에서 실행되며, 로컬 성공을 원격 CI 성공이나 GHCR 게시 완료로 기록하지 않습니다.

## 제한 사항

이 단계는 전체 v0.4 제품이 완료됐다는 선언이 아닙니다. 로그인/RBAC·테넌트 격리·승인자 감사·영속 요청 멱등성·운영 백업/복원을 추가하기 전에는 API를 인터넷에 직접 공개하지 않습니다. `execute`는 사람이 이미 수행한 조치의 기록이며 외부 재고·설비를 자동 변경하지 않습니다.

Jev·Gemini/Ollama Runtime·LangGraph·Multi-Agent·Harness·MCP는 아직 구현되지 않았습니다. Agent는 특정 Provider SDK가 아니라 공통 LLM Gateway 뒤의 Gemini(기본)·Ollama(로컬/대체)를 사용하도록 이후 연결합니다. 미리보기 화면과 실제 Outbox Worker 상태는 아직 같은 조회 API로 연결되지 않습니다.

## 다음 단계

인증·테넌트·승인 감사·명령 멱등성을 먼저 보강하고 실제 Review/Queue/운영 집계 Query를 연결합니다. 그다음 Jev → LLM Gateway → LangGraph → Multi-Agent → Harness/Loop → MCP를 작은 Vertical Slice로 구현합니다. 배포는 CI를 통과한 이미지와 보호된 환경 승인으로 확장하며 자동 merge하지 않습니다.
