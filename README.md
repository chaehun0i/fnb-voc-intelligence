# fnb-voc-intelligence

식음료 고객의 VOC 데이터를 수집·정리·분석하여 상품 개선 인사이트를 만드는 프로젝트입니다.

## 현재 아키텍처

`src/config`는 설정을, `src/data`는 모델·로더·품질 검사·PostgreSQL 저장소를,
`src/rag`는 임베딩·벡터 색인·검색을 제공합니다. `tests/fixtures`에는 결정적인
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
python -m src.data.validate_data --products tests/fixtures/sample_products.csv --reviews tests/fixtures/sample_reviews.csv
```

## 디렉터리

- `data/raw`: 원본 데이터
- `data/interim`: 중간 처리 데이터
- `data/processed`: 처리 완료 데이터
- `src`: 애플리케이션 코드
- `tests`: 테스트
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
