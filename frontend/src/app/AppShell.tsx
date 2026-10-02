import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { Activity, Boxes, ClipboardCheck, FileWarning, LayoutDashboard, Settings, Sparkles, Workflow } from "lucide-react";
import type { Route } from "./App";

const navigation: Array<[Route, string, typeof LayoutDashboard]> = [["dashboard", "운영 대시보드", LayoutDashboard], ["incidents", "인시던트", FileWarning], ["reviews", "검토 대기함", ClipboardCheck], ["trace", "실행 추적", Workflow], ["integrations", "연동 관리", Boxes], ["queue", "작업 대기열", Activity], ["settings", "운영 설정", Settings]];

export function AppShell({ route, onNavigate, children }: { route: Route; onNavigate: (route: Route) => void; children: ReactNode }) {
  return <div className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark"><Sparkles size={19} /></span><span>ServIQ<small>운영 인텔리전스 v0.4.1</small></span></div><nav className="navigation" aria-label="주요 메뉴">{navigation.map(([id, label, Icon]) => <button key={id} className={route === id ? "active" : ""} onClick={() => onNavigate(id)}><Icon size={17} />{label}</button>)}</nav><p className="sidebar-foot">인시던트 판단과 검토 과정을<br />한 곳에서 안전하게 관리합니다.</p></aside><main className="content"><header className="topbar"><span className="topbar-title">SERVIQ / CONTROL PLANE</span><span className="topbar-user"><span aria-hidden="true">●</span> 운영 콘솔</span></header><div className="page-scroll"><motion.div key={route} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }}>{children}</motion.div></div></main></div>;
}
