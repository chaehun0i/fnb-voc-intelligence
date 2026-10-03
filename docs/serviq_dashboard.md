# Day 19 실제 Dashboard Projection

## 목적

Day 18 이후 실제 Incident·Approval·Job 원본을 읽는 운영 Dashboard를 연결합니다. 최신 정본은 Drive ServIQ v0.5이며 Day 16 구현 스냅샷 대신 현재 main의 Day 17~18 코드를 대조합니다. Drive 원문은 수정하지 않습니다.

## 구성

Frontend-first 계약은 `DashboardSnapshot`과 `api/dashboard`입니다. `as_of`, `window=7d`, UTC 날짜 추세, 명시적 KPI·RCA·CAPA를 사용합니다. Integration Health는 실제 원본이 없어 NOT_IMPLEMENTED로 구분합니다. 초기 계약 단계이며 서버 구현은 후속 커밋에서 연결합니다.

## 실행/검증

Frontend의 기존 lint/test/build 명령으로 계약 호환성을 검증합니다. 최종 실제 결과는 Day 마감 때 기록합니다.

## 제한 사항

Mock은 예시일 뿐 실제 운영 집계가 아닙니다. Redis·Agent·LLM·별도 projection DB를 추가하지 않습니다.

## 다음 단계

Tenant-safe Query → PostgreSQL 집계 → API → HTTP Adapter → 실제 smoke 순으로 연결합니다.
