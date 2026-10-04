# Day 21 Jev Decision Layer와 Shadow 실행

## 목적

Day 20 Config 뒤에서 외부 AI 없이 정규화된 사실로 판단합니다. 기준 main은 `9e2d947`이며 Drive v0.5 정본을 사용합니다.

## 구성

순수 safety/risk 규칙은 타입·시간대·Config 상한을 검사하고 식품 안전·재발·근거 부족 위험을 계산합니다. 긴급/blocked/자동화 off/수동 요청/조사 불가 상태는 이후 라우팅이 해제할 수 없는 gate입니다.

`decision/jev`의 불변 Context/Result와 Frontend Decision 계약은 Shadow를 실행 결과와 구분합니다. ID·시각·저장은 pure core 밖의 경계 책임입니다.

## 실행/검증

각 기능 커밋에서 관련 pytest·ruff와 Frontend 타입·린트를 확인합니다. 전체 결과는 Day 마감에 기록합니다.

## 제한 사항

Jev는 상태 변경·승인·Provider 선택·Tool/LLM/Agent 실행을 하지 않습니다. 원문 VOC·PII는 입력 계약에 없습니다.

## 다음 단계

안전 규칙 → 프로필 → Config snapshot → 감사 저장 → Job Shadow → 조회/UI 순으로 연결합니다. 이후 LLM Gateway는 별도 Day입니다.
