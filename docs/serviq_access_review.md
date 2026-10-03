# Day 17 Tenant RBAC와 Review 실행 계약

## 목적

Day 16의 Incident 업무 흐름에 요청자·조직·권한·승인·감사·멱등성 경계를 연결합니다. 기준은 Google Drive v0.5의 05·14·24·28·30 문서입니다. 기존 Data Intelligence와 Streamlit은 보존합니다.

## 구성

`Principal`은 요청자·조직·역할·매장 범위·인증 출처를 표현하고 `IdentityProvider` Port에서 전달합니다. `LocalIdentityProvider`는 서버에 설정한 계정만 반환하며 브라우저의 조직·역할 헤더를 신뢰하지 않습니다.

Incident HTTP 경로는 조직에 고정된 Repository를 사용합니다. 다른 조직의 ID는 존재 여부를 노출하지 않는 404, 같은 조직 내 역할·매장 권한 부족은 403으로 구분합니다. 조회·운영·검토·관리 역할은 중앙 Authorization에서 판정하며 Reviewer는 조사 명령을 실행할 수 없습니다. `002_tenant_security.sql`은 기존 자료를 `legacy-local` 조직으로 보존합니다.

## 실행 및 검증

`uv run --extra dev pytest backend/tests/test_authentication.py`로 로컬 계정 매핑과 인증 거부를 확인합니다.

## 제한 사항

현재 추가한 인증 공급자는 로컬 개발용입니다. OIDC/SSO, JWT 검증, 실제 로그인은 아직 구현하지 않았습니다. `SERVIQ_ENV`가 development/test가 아니면 로컬 인증을 거부합니다. 기본 개발 계정은 기존 로컬 실행을 보존하기 위한 것이며 운영 인증이 아닙니다.

## 다음 단계

Tenant 범위의 저장소 조회와 서버 RBAC를 연결하고, Approval·Audit·Idempotency를 같은 트랜잭션에서 처리합니다.
