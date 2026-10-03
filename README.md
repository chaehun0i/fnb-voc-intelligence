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
