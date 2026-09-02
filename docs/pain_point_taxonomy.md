# Day 3 Pain Point Taxonomy

## 카테고리

`quality`, `taste`, `price`, `quantity`, `packaging`, `delivery`, `freshness`, `service`, `usability`를 버전 1.0 분류체계로 제공합니다.

## 분류와 점수

리뷰 텍스트를 공백·문장부호 기준으로 정규화한 뒤 카테고리 키워드를 매칭합니다. 점수는 매칭된 키워드 수이며 동점은 카테고리 ID로 정렬합니다. 결과에는 카테고리와 근거 키워드가 포함됩니다. 매칭이 없으면 `score: 0`, 빈 categories/evidence로 안전하게 미분류됩니다.

## CLI

```bash
python -m src.analysis.classify_reviews --products tests/fixtures/sample_products.csv --reviews tests/fixtures/sample_reviews.csv --output data/processed/classification.json
```

생성 결과는 무시되는 `data/processed` 경로에만 저장합니다.

## 제한과 확장 규칙

현재 방식은 결정적 키워드 매칭이므로 문맥·동의어·부정을 완전히 이해하지 못합니다. 새 카테고리나 키워드는 `taxonomy_v1.json`과 검증 테스트를 함께 갱신하고, 분류 로직과 데이터는 분리합니다.
