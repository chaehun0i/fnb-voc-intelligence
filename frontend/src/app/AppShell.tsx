import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Activity, Boxes, ChevronRight, ClipboardCheck, FileWarning, LayoutDashboard, Settings, Sparkles, Workflow } from "lucide-react";
import type { Route } from "./App";

const navigation: Array<[Route, string, typeof LayoutDashboard]> = [["dashboard", "운영 대시보드", LayoutDashboard], ["incidents", "인시던트", FileWarning], ["reviews", "검토 대기함", ClipboardCheck], ["trace", "실행 추적", Workflow], ["integrations", "연동 관리", Boxes], ["queue", "작업 대기열", Activity], ["settings", "운영 설정", Settings], ["onboarding", "데이터 시작하기", Sparkles]];

export function AppShell({ route, onNavigate, children }: { route: Route; onNavigate: (route: Route) => void; children: ReactNode }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();
  const selectedLabel = navigation.find(([id]) => id === route)?.[1] ?? "운영 콘솔";

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0;
      scrollRef.current.scrollLeft = 0;
    }
  }, [route]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); scrollRef.current?.focus(); }}>본문 바로가기</a>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark"><Sparkles size={19} aria-hidden="true" /></span>
          <span className="brand-name">ServIQ<small>운영 인텔리전스</small></span>
        </div>
        <p className="sidebar-section-label">운영 워크스페이스</p>
        <nav className="navigation" aria-label="주요 메뉴">
          {navigation.map(([id, label, Icon]) => (
            <button key={id} className={route === id ? "active" : ""} aria-label={label} aria-current={route === id ? "page" : undefined} onClick={() => onNavigate(id)} title={label}>
              <Icon size={18} aria-hidden="true" /><span className="nav-label">{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot"><strong>운영 판단과 검토</strong><p>인시던트에서 근거와 조치를<br />한 흐름으로 확인하세요.</p></div>
      </aside>
      <main className="content">
        <header className="topbar">
          <div className="topbar-title"><span>운영 콘솔</span><ChevronRight size={13} aria-hidden="true" /><strong>{selectedLabel}</strong></div>
          <div className="topbar-user"><span>ServIQ 워크스페이스</span><span className="topbar-version" aria-label="제품 버전 0.4.1">v0.4.1</span></div>
        </header>
        <div id="main-content" ref={scrollRef} className="page-scroll" tabIndex={-1} aria-label={`${selectedLabel} 본문`}>
          <motion.div key={route} initial={reduceMotion ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduceMotion ? 0 : 0.16 }}>
            {children}
          </motion.div>
        </div>
      </main>
    </div>
  );
}
