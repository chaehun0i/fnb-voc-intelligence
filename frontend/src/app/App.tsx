import { useState } from "react";
import { ArrowUpRight, CircleAlert, Clock3, ShieldCheck } from "lucide-react";
import { AppShell } from "./AppShell";
import { IncidentList } from "../features/incidents/IncidentList";
import { IncidentDetail } from "../features/incidents/IncidentDetail";
import { ReviewQueue } from "../features/reviews/ReviewQueue";
import { AgentTrace } from "../features/trace/AgentTrace";
import { ControlPlaneSettings } from "../features/settings/ControlPlaneSettings";
import { Integrations } from "../features/operations/Integrations";
import { Queue } from "../features/operations/Queue";

export type Route = "dashboard" | "incidents" | "reviews" | "trace" | "integrations" | "queue" | "settings";
const summaryItems = [["확인 필요", "2건", CircleAlert, "text-rose-600"], ["검토 대기", "1건", Clock3, "text-amber-600"], ["정상 처리", "8건", ShieldCheck, "text-emerald-600"], ["평균 대응 시간", "28분", Clock3, "text-blue-600"]] as const;

function Dashboard({ onNavigate }: { onNavigate: (route: Route) => void }) { return <section className="page"><div className="page-heading"><div><h1>오늘의 운영 현황</h1><p>우선 확인이 필요한 식품 안전 및 고객 경험 이슈를 살펴보세요.</p></div><button className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700" onClick={() => onNavigate("incidents")}>인시던트 열기 <ArrowUpRight className="ml-1 inline" size={15} /></button></div><div className="summary-grid">{summaryItems.map(([label, value, Icon, color]) => <div className="summary-card" key={label}><span>{label}</span><strong>{value}</strong><Icon className={`${color} mt-3`} size={18} /></div>)}</div><div className="panel"><h2><CircleAlert size={17} /> 우선 검토 안내</h2><p><strong>강남점 냉장 보관 온도 이탈</strong> 건은 조치안 승인을 기다리고 있습니다. 증거와 제안 조치를 검토한 뒤 승인 여부를 결정해 주세요.</p><button className="mt-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50" onClick={() => onNavigate("reviews")}>검토 대기함으로 이동</button></div></section>; }

export function App() { const [route, setRoute] = useState<Route>("dashboard"); const [incidentId, setIncidentId] = useState<string>(); const navigate = (next: Route) => { setIncidentId(undefined); setRoute(next); }; const page = route === "dashboard" ? <Dashboard onNavigate={navigate} /> : route === "incidents" ? <><IncidentList onSelect={setIncidentId} />{incidentId && <IncidentDetail id={incidentId} onBack={() => setIncidentId(undefined)} />}</> : route === "reviews" ? <ReviewQueue /> : route === "trace" ? <AgentTrace /> : route === "settings" ? <ControlPlaneSettings /> : route === "integrations" ? <Integrations /> : <Queue />; return <AppShell route={route} onNavigate={navigate}>{page}</AppShell>; }
