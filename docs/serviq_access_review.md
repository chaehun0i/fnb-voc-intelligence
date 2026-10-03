# Day 17 Tenant RBAC와 Review 실행 계약

## 목적

Day 16의 Incident 업무 흐름에 요청자·조직·권한·승인·감사·멱등성 경계를 연결합니다. 기준은 Google Drive v0.5의 05·14·24·28·30 문서입니다. 기존 Data Intelligence와 Streamlit은 보존합니다.

## 구성

`Principal`은 요청자·조직·역할·매장 범위·인증 출처를 표현하고 `IdentityProvider` Port에서 전달합니다. `LocalIdentityProvider`는 서버에 설정한 계정만 반환하며 브라우저의 조직·역할 헤더를 신뢰하지 않습니다.

Incident HTTP 경로는 조직에 고정된 Repository를 사용합니다. 다른 조직의 ID는 존재 여부를 노출하지 않는 404, 같은 조직 내 역할·매장 권한 부족은 403으로 구분합니다. 조회·운영·검토·관리 역할은 중앙 Authorization에서 판정하며 Reviewer는 조사 명령을 실행할 수 없습니다. `002_tenant_security.sql`은 기존 자료를 `legacy-local` 조직으로 보존합니다.

## 실행 및 검증

Audit은 승인과 별도인 추기 전용 기록입니다. 보호된 명령의 성공 기록은 업무 변경과 같은 트랜잭션에서 저장하고, 인증된 요청자의 권한 거부는 업무 롤백 뒤 DENIED로 기록합니다. 요청 본문·토큰·비밀은 저장하지 않습니다. PostgreSQL trigger는 기존 감사 기록의 UPDATE/DELETE를 거부합니다.

승인 요청은 조치 목록 digest·위험도·요청자·기한을 별도 Approval에 저장합니다. 결정은 검토자·시각·사유를 기록하고 기존 Incident approve/reject를 재사용합니다. PostgreSQL은 같은 연결, 메모리는 잠금·복원으로 Incident와 Approval을 함께 저장합니다. `003_approval.sql`은 additive migration입니다. 기존 자료의 승인 boolean을 실제 검토 기록으로 꾸며 이관하지 않습니다.

`uv run --extra dev pytest backend/tests/test_authentication.py`로 로컬 계정 매핑과 인증 거부를 확인합니다.

## 제한 사항

명령은 조직·요청자·명령·Idempotency-Key 범위에 fingerprint와 완료 결과를 저장합니다. 같은 내용은 결과를 재사용하고 다른 내용은 409 IDEMPOTENCY_CONFLICT입니다. DB 유일성과 잠금 대기 제한을 사용하며 업무 변경·Approval·Audit·Outbox·멱등 결과가 함께 커밋됩니다. 등록된 개발 계정은 키가 필수입니다. 기존 기본 로컬 계정의 키 없는 요청만 호환 목적으로 새 키를 생성하므로, 해당 예외에서는 재전송 보호를 보장하지 않습니다.

현재 추가한 인증 공급자는 로컬 개발용입니다. OIDC/SSO, JWT 검증, 실제 로그인은 아직 구현하지 않았습니다. `SERVIQ_ENV`가 development/test가 아니면 로컬 인증을 거부합니다. 기본 개발 계정은 기존 로컬 실행을 보존하기 위한 것이며 운영 인증이 아닙니다.

## 다음 단계

Tenant 범위의 저장소 조회와 서버 RBAC를 연결하고, Approval·Audit·Idempotency를 같은 트랜잭션에서 처리합니다.
