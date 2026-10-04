# Day 20 Versioned Control Plane

## 목적

Day 19 이후 Settings를 실제 서버 설정 계약으로 전환합니다. Drive v0.5의 Day 16 스냅샷과 현재 main의 Day 17~19 구현을 구분하며 이전 버전 fallback을 사용하지 않습니다.

## 구성

`RuntimeConfig`는 React/FastAPI와 독립적인 타입이고 `ConfigVersion`은 변경자·사유·부모 버전·복원 원본을 가진 불변 스냅샷입니다. 기존 Frontend 표시 필드를 유지하되 raw와 effective, source를 구분하는 계약을 추가했습니다.

서버 `ConfigResolver`는 수치 상한·타입·승인 정책·예약 읽기 도구를 검증합니다. 상한 초과를 조용히 낮추지 않고 필드별 오류로 거부하므로 raw/effective는 검증 성공 시 동일하며 `adjusted_fields`는 비어 있습니다. HIGH/CRITICAL 승인과 요청자·승인자 분리 계약은 설정으로 해제할 수 없습니다. 실제 Runtime enforcement는 별도 후속 과제입니다.

## 실행/검증

`007_control_plane.sql`은 조직·버전 복합 키와 부모/복원 원본 참조를 추가합니다. DB trigger가 과거 row의 UPDATE/DELETE를 금지합니다. 첫 버전부터 조직 advisory lock과 `expected_version` 비교로 동시 수정 충돌을 방지합니다. 기존 보안 UoW에 Config Repository를 추가해 기존 Incident/Review/Job 저장소를 보존합니다.

각 단계에서 관련 테스트와 린트를 실행하며 최종 결과는 Day 마감 시 기록합니다.

## 제한 사항

현재값은 `config`(raw)·`effective`·`sources`·`rules`·서버 permission을 함께 제공합니다. 아직 저장하지 않은 조직은 version 0 플랫폼 기본값이며 GET이 버전을 생성하지 않습니다. 이력은 limit 1~100, offset 0~10000으로 제한하고 부모와의 typed field diff를 서버에서 계산합니다. AUDITOR는 읽을 수 있지만 수정 permission은 없습니다.

설정 계약의 존재는 Jev/Gemini/Ollama/Agent Runtime 구현을 의미하지 않습니다. 이번 Day에는 해당 Runtime과 production OIDC/SSO를 추가하지 않습니다.

## 다음 단계

서버 안전 상한, append-only 저장소, 조회·변경·복원 API와 실제 Settings 화면을 순서대로 연결합니다.
