# ServIQ 프론트엔드

Day 13은 ServIQ v0.4.1 전환의 첫 단계로, Frontend-first와 Contract-first Vertical Slice를 구현합니다. 이 Vite React TypeScript 애플리케이션은 향후 운영 콘솔이며, 기존 Streamlit Dashboard는 Day 1~12 분석 대시보드로 그대로 유지됩니다.

화면 컴포넌트는 향후 FastAPI/Pydantic 계약과 연결될 Mock API Contract를 사용합니다. 권한과 정책은 화면 내부에 숨기지 않고 계약 데이터로 표현합니다.

Jev는 아직 구현하지 않습니다. Gemini는 향후 공통 LLM Gateway의 기본 Provider이고, Ollama는 로컬 개발 및 대체 Provider로 유지합니다. Day 13에서는 Gemini, Ollama, Jev, LangGraph를 실제 호출하지 않습니다.

이후 개발 순서는 `Domain/API -> Queue/Worker -> Jev -> LLM Gateway -> LangGraph -> Multi-Agent -> Harness/Loop -> MCP`입니다.

화면은 Tailwind CSS, Framer Motion, lucide-react를 사용해 한글 운영 콘솔 경험을 제공합니다. 의존성 설치 후 이 디렉터리에서 `npm run dev`, `npm run lint`, `npm run test`, `npm run build`를 실행합니다.
