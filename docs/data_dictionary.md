# 데이터 딕셔너리

## 데이터 계층

`raw`는 수집 원본을 보존하고, `interim`은 정제·표준화 중간 산출물이며, `processed`는 분석에 바로 쓰는 검증 완료 데이터다.

## Product

| 필드 | 타입 | Nullable | 설명 | 예시 | 검증 |
| --- | --- | --- | --- | --- | --- |
| product_id | string | 아니오 | 상품 식별자 | P001 | 공백 불가 |
| brand | string | 아니오 | 가상 브랜드명 | 가상푸드 | 공백 불가 |
| product_name | string | 아니오 | 상품명 | 든든 도시락 | 공백 불가 |
| category | string | 아니오 | 상품 분류 | 도시락 | 공백 불가 |
| price | float | 아니오 | 판매가(원) | 5900 | 0 이상 |
| weight_g | float | 아니오 | 중량(g) | 350 | 0 이상 |
| calories_kcal | float | 아니오 | 열량(kcal) | 520 | 0 이상 |
| protein_g | float | 아니오 | 단백질(g) | 20 | 0 이상 |
| carbohydrate_g | float | 아니오 | 탄수화물(g) | 65 | 0 이상 |
| sugar_g | float | 아니오 | 당류(g) | 8 | 0 이상 |
| fat_g | float | 아니오 | 지방(g) | 15 | 0 이상 |
| sodium_mg | float | 아니오 | 나트륨(mg) | 900 | 0 이상 |
| source | string | 아니오 | 데이터 출처 | synthetic | 공백 불가 |

## Review

| 필드 | 타입 | Nullable | 설명 | 예시 | 검증 |
| --- | --- | --- | --- | --- | --- |
| review_id | string | 아니오 | 리뷰 식별자 | R001 | 공백 불가 |
| product_id | string | 아니오 | 대상 상품 식별자 | P001 | 공백 불가 |
| rating | integer | 아니오 | 평점 | 5 | 1~5 |
| review_text | string | 아니오 | 리뷰 본문 | 맛있어요 | 공백 불가, 2자 이상 |
| review_date | date | 아니오 | 작성일 | 2026-08-01 | ISO 날짜 |
| source | string | 아니오 | 데이터 출처 | synthetic | 공백 불가 |

## 향후 엔터티

- customers
- orders
- promotions
- survey_responses
- review_embeddings
