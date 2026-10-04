# Day 22 LLM Gateway

## 목적

Day 21 Jev Shadow 뒤에 Provider 중립 실행 경계를 추가합니다. 기존 RAG 생성기와 Incident/Job 실행 흐름은 보존합니다.

## 구성

- 1단계: `src/llm/contracts.py`에 불변 Intent/Request/Response/Usage 계약과 Provider Protocol을 정의했습니다. SDK 타입과 credential을 포함하지 않습니다.
- 2단계: 비동기 Gateway와 FakeProvider로 정상 응답·일시 오류·rate limit·timeout을 외부 네트워크 없이 재현합니다. deadline이 만료되면 호출하지 않습니다.
- 3단계: JSON Schema 검증과 업무 검증 hook을 분리합니다. 외부 `$ref`를 차단하고 schema repair는 설정값과 관계없이 최대 한 번입니다. 이전 응답을 repair prompt에 복제하지 않습니다.
- 4단계: Data Policy를 호출 전에 강제합니다. canonical PII/credential/raw document 필드를 재귀적으로 제거하며 RESTRICTED는 차단합니다. 자유 텍스트의 PII 탐지는 제공하지 않으므로 PII/CONFIDENTIAL 입력은 Application의 검토 표시도 필요합니다.
- 5단계: 기존 versioned Runtime Config에 Provider 허용·등급별 모델/요금·fallback 허용을 추가합니다. 이전 버전은 기본적으로 실제 호출이 비활성입니다. Router는 정책/capability/token·비용 예약량을 확인합니다. 실제 가격은 운영자가 검토한 설정값이며 제품 가격을 코드에 고정하지 않습니다.
- 6단계: 공식 `google-genai` SDK를 Gemini 어댑터에만 추가했습니다. v1 API·밀리초 timeout·SDK retry 1회(추가 재시도 없음)·JSON Schema·reasoning 포함 usage를 공통 계약으로 변환합니다. 키는 환경에서만 읽으며 실제 외부 호출은 검증하지 않았습니다.

기술 선택 근거: 기존 RAG의 `generate(str) -> str`는 Tenant/정책/schema/usage 계약이 없어 유지하고 ServIQ 경계를 추가합니다. 공식 [Google Gen AI SDK](https://googleapis.github.io/python-genai/)는 Provider 교체 가능한 어댑터 뒤에 격리합니다. 별도 Agent 프레임워크·서비스는 늘리지 않으며 mock 계약 테스트와 lockfile로 도입 위험을 줄입니다.

## 실행/검증

각 단계에서 관련 pytest와 전체 ruff를 실행합니다. 전체 검증 결과는 Day 마감 시 기록합니다.

## 제한 사항

아직 외부 모델을 호출하지 않습니다. Jev Shadow는 자동 Agent/LLM 실행 명령이 아닙니다.

## 다음 단계

FakeProvider → 구조화 출력 → Data Policy → Config Router → Gemini/Ollama → 안전한 사용 기록 순으로 진행합니다.
