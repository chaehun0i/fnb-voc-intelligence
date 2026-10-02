# Day 16 Incident 영속화와 Outbox

## 목적

서버 재시작 후에도 Incident와 상태 변경 기록을 유지하고, 상태 저장과 이벤트 기록이 분리되어 유실되는 문제를 막습니다.

## 구성

`PostgresIncidentRepository`는 기존 Repository Port를 구현합니다. `serviq_incidents`의 저장용 JSON은 Domain 객체와 직렬화 경계로 분리하며, 기존 Product/Review/pgvector 테이블을 변경하지 않습니다.

새 Incident는 버전 1로 저장합니다. 업데이트는 읽은 버전과 저장 버전이 같을 때만 성공합니다. 상태 변경은 같은 트랜잭션에 `serviq_outbox` 이벤트를 기록합니다. 충돌과 롤백 시 이벤트도 저장되지 않습니다.

## 실행 및 검증

```bash
export SERVIQ_DATABASE_URL=postgresql://user:password@localhost:5432/fnb_voc
python -m src.infrastructure.migrations
```

SQL 초기화는 반복 실행 가능합니다. 비밀번호는 환경 파일이나 배포 Secret에만 저장하세요. API/Compose 실행과 통합 검증은 Day 16 배포 문서에서 연결합니다.

### 실제 PostgreSQL 통합 검증

`scripts/serviq_postgres_smoke.py`는 Mock 연결 대신 실제 PostgreSQL에서 저장소 초기화 반복 실행, 생성·조회·필터, 버전 충돌, 상태 이벤트 기록과 Outbox 원자적 롤백을 확인합니다. Worker의 잠금 건너뛰기, 만료 잠금 복구, 이전 시도의 완료 기록 차단, 제한된 재시도와 `DLQ`도 함께 검증합니다.

반드시 다른 Worker나 대기 작업이 없는 전용 테스트 DB를 지정하세요. 실행 중 UUID 전용 Incident 두 건과 해당 ID만 거부하는 임시 Outbox `CHECK` 제약을 만듭니다. 종료 시 해당 제약을 해제하고 정확히 그 Incident ID에 연결된 Outbox와 Incident 행만 정리합니다. 기존 Product/Review 데이터는 수정하지 않습니다.

```powershell
$env:SERVIQ_TEST_DATABASE_URL = "postgresql://사용자:비밀번호@localhost:5432/serviq_test"
uv run python -m scripts.serviq_postgres_smoke
```

이 명령은 외부 AI나 조치 서비스를 호출하지 않습니다. 재시도 검증은 테스트 시계를 앞당기므로 실제 시간 경과를 기다리지 않습니다. CLI는 오류 시 실패 코드로 종료하며, 성공한 항목은 `[통과]`로 표시합니다.

2026년 10월 2일 전용 PostgreSQL 컨테이너의 새 테스트 DB에서 위 통합 검증을 실제로 완료했습니다. 반복 마이그레이션, Repository 저장·조회·필터·버전 충돌, 상태 이벤트, Worker 잠금·재시도·실패 보관, Outbox 실패 시 전체 롤백과 UUID 검증 데이터 정리를 모두 통과했습니다. 앞서 중단된 실행으로 대기 작업이 남은 테스트 DB는 실행 전 확인 단계에서 거부되었으며, 그 DB의 기존 행을 삭제하지 않고 새 테스트 DB로 검증했습니다.

## 제한 사항

이 저장소는 단일 운영 환경의 첫 Incident 영속화입니다. 멀티테넌트 인증·데이터 격리와 온라인 스키마 버전 업그레이드는 별도 개발 항목입니다. 운영 배포 전 인증과 데이터 접근 경계를 연결해야 합니다.

## 다음 단계

Outbox 처리, 장애 시 lease 복구, 실행 결과 감사, PostgreSQL 백업과 복구 절차를 연결합니다.
