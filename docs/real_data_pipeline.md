# Day 11: 실제 데이터 파이프라인

외부 CSV, JSON, JSONL 상품·리뷰 파일은 소스 어댑터를 통해 원시 레코드로 읽고, 명시적
열 매핑으로 기존 `Product`·`Review` 모델로 검증합니다. 잘못된 행은 행 번호와 함께
보고되며 정상 행의 수집은 계속할 수 있습니다.

## CLI

```bash
ingest-data --source-type jsonl --path data/raw/reviews.jsonl \
  --source partner-a --mapping '{"review_id":"id"}' --dry-run --limit 100
```

`--source-type`은 `csv`, `json`, `jsonl`을 지원하며, `--mapping`은 외부 열 이름을
도메인 필드에 연결하는 JSON 객체입니다. `--dry-run`은 파일을 읽고 요약하지만 DB에는
쓰기 전에 사용할 수 있습니다.

## 감사성과 안전성

수집 실행은 소스, 시작/완료 시간, 입력·수락·거부·중복 수 및 소스 메타데이터를 이력으로
남길 수 있습니다. 중복 키는 정규화된 source/external ID 또는 안정적인 콘텐츠 키를 사용합니다.
적재는 상품을 먼저 검증·저장하고 리뷰 FK를 검사합니다.

원본 데이터는 `data/raw`에만 두며 개인정보, 비밀 정보, 대용량 원본 파일은 절대 커밋하지
않습니다. 분산 실행 환경에서는 단일 로컬 체크포인트와 DB 연결 한도를 별도로 운영해야 합니다.
