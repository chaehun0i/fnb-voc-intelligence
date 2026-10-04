# Day 22 LLM Gateway

## 목적

Day 21 Jev Shadow 뒤에 Provider 중립 실행 경계를 추가합니다. 기존 RAG 생성기와 Incident/Job 실행 흐름은 보존합니다.

## 구성

- 1단계: `src/llm/contracts.py`에 불변 Intent/Request/Response/Usage 계약과 Provider Protocol을 정의했습니다. SDK 타입과 credential을 포함하지 않습니다.
- 2단계: 비동기 Gateway와 FakeProvider로 정상 응답·일시 오류·rate limit·timeout을 외부 네트워크 없이 재현합니다. deadline이 만료되면 호출하지 않습니다.
- 3단계: JSON Schema 검증과 업무 검증 hook을 분리합니다. 외부 `$ref`를 차단하고 schema repair는 설정값과 관계없이 최대 한 번입니다. 이전 응답을 repair prompt에 복제하지 않습니다.
- 4단계: Data Policy를 호출 전에 강제합니다. canonical PII/credential/raw document 필드를 재귀적으로 제거하며 RESTRICTED는 차단합니다. 자유 텍스트의 PII 탐지는 제공하지 않으므로 PII/CONFIDENTIAL 입력은 Application의 검토 표시도 필요합니다.

## 실행/검증

각 단계에서 관련 pytest와 전체 ruff를 실행합니다. 전체 검증 결과는 Day 마감 시 기록합니다.

## 제한 사항

아직 외부 모델을 호출하지 않습니다. Jev Shadow는 자동 Agent/LLM 실행 명령이 아닙니다.

## 다음 단계

FakeProvider → 구조화 출력 → Data Policy → Config Router → Gemini/Ollama → 안전한 사용 기록 순으로 진행합니다.
