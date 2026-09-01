# Day 2 EDA

## 제공 분석

- 데이터셋 스키마·결측·고유값 요약
- 평점 및 리뷰 길이 분포
- 상품·카테고리별 리뷰 지표
- 저·고평점 리뷰와 평점 구간별 핵심 단어

## CLI 사용

```bash
python -m src.analysis.eda_report --products tests/fixtures/sample_products.csv --reviews tests/fixtures/sample_reviews.csv --output data/processed/eda_report.json
```

출력 JSON은 데이터셋 요약, 평점·길이 분포, 카테고리 지표, 어휘 비교를 담습니다. 생성 보고서는 `data/processed`에만 저장하며 커밋하지 않습니다.

## 다음 단계

다음 Day 3에서는 EDA 결과를 기반으로 Pain Point taxonomy를 정의합니다.
