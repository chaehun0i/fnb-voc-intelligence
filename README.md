# fnb-voc-intelligence

식음료 고객의 VOC 데이터를 수집·정리·분석하여 상품 개선 인사이트를 만드는 프로젝트입니다.

## 현재 아키텍처

`backend/src/config`는 설정을, `backend/src/data`는 모델·로더·품질 검사·PostgreSQL 저장소를,
`backend/src/rag`는 임베딩·벡터 색인·검색을 제공합니다. `backend/tests/fixtures`에는 결정적인
합성 샘플 데이터가 있습니다.

## 데이터 계층

- `data/raw`: 수집 원본(커밋 금지)
- `data/interim`: 정제 중간 데이터
- `data/processed`: 분석용 검증 완료 데이터

## 핵심 엔터티

- Product: 상품 정보와 영양 성분
- Review: 상품에 연결된 고객 리뷰

## 시작하기

### 처음 ServIQ를 체험한다면

기존 `.env`와 DB/volume을 보존하고 `docker compose --profile serviq up --build -d --wait api frontend worker`로 실행한 뒤 `http://localhost:8080`에 접속하세요. 현재 로컬 호환 인증은 별도 로그인 화면이나 production OIDC가 아닙니다.

**데이터 시작하기 → 매장 등록 → 샘플 데이터 또는 Excel/CSV → 컬럼 확인 → 검증/미리보기 → 확인 Import → 시작 체크리스트 → 첫 조사** 순서로 진행합니다. 처음에는 개인정보 없는 샘플과 검색어 `품질`을 권장합니다. 공식 Excel 템플릿은 화면에서 다운로드합니다. 기존 운영 설정을 자동으로 덮어쓰지 않으며, 설정이 없는 조직의 관리자만 동의 후 안전한 초기 조사 설정을 적용할 수 있습니다. 실제 조사는 Worker/PostgreSQL이 필요합니다.

지원 형식·매핑·날짜·파일 제한·샘플 의미와 실제 첫 분석 방법은 [처음 사용하는 ServIQ](docs/serviq_onboarding_import.md)를 참고하세요. 거래/재고는 관측 자료이며 POS/ERP 연결이나 외부 시스템 변경이 아닙니다.

Python 3.12 환경에서 의존성을 설치한 뒤 검증 명령을 실행합니다.

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest
```

## 검증 CLI

현재 책임별 폴더와 코드를 찾는 기준은 [프로젝트 구조](docs/serviq_structure.md)를 참고하세요.

AI Runtime은 **Decision / Intelligence / Workflow / Execution / AX**로 찾습니다. 기존 업무·보안·Checkpoint 경계를 유지한 구조 통합과 검증 결과는 [Architecture Simplification](docs/serviq_architecture_simplification.md)에 기록합니다.

```bash
python -m src.data.validate_data --products backend/tests/fixtures/sample_products.csv --reviews backend/tests/fixtures/sample_reviews.csv
```

## 디렉터리

- `data/raw`: 원본 데이터
- `data/interim`: 중간 처리 데이터
- `data/processed`: 처리 완료 데이터
- `backend/src`: Python 애플리케이션 코드
- `backend/tests`: Python 테스트
- `frontend`: React 운영 콘솔
- `db`: DB SQL 초기화 자료
- `docs`: 프로젝트 문서

## 로드맵

1. 데이터 기반 구축 (Day 1)
2. VOC 탐색 분석 및 지표 정의
3. 인사이트 리포트와 대시보드

Day 2 EDA 사용법과 분석 결과 해석은 [EDA 문서](docs/eda.md)를 참고하세요.

Day 3 키워드 기반 페인포인트 분류는 [taxonomy 문서](docs/pain_point_taxonomy.md)를 참고하세요.

Day 4 PostgreSQL 스키마와 저장소 사용법은 [PostgreSQL 문서](docs/postgresql.md)를 참고하세요.

Day 5 pgvector 색인과 의미 검색 사용법은 [Vector Search 문서](docs/vector_search.md)를 참고하세요.

Day 6 키워드·벡터 하이브리드 검색은 [Hybrid Search 문서](docs/hybrid_search.md)를 참고하세요.

Day 7 근거 중심 RAG 질의는 [RAG 문서](docs/rag.md)를 참고하세요.

Day 8 RAG 평가 지표와 실행법은 [RAG Evaluation 문서](docs/rag_evaluation.md)를 참고하세요.

Day 9 VOC 대시보드 구조와 실행법은 [Dashboard 문서](docs/dashboard.md)를 참고하세요.

Day 10 대규모·재개 가능한 벡터 색인은 [Scale-up 문서](docs/scale_up.md)를 참고하세요.

Day 11 실제 외부 데이터 수집과 적재는 [Real Data Pipeline 문서](docs/real_data_pipeline.md)를 참고하세요.

Day 12 Docker Compose 환경은 [Docker 문서](docs/docker.md)를 참고하세요.

Day 13 ServIQ v0.4.1 프론트엔드 기반과 이후 개발 방향은 [ServIQ Frontend 문서](docs/serviq_frontend.md)를 참고하세요.

Day 14 Incident Domain API는 [Incident API 문서](docs/serviq_incident_api.md)를 참고하세요.

Day 15 ServIQ 운영 콘솔의 한글 사용자 경험과 UI 구성은 [Frontend UX 문서](docs/serviq_frontend_ux.md)를 참고하세요.

Day 16 ServIQ 운영 화면·업무 흐름·영속 저장·실행과 CI/CD는 [운영 Vertical Slice 문서](docs/serviq_runtime.md)를 참고하세요.

Day 17 Tenant/RBAC·승인·감사·영속 멱등성과 실제 Review 연결은 [운영 안전 실행 계약 문서](docs/serviq_access_review.md)를 참고하세요.

Day 18 Persistent Job·독립 Worker·실제 Queue 조회와 재시도·취소는 [작업 대기열 운영 문서](docs/serviq_job_queue.md)를 참고하세요.

Day 19 실제 운영 KPI·추세·RCA/CAPA와 Tenant 범위 Dashboard는 [Dashboard Projection 문서](docs/serviq_dashboard.md)를 참고하세요.

Day 20 버전 설정·서버 안전 상한·변경 이력과 안전 복원·실제 Settings 연결은 [Control Plane 문서](docs/serviq_control_plane.md)를 참고하세요.

Day 21 외부 AI 없는 Jev 위험·라우팅 판단과 실제 Job Shadow 감사·조회는 [Decision Layer 문서](docs/serviq_jev.md)를 참고하세요.

Day 22 Provider 중립 LLM 계약·Data Policy·Gemini/Ollama 어댑터와 안전한 사용 기록은 [LLM Gateway 문서](docs/serviq_llm_gateway.md)를 참고하세요.

Day 23 단일 History 조사·AgentRun·LangGraph durable Checkpoint와 실제 실행 추적은 [History Workflow 문서](docs/serviq_langgraph_history.md)를 참고하세요.

Day 24 출처가 보존된 Evidence 정규화·결정적 충분성·근거 기반 미확정 RCA와 실제 Trace는 [Evidence/RCA Workflow 문서](docs/serviq_evidence_rca.md)를 참고하세요. Incident 상태 변경이나 CAPA/승인 자동 실행은 포함하지 않습니다.

Day 25 근거 기반 CAPA 제안·기존 Application Command·실제 Approval·LangGraph 승인 대기/재개와 Review/Trace 연결은 [CAPA/Human Approval 문서](docs/serviq_capa_approval.md)를 참고하세요. 사람의 승인은 실행 단계 대기이며 외부 Action 실행 완료가 아닙니다.

Day 26 승인 재검증·내부 실행 기록·Evidence 기반 Verification과 PASS/FAIL/INCONCLUSIVE Golden Closed Loop는 [Verification 문서](docs/serviq_verification.md)를 참고하세요. 실행은 INTERNAL_RECORD_ONLY, 검증 근거는 SIMULATED이며 외부 시스템 변경이나 실제 현장 개선 효과를 주장하지 않습니다. 자동 CLOSED도 수행하지 않습니다.

Day 27 capability-aware Registry·최소 Context Pack·History/Transaction/Inventory read-only fan-out/fan-in·부분 실패 격리·checkpoint 복구와 실제 업무 AX는 [Multi-Agent 문서](docs/serviq_multi_agent.md)를 참고하세요. 거래/재고는 합성 운영 관측 자료이며 실제 POS/ERP 연결이나 외부 write가 아닙니다. 기존 Sufficiency/RCA/승인/내부 실행/Verification 흐름을 재사용하고 Jev Shadow는 자동 실행하지 않습니다.

Day 28 제한 반복·종료·현재 정책 Harness·불변 Manifest·안전 Replay·Pause/Resume/Stop/수동 인계는 [Loop/Harness 문서](docs/serviq_loop_harness.md)를, 첫 실행·Excel Template·컬럼 매핑·확인 Import·Demo·첫 조사 체크리스트는 [온보딩 문서](docs/serviq_onboarding_import.md)를 참고하세요. MCP/LangChain 신규 Runtime과 실제 외부 write는 미구현입니다.

Day 29 versioned Tool/Prompt Registry·LLM Gateway 기반 LangChain Node composition·공식 MCP in-memory read adapter·Harness·거래/재고 Tool branch와 안전한 Tool AX는 [LangChain/MCP 문서](docs/serviq_langchain_mcp.md)를 참고하세요. Day 28 당시 미구현이던 두 Runtime의 좁은 Vertical Slice이며, public MCP endpoint·실제 POS/ERP write·모든 Node migration·Day 30 RC를 의미하지 않습니다.

Day 30 현재 MVP 단계는 **AX/AI MVP Release Candidate**입니다. Incident의 AI Brief·업무 진행·근거 범위·사람 행동·다음 행동·기존 Agent 제어, per-run RC Manifest/Golden 비교와 최소 Feedback/지표는 [AX/AI MVP RC 문서](docs/serviq_ax_mvp_rc.md)를 참고하세요. Production Ready가 아닙니다.

Day 31은 **실제 사용자 검증을 수행하고 AX friction을 측정할 수 있는 기반**입니다. 동의 기반 과업 Session·서버 상태와 결합한 Journey·선택형 RAW Feedback·표본 수/측정 가능성을 표시하는 지표는 [User Validation 가이드](docs/serviq_user_validation.md)를 참고하세요. Synthetic 검증과 실제 사용자 관찰을 별도로 집계하며, 실제 사용자 검증은 **NOT YET PERFORMED**입니다.

### 처음 체험하는 순서

실제 API 모드에서 로그인 → 매장 확인 → [샘플 또는 Excel/CSV 입력](docs/serviq_onboarding_import.md) → 시작 체크리스트의 Incident 열기 → 조사 시작 → AI Brief/근거/다음 행동 확인 → 기존 Review에서 승인/반려 → 내부 실행 기록/Verification 결과 확인 순서입니다. 승인 ≠ 실행이며 실행은 INTERNAL_RECORD_ONLY, 검증은 SIMULATED입니다. 서버 오류를 Mock으로 대체하지 않습니다. 후속은 사용자 과업 관찰과 AX friction 개선·Productionization입니다.

사용자 과업 관찰은 HTTP 모드의 **사용자 과업 검증 참여**에서 매장·과업을 선택하고 동의한 뒤 시작합니다. 기존 화면에서 스스로 판단하고 의견을 남긴 뒤 **과업 완료 확인**을 요청하세요. 서버가 실제 결정/검증 결과를 확인하며 페이지 조회만으로 완료하지 않습니다. 관리자는 Dashboard의 **사용자 검증 지표 조회**에서 매장과 사용자 관찰/Synthetic 자료를 구분해 볼 수 있습니다. 이름·원문 입력을 수집하지 않으며 자동화 smoke는 사용자 참여로 집계하지 않습니다.
