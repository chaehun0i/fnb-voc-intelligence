# Day 15 ServIQ 프론트엔드 사용자 경험

## 목적

Day 13에서 고정한 ServIQ 운영 콘솔의 화면 구조와 Mock/HTTP Contract를 유지하면서, 실제 운영자가 빠르게 읽고 판단할 수 있는 한글 중심 사용자 경험을 마련한다.

## 구성

- `Tailwind CSS`: 대시보드의 여백, 색상, 버튼, 상태 표현을 유틸리티 클래스 기반으로 일관되게 구성한다.
- `Framer Motion`: 메뉴 전환 시 짧은 화면 진입 모션을 제공한다. 업무 판단을 방해하지 않도록 과도한 애니메이션은 사용하지 않는다.
- `lucide-react`: 메뉴와 상태, 증거·검토·실행 이력의 의미를 아이콘으로 보조한다.
- `Radix Select`와 `Radix Dialog`: 필터 선택과 인시던트 상세 팝업에 접근성 있는 키보드 조작, 포커스 관리, ESC 닫기를 제공한다.
- 한글 운영 용어: Dashboard, Incidents, Reviews 같은 내부 화면 라벨을 `운영 대시보드`, `인시던트`, `검토 대기함`처럼 사용자의 업무 언어로 표시한다.
- 상태 표현: 심각도와 인시던트 상태를 구분된 배지로 표시하고, 로딩·오류·빈 결과 상태를 각각 안내한다.
- 고정 App Shell: 상단 바와 사이드바는 고정하고, 각 탭의 본문 영역만 독립적으로 스크롤한다.
- 탭별 본문: 운영 대시보드, 인시던트, 검토 대기함, 실행 추적, 연동 관리, 작업 대기열, 운영 설정을 각각 독립된 운영 화면으로 구성한다.

## 실행 및 검증

`frontend/` 디렉터리에서 실행한다.

```bash
npm install
npm run dev
npm run lint
npm run test
npm run build
```

기존 Incident Mock/HTTP Adapter의 설정은 유지한다.

```bash
VITE_API_MODE=mock
VITE_API_MODE=http
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## 제한 사항

- 이번 변경은 화면 표현과 사용성에 한정한다. 인시던트 상태 전이, 승인 권한, 정책 판단은 프론트엔드가 결정하지 않는다.
- shadcn/ui는 컴포넌트 소스를 프로젝트가 직접 소유하는 방식이므로, 현재는 Tailwind와 Radix 기반 공통 패턴으로 충분한 운영 UI를 구성했다. 화면 규모가 커질 때 필요한 컴포넌트부터 선택적으로 도입한다.
- Queue/Worker, Jev, Gemini/Ollama Runtime, LangGraph, Multi-Agent, MCP는 이번 Day에서 구현하지 않는다.

## 다음 단계

Day 16에서는 Queue/Worker와 Outbox를 도입해 Incident Command 이후의 비동기 작업을 안정적으로 연결한다. 화면은 이번 Day에 마련한 공통 상태 표현을 재사용한다.
