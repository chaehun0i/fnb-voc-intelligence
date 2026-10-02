# Day 16 ServIQ 인시던트 수동 업무 흐름

## 목적

운영자가 증거를 바탕으로 문제를 조사하고, 조치를 승인한 뒤 결과를 확인하는 닫힌 업무 흐름을 제공합니다. LLM이 없어도 결과가 결정적으로 나오며, 앞으로 자동화가 추가되어도 동일한 Domain Rule을 거칩니다.

## 구성

기본 흐름은 다음과 같습니다.

```text
DETECTED → TRIAGED → INVESTIGATING → RCA_READY → ACTION_PROPOSED
→ PENDING_APPROVAL → EXECUTING → VERIFYING → RESOLVED → CLOSED
```

각 단계는 다음 선행 조건을 확인합니다.

| 단계 | 확인할 조건 |
| --- | --- |
| 조사 시작 | 초기 분류를 완료했거나 재조사 상태여야 합니다. |
| 원인 후보 확정 | 원인 후보에 실제 등록된 AVAILABLE 증거가 필요합니다. 같은 증거를 찬성·반대 근거로 동시에 지정할 수 없습니다. |
| 조치 제안 | 원인 후보를 확정해야 하며 기대 효과와 검증 기준을 입력합니다. |
| 조치 실행 | 사람의 승인이 있어야 합니다. 외부 시스템 변경 없이 수동 실행을 기록합니다. |
| 해결 | 검증 결과가 PASS여야 합니다. |
| 재조사 | VERIFYING에서 FAIL이 나오거나 RESOLVED 이후 재발 사유를 기록해야 합니다. |
| 종료 | RESOLVED 이후에만 가능합니다. CLOSED에서 실행 단계로 돌아갈 수 없습니다. |

승인 반려는 `PENDING_APPROVAL → ACTION_PROPOSED`로 돌아가며 승인을 해제합니다. 제안 단계에서 `actions` 명령으로 조치안을 수정한 뒤 승인을 다시 요청할 수 있습니다. 검증 결과가 `INCONCLUSIVE`이면 `VERIFYING`에 남습니다. 검증 실패로 재조사할 때는 기존 승인·원인 후보·조치안을 해제하여 이전 승인을 재사용하지 않습니다. 수집한 증거와 상태 이력은 유지합니다.

Domain의 `transition`은 새 모델을 반환합니다. Application은 전이가 성공한 모델만 저장합니다. 메모리 Repository는 중첩 목록까지 복사하므로 실패한 명령이나 화면 밖의 수정이 저장된 데이터를 바꿀 수 없습니다.

Repository의 `save`는 새 모델의 `version=0`을 저장해 `version=1`로 반환합니다. 수정할 때는 읽은 버전이 저장된 버전과 같아야 하며, 성공할 때만 증가합니다. 따라서 동시에 수정한 두 요청 중 오래된 요청은 `CONFLICT`로 거절됩니다.

## 실행 및 검증

API 실행과 전체 Endpoint는 [Incident API 문서](serviq_incident_api.md)를 참고하세요. API를 실행하는 작업 폴더는 `backend/`이며, 업무 코드는 `backend/src/domain`, `backend/src/application`, `backend/src/api`로 구분합니다. Python import 이름 `src.*`는 유지하므로 기존 RAG·ingestion·Streamlit 코드도 이전과 같은 모듈 명령으로 동작합니다.

```bash
cd backend
uv run fastapi run
```

로컬 컴퓨터에서만 접근하려면 `uv run fastapi run --host 127.0.0.1`로 실행합니다. 저장소 루트의 기존 `uv run uvicorn src.api.app:app --reload` 실행 경로도 유지합니다.

저장 방식은 `SERVIQ_REPOSITORY=memory` 또는 `SERVIQ_REPOSITORY=postgres`로 선택합니다. PostgreSQL을 사용하면 `SERVIQ_DATABASE_URL`을 지정하고 별도 마이그레이션 명령으로 스키마를 준비합니다. `SERVIQ_SEED_DEMO=true`는 개발 예시를 명시적으로 생성합니다. 기본값은 `memory`, 예시 데이터 비활성화입니다. DB 배포/SQL 파일은 `db/` 경로와 해당 문서를 확인하세요.

새 접수의 최소 요청은 다음과 같습니다.

```json
{
  "title": "냉장 진열 온도 이상",
  "severity": "HIGH",
  "store": "강남점",
  "owner": "운영 담당자",
  "priority": "P1"
}
```

분류는 `POST /api/v1/incidents/{id}/triage`에 `{ "severity": "HIGH", "expected_version": 1 }`을 보냅니다. 조사 시작 후 `evidence`에 증거를 등록하고, `rca`에는 증거 ID를 참조하는 `candidates`를 보냅니다. `actions`의 조치안에는 위험도·기대 효과·검증 기준을 포함합니다. `request-approval`, `approve`, `execute`를 순서대로 호출한 후 `verify`에 검증 결과와 요약을 기록합니다.

```json
{
  "result": "PASS",
  "summary": "4도 이하로 유지되는 것을 확인했습니다."
}
```

`GET /api/v1/incidents/{id}/workspace`의 `commands`는 각 동작의 `allowed`와 `reason`을 제공합니다. 프론트엔드 버튼은 이 결과를 사용하며 업무 규칙을 복제하지 않습니다.

다음 테스트는 고정 시계와 ID로 실행합니다.

```bash
uv run --extra dev pytest backend/tests/test_incident_domain.py backend/tests/test_incident_application.py backend/tests/test_api_app.py
```

정상 완료 흐름, 승인 없는 실행 거부, 검증 실패·판정 보류, 잘못된 근거 ID, 실패 명령의 원본 보존, 버전 충돌, HTTP 입력 검증, CORS, arbitrary status PATCH 부재를 확인합니다.

## 제한 사항

이 흐름은 운영 명령의 결정적 기반입니다. 실제 외부 장비·재고·거래 변경을 수행하지 않습니다. 모든 HTTP 사용자에게 동일한 업무 상태 Permission이 제공되며, 로그인·사용자 역할·승인자 감사는 별도 연결이 필요합니다.

타입에 있는 `ESCALATED`, `BLOCKED`, `FAILED`는 앞으로 Policy/실행 실패를 연결할 수 있도록 유지합니다. 이 상태로 자유롭게 변경하는 일반 API는 제공하지 않습니다. 요청 멱등 키와 자동 재시도는 아직 이 Application Service의 기능이 아닙니다.

## 다음 단계

Repository 구현별로 같은 버전 충돌·복사·저장 계약을 검증합니다. 그 다음 영속적인 명령 멱등성, 사용자/승인자 감사, Outbox와 비동기 Worker를 연결합니다. 자동화 도입 후에도 승인과 검증을 건너뛰지 않도록 Domain Rule을 공통 경계로 유지합니다.
