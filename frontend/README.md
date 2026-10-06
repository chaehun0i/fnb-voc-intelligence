# ServIQ 프론트엔드

## 목적

ServIQ의 운영 콘솔입니다. Day 13 v0.4.1 기반을 유지하며 현재 운영 안전 설계 기준은 v0.6입니다. Frontend-first → Contract-first → Domain/API 순서로 개발하며 기존 Streamlit 분석 대시보드를 대체하지 않습니다.

## 구성

- `src/shared/api.ts`: 공통 HTTP 연결·인증·명령 키 설정입니다.
- `src/shared/fixtures.ts`, `mockApi.ts`: 화면 검토용 데이터와 세션 내 Mock Action을 제공합니다.
- `src/features/incidents/api.ts`: 같은 Incident Contract를 사용하는 Mock/HTTP 경계입니다.
- `src/features/reviews/api.ts`: 실제 Approval 조회·승인·반려와 기존 Mock 경로입니다.
- `src/features/operations/api.ts`: 실제 Job 조회·재시도·취소와 Mock 경로입니다.
- `src/features/dashboard/api.ts`: 서버 Snapshot의 KPI·UTC 추세와 Mock 경로입니다.
- `src/features/settings/api.ts`: 서버 Config Version·해석값·이력·변경·복원입니다.
- `src/features/ai/`: Jev Shadow API·AgentRun 응답 decoder·실제 Evidence/RCA/CAPA/Verification Trace입니다.
- `src/features/`: 대시보드, 인시던트, 검토, 실행 추적, 연동, 대기열, 운영 설정입니다.
- Tailwind CSS, Radix Select/Dialog/Tabs, Framer Motion, lucide-react로 화면·키보드 조작·상태를 구성합니다.
- 인시던트 팝업은 진행 이력·증거·RCA·CAPA·담당 작업·검증·추적의 7개 탭과 서버 Permission에 따른 운영 명령을 제공합니다.
- 메뉴별 `#/incidents`, `#/reviews` 등의 주소를 유지해 새로고침·뒤로가기와 화면 공유를 지원합니다. `#/incidents?incident=inc-1`로 상세를 직접 열 수 있습니다. 페이지 코드는 필요할 때 지연 로딩합니다.

## 실행 및 검증

이 디렉터리에서 실행합니다. 테스트 도구의 지원 범위에 맞춰 Node.js 24 LTS의 `24.15.0` 이상을 사용합니다. 이전 24.x 버전에서는 `npm ci`에 `EBADENGINE` 경고가 나올 수 있습니다.

```bash
npm ci
npm run dev
npm run lint
npm run test
npm run build
```

Windows에서 `npm ci`가 Tailwind 바이너리의 `EPERM` 오류로 실패하면 이 저장소의 Vite 개발 서버를 먼저 종료하고 재실행합니다. 실행 중인 개발 서버의 파일 잠금은 코드 빌드 실패와 구분합니다. 설치가 끝난 뒤 `npm run dev`로 서버를 다시 실행합니다.

`.env.example`을 `.env.local`로 복사하면 기본 Mock 모드로 실행합니다. 실제 API는 `backend/`에서 `uv run fastapi run`으로 시작한 뒤 다음과 같이 설정하고 Vite를 재시작합니다.

```dotenv
VITE_API_MODE=http
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_LOCAL_AUTH_TOKEN=local-reviewer-demo
```

HTTP 모드에서는 Incident 접수·조회·조사·증거/RCA/CAPA 등록·승인·수동 실행 기록·검증·종결을 API에 요청합니다. 화면은 다음 상태를 계산하지 않으며 서버가 반환한 `workspace.commands`의 `allowed`, `reason`을 표시합니다. 데이터 버전을 함께 전송해 충돌을 감지합니다.

Review도 HTTP 모드에서는 실제 서버의 목록·상세·승인·반려를 사용합니다. 승인과 반려 모두 사유와 Approval 버전을 보내고, 같은 내용의 네트워크 재시도에는 같은 Idempotency-Key를 재사용합니다. 제출 중 중복 클릭을 차단하고 서버의 permission·비활성 사유를 표시합니다. 승인해도 외부 조치는 자동 실행되지 않습니다. 수정·추가 증거 요청은 HTTP에서 미지원 사유를 표시하며 Mock Action은 유지합니다.

`VITE_LOCAL_AUTH_TOKEN`은 개발 모드에서만 전달하는 서버 등록 계정의 예시 토큰입니다. 실제 Backend 계정 매핑과 Tenant/RBAC 설정은 [Day 17 문서](../docs/serviq_access_review.md)를 따르세요. 역할·조직을 브라우저 헤더로 지정하지 않습니다. VITE 설정은 브라우저에 공개되므로 운영 비밀이나 OIDC client secret을 넣지 마세요. 실제 로그인과 운영 토큰 전달 경로는 아직 없습니다. 개발 계정을 바꾸면 Vite를 재시작합니다.

API Adapter는 조회뿐 아니라 등록·명령 응답의 필수 필드, 날짜, 증거·작업 목록, Permission 형식도 확인합니다. 잘못된 응답은 화면에 전달하지 않고 `CONTRACT_ERROR`로 안내합니다. 연결 실패는 `NETWORK_ERROR`, 입력 오류는 `VALIDATION_ERROR` 등 안정적인 오류 코드로 구분하며, 서버의 요청 ID가 있으면 안내에 함께 표시합니다.

다른 담당자가 먼저 수정해 `CONFLICT`가 발생하면 운영 명령을 자동으로 재실행하지 않습니다. 팝업의 `최신 정보 다시 불러오기`로 현재 상태와 Permission을 확인한 후 다시 요청하세요. Mock 모드에서는 실제 등록·운영 명령이 비활성화되며, 화면에 보이는 예시 상태로 업무 규칙을 대신 판단하지 않습니다.

Queue도 HTTP 모드에서는 실제 Job 목록과 상세 팝업을 사용합니다. 실행 시각, 시도 횟수, 오류, 재시도 원본과 서버 Permission을 표시합니다. 재시도·취소에는 사유와 Job 버전을 보내며 같은 네트워크 재시도에는 같은 Idempotency-Key를 사용합니다. 실행 중인 작업을 실제로 중단할 수 없는 경우 취소 완료로 표시하지 않습니다. 목록은 최대 100건이며 자세한 실행·안전 계약은 [Day 18 문서](../docs/serviq_job_queue.md)를 참고하세요.

## 제한 사항

Settings HTTP 모드는 실제 current/effective/source/서버 상한과 Config Version 이력을 표시합니다. 전체 설정·현재 버전·필수 사유를 보내며 변경·복원은 서버 HQ_ADMIN permission을 따릅니다. 같은 입력의 네트워크 재시도에는 같은 Idempotency-Key를 사용하고 이중 제출을 막습니다. 복원도 새 버전이며 409 VERSION_CONFLICT에서는 최신 설정을 다시 불러옵니다. HTTP 실패에 Mock을 반환하지 않습니다. 설정 저장과 Jev/LLM/Agent·Worker 정책 적용은 구분하며 Runtime 미연결을 표시합니다. 자세한 계약은 [Day 20 문서](../docs/serviq_control_plane.md)를 참고하세요.

Dashboard HTTP 모드는 `GET /api/v1/dashboard?window=7d` 한 응답으로 실제 KPI·추세·RCA·CAPA를 표시합니다. `as_of`는 서버 정보 기준 시각이며 추세 날짜는 UTC입니다. 브라우저에서 Incident/Review/Queue를 합산하지 않고 실패 시 예시로 대체하지 않습니다. 연동 상태는 실제 원본이 없어 준비 중으로 구분합니다. KPI 계산 규칙과 Tenant/store 범위는 [Day 19 문서](../docs/serviq_dashboard.md)를 참고하세요.

기본 Mock 모드의 자료는 새로고침하면 초기화됩니다. HTTP 모드에서는 Incident·Review·Queue·Dashboard·Settings와 단일 History 실행 추적이 실제 API를 사용하지만 연동은 여전히 Mock입니다. 예시 자료와 실제 자료를 혼동하지 않도록 안내를 구분합니다. 날짜가 없는 검증은 `기록 없음`으로 표시합니다. PostgreSQL 영속 기록은 Backend의 PostgreSQL 모드에서만 보장합니다.

Incident 상세의 실행 추적 탭에는 실제 Jev Shadow 판단 이력이 별도로 표시됩니다. 설정의 Jev 사용 이후 처리한 Job에서만 생성되며 후보·근거·Config/ruleset 버전을 확인할 수 있습니다. 판단은 실행 경로를 변경하지 않고 기존 Agent Trace 예시는 분리합니다. HTTP 실패를 Mock으로 대체하지 않습니다. 자세한 범위는 [Day 21 문서](../docs/serviq_jev.md)를 참고하세요.

Day 22에서 Backend의 공통 LLM Gateway와 Gemini/Ollama 어댑터가 추가됐습니다. Settings는 versioned Provider 허용·모델 mapping·fallback 상태를 보존하고 표시합니다. HTTP 실패를 Mock으로 대체하지 않습니다. Jev Shadow가 자동으로 외부 모델을 호출하지 않으며 실제 모델도 이번 검증에서는 호출하지 않았습니다. 자세한 계약은 [LLM Gateway 문서](../docs/serviq_llm_gateway.md)를 참고하세요.

Day 23 실행 추적 페이지와 Incident 상세 탭은 실제 History AgentRun을 표시합니다. 과거 VOC 출처, 근거 공백, 실행 상태·단계·지연, Jev/Config/Job 원본과 토큰·비용을 확인하고 새로고침할 수 있습니다. HTTP 실패를 Demo Multi-Agent로 대체하지 않습니다. 조사는 서버 Application에서 명시적으로 등록한 History Job만 실행하며 화면에 임의 실행 버튼을 추가하지 않았습니다. 자세한 복구·보안 경계는 [History Workflow 문서](../docs/serviq_langgraph_history.md)를 참고하세요.

Day 24 실제 HTTP Trace에는 정규화 Evidence, 검색 경로·출처 시각, 충분성/상충 판정과 미확정 RCA 후보가 추가됐습니다. 지지/반대 근거 버튼을 누르면 해당 출처가 펼쳐집니다. 브라우저는 충분성이나 RCA를 계산하지 않으며 HTTP 실패 시 Mock으로 대체하지 않습니다. 기존 `history-v1` 실행은 판정 이전 버전으로 구분합니다. CAPA/Approval 자동 생성·Verification·Multi-Agent·Harness/MCP는 미구현입니다. [Evidence/RCA 문서](../docs/serviq_evidence_rca.md)를 참고하세요.

## 다음 단계

단일 History 조사와 실제 Trace까지 연결했습니다. Day 24는 Evidence Fan-in/Sufficiency/RCA Draft를 이어가며 Day 30 MVP까지 승인·검증·Golden Workflow를 우선합니다. 기존 서버 Permission·Tenant/store·Audit·멱등성·Config 안전 상한을 재사용합니다. Multi-Agent 종류·Harness/MCP 개수는 최소화하고 OIDC/SSO·Integration/SyncJob는 별도 완료 기준으로 추적합니다. 실행·배포는 [배포 문서](../docs/serviq_delivery.md), 구조는 [실행 구조 문서](../docs/serviq_structure.md)를 참고하세요.
