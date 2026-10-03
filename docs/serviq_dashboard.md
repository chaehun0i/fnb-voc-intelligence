# Day 19 실제 Dashboard Projection

## 목적

Day 18 이후 실제 Incident·Approval·Job 원본을 읽는 운영 Dashboard를 연결합니다. 최신 정본은 Drive ServIQ v0.5이며 Day 16 구현 스냅샷 대신 현재 main의 Day 17~18 코드를 대조합니다. Drive 원문은 수정하지 않습니다.

## 구성

Frontend-first 계약은 `DashboardSnapshot`과 `api/dashboard`입니다. `as_of`, `window=7d`, UTC 날짜 추세, 명시적 KPI·RCA·CAPA를 사용합니다. Integration Health는 실제 원본이 없어 NOT_IMPLEMENTED로 구분합니다. 초기 계약 단계이며 서버 구현은 후속 커밋에서 연결합니다.

## 실행/검증

Frontend의 기존 lint/test/build 명령으로 계약 호환성을 검증합니다. 최종 실제 결과는 Day 마감 때 기록합니다.

## 제한 사항

RCA에 category 필드가 없으므로 실제 root_cause_candidates 개수를 ‘미분류’로 반환합니다. 후보가 없으면 빈 분포입니다. CAPA는 모든 범위 내 Incident의 실제 corrective_actions를 PROPOSED/APPROVED/EXECUTED별로 세며 빈 상태는 각각 0입니다. LLM 분류나 과거 fixture label을 실제 집계에 사용하지 않습니다.

Approval은 원본 PENDING 기록을 Incident의 조직·매장과 연결해 집계합니다. Job은 FAILED와 DLQ를 분리하고 Queue Depth는 실행 가능 시각과 무관한 PENDING 전체입니다. RUNNING은 별도 지표이며 COMPLETED/CANCELLED는 대기 수에서 제외합니다. 모든 count는 100건 목록 제한과 무관한 전체 원본 집계입니다.

Incident KPI는 현재 상태에서 RESOLVED/CLOSED를 제외한 열린 사건과 그중 CRITICAL을 집계합니다. UTC 오늘을 포함한 7개 날짜의 생성 및 마지막 RESOLVED 기록을 각각 사건당 한 번 계산합니다. KPI는 기간 내 생성에 제한하지 않고 현재 원본 전체를 사용합니다. SQL은 Tenant/store 범위를 적용한 읽기 전용 repeatable-read snapshot이며 원본 테이블을 복제하지 않습니다.

Mock은 예시일 뿐 실제 운영 집계가 아닙니다. Redis·Agent·LLM·별도 projection DB를 추가하지 않습니다.

## 다음 단계

Tenant-safe Query → PostgreSQL 집계 → API → HTTP Adapter → 실제 smoke 순으로 연결합니다.
