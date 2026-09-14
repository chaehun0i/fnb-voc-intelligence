# Day 10: 대규모 벡터 색인

대규모 리뷰 색인은 입력을 안정적인 순서의 작은 배치로 나누고, 기존 콘텐츠 해시를
통해 바뀌지 않은 리뷰를 건너뜁니다. 리뷰와 분류 결과는 파라미터화된 일괄 INSERT로
저장하며 충돌 시 무시해 재실행해도 중복을 만들지 않습니다.

## 실행

PostgreSQL 및 임베딩 설정을 준비한 뒤 다음 명령으로 실행합니다.

```bash
scale-index --batch-size 100 --workers 2 --retries 3 --resume --limit 10000
```

`--batch-size`, `--workers`, `--retries`, `--resume`, `--limit`은 모두 검증된 작업
설정으로 변환됩니다. 현재 CLI는 진행/최종 JSON에 `processed`, `succeeded`, `skipped`,
`failed`, `elapsed_seconds`, `throughput_per_second`을 출력합니다.

## 실행 특성

- 동시 작업은 워커 수만큼만 제출하며, 결과는 입력 순서에 맞춥니다.
- `TransientJobError`만 지수 백오프로 재시도합니다. 검증 오류와 영구 오류는 즉시
  전달됩니다.
- 체크포인트는 완료 배치와 카운터를 JSON으로 저장할 수 있고, 재개 시 완료 배치를
  다시 처리하지 않습니다.
- 벤치마크는 외부 서비스나 원본 데이터 없이 결정적인 ID를 사용합니다.

```bash
python -m src.rag.benchmark --count 1000 --batch-size 100
```

## 운영상 한계

동시성은 제공자 및 PostgreSQL 연결 한도에 맞춰 보수적으로 설정해야 합니다. 체크포인트는
단일 실행자용 로컬 파일이므로, 여러 프로세스가 같은 파일을 공유하는 분산 잠금은 제공하지
않습니다. 실제 처리량은 임베딩 제공자 지연과 데이터베이스 성능에 따라 달라집니다.
