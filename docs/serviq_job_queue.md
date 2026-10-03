# Day 18 Persistent Job과 Queue 운영 Console

## 목적

Day 17의 Tenant/RBAC·승인·감사·멱등성 계약 위에 독립 Job 실행 생명주기를 추가합니다.
기준 main은 `f901195`입니다. Drive v0.5의 Day 16 구현 스냅샷과 구분합니다.

## 구성

Outbox는 발생한 업무 이벤트의 내구성, Job은 실행 상태의 원본을 담당합니다.
`domain/jobs`는 시간대가 있는 시각, 우선순위, 시도 횟수, 잠금과 안전한 오류를 표현합니다.
`006_serviq_jobs.sql`은 기존 migration을 수정하지 않고 Job 테이블과 조회 index를 추가합니다.
조직과 Incident·부모 Job을 복합 외래 키로 연결하며 dispatch ID 중복도 DB에서 차단합니다.
저장소는 JSONB 문서와 조회용 열을 함께 저장하고 버전 충돌을 거부합니다.
기존 업무 트랜잭션 경계에 조직별 Job 저장소를 추가했습니다. 메모리 구현은 테스트용입니다.
상태는 `PENDING → RUNNING → COMPLETED`이며 실패는 `FAILED` 또는 `DLQ`로 남깁니다.
자동 재시도는 횟수와 대기 시간을 제한합니다. 운영 재시도는 원본을 보존한 새 Job을 만듭니다.
취소는 `PENDING`에만 허용하며 실행 중인 작업을 중단한 것처럼 표시하지 않습니다.

## 실행/검증

도메인 검증: `uv run --extra dev pytest backend/tests/test_job_domain.py`

## 제한 사항

현재 이 문서는 Day 18 구현 진행 기록입니다. 저장소·API·Worker·UI의 완료 여부는 구현 후 갱신합니다.
Redis와 AI/Agent Runtime은 이번 Day 범위가 아닙니다.

## 다음 단계

PostgreSQL Job 저장소와 Outbox dispatch를 연결합니다.
