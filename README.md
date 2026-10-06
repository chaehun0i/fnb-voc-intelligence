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
