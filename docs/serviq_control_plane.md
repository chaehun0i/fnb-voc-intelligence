# Day 20 Versioned Control Plane

## 목적

Day 19 이후 Settings를 실제 서버 설정 계약으로 전환합니다. Drive v0.5의 Day 16 스냅샷과 현재 main의 Day 17~19 구현을 구분하며 이전 버전 fallback을 사용하지 않습니다.

## 구성

`RuntimeConfig`는 React/FastAPI와 독립적인 타입이고 `ConfigVersion`은 변경자·사유·부모 버전·복원 원본을 가진 불변 스냅샷입니다. 기존 Frontend 표시 필드를 유지하되 raw와 effective, source를 구분하는 계약을 추가했습니다.

## 실행/검증

각 단계에서 관련 테스트와 린트를 실행하며 최종 결과는 Day 마감 시 기록합니다.

## 제한 사항

설정 계약의 존재는 Jev/Gemini/Ollama/Agent Runtime 구현을 의미하지 않습니다. 이번 Day에는 해당 Runtime과 production OIDC/SSO를 추가하지 않습니다.

## 다음 단계

서버 안전 상한, append-only 저장소, 조회·변경·복원 API와 실제 Settings 화면을 순서대로 연결합니다.
