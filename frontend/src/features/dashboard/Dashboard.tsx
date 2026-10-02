import { ArrowUpRight } from "lucide-react";
import { incidentApi } from "../../api/incidents";
import { mockApi } from "../../api/mockApi";
import { Button, PageHeading, PreviewNotice, StateMessage, StatCard } from "../../components/ui";
import { dateTime } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";
import { Badge } from "../incidents/IncidentList";

const load = async () => { const [incidents, approvals, jobs, integrations, snapshot] = await Promise.all([incidentApi.listIncidents(), mockApi.listApprovals(), mockApi.listJobs(), mockApi.listIntegrations(), mockApi.getDashboardSnapshot()]); return { incidents, approvals, jobs, integrations, snapshot }; };
export function Dashboard({ onIncidents, onReviews, onQueue, onIncident }: { onIncidents: () => void; onReviews: () => void; onQueue: () => void; onIncident: (id: string) => void }) {
  const query = useQuery(load);
  if (query.loading) return <section className="page"><StateMessage kind="loading" title="운영 현황을 불러오는 중입니다" /></section>;
  if (query.error || !query.data) return <section className="page"><StateMessage kind="error" title="운영 현황을 불러오지 못했습니다" onRetry={query.reload} /></section>;
  const { incidents, approvals, jobs, integrations, snapshot } = query.data;
  const open = incidents.filter((item) => !["RESOLVED", "CLOSED"].includes(item.status));
  const maxTrend = Math.max(1, ...snapshot.incident_trend.flatMap((item) => [item.detected, item.resolved]));
  const totalCauses = snapshot.root_cause_distribution.reduce((total, item) => total + item.count, 0);
  return <section className="page"><PageHeading title="오늘의 운영 현황" description="우선 처리할 사건과 검토·작업·연동 상태를 한눈에 살펴보세요."><Button variant="primary" onClick={onIncidents}>인시던트 보기 <ArrowUpRight size={15} /></Button></PageHeading><PreviewNotice />
    <div className="summary-grid"><StatCard label="진행 중 인시던트" value={`${open.length}건`} /><StatCard label="긴급 인시던트" value={`${open.filter((item) => item.severity === "CRITICAL").length}건`} /><StatCard label="승인 대기" value={`${approvals.filter((item) => item.status === "PENDING").length}건`} /><StatCard label="실패 / DLQ 작업" value={`${jobs.filter((item) => ["FAILED", "DLQ"].includes(item.status)).length}건`} /></div>
    <div className="panels"><article className="panel"><h2>최근 7일 인시던트 추세</h2><p>감지와 해결 건수 · 집계 기준 {dateTime(snapshot.as_of)}</p><div className="trend-chart" aria-label="최근 7일 감지·해결 추세">{snapshot.incident_trend.map((item) => <div key={item.day} className="trend-column"><div className="trend-bars"><div className="trend-bar detected" style={{ height: `${item.detected / maxTrend * 110}px` }} title={`감지 ${item.detected}건`} /><div className="trend-bar resolved" style={{ height: `${item.resolved / maxTrend * 110}px` }} title={`해결 ${item.resolved}건`} /></div><small>{item.day}</small><small>{item.detected} / {item.resolved}</small></div>)}</div><p className="chart-legend"><span>● 감지</span><span>● 해결</span></p></article><article className="panel"><h2>원인 분석 분포</h2>{snapshot.root_cause_distribution.map((item) => <div key={item.label} className="distribution-row"><span>{item.label}</span><div className="progress-track"><div style={{ width: `${item.count / totalCauses * 100}%` }} /></div><strong>{item.count}건</strong></div>)}<h2 className="mt-6">시정·예방 조치 현황</h2><div className="flex gap-5">{snapshot.capa_status.map((item) => <div key={item.status}><span className="muted text-xs">{{ PROPOSED: "제안", APPROVED: "승인", EXECUTED: "실행" }[item.status]}</span><div className="font-bold">{item.count}건</div></div>)}</div></article></div>
    <div className="panels"><article className="panel"><h2>우선 확인할 인시던트</h2>{open.length ? open.slice(0, 4).map((item) => <div key={item.id} className="record-row"><div><button className="text-link" onClick={() => onIncident(item.id)}>{item.title}</button><p>{item.store} · 담당 {item.owner}</p></div><Badge value={item.severity} /></div>) : <p>진행 중인 인시던트가 없습니다.</p>}</article><article className="panel"><h2>운영 처리 상태</h2><div className="record-row"><span>작업 대기 {jobs.filter((item) => item.status === "QUEUED").length}건 / 처리 중 {jobs.filter((item) => item.status === "RUNNING").length}건</span><Button onClick={onQueue}>대기열 보기</Button></div><div className="record-row"><span>사람의 검토가 필요한 요청</span><Button onClick={onReviews}>검토 대기함</Button></div><h2 className="mt-5">연동 건강 상태</h2>{integrations.map((item) => <div key={item.id} className="record-row"><span>{item.name}</span><span className={`tag ${item.status === "HEALTHY" ? "low" : "high"}`}>{item.status === "HEALTHY" ? "정상" : "확인 필요"}</span></div>)}</article></div>
  </section>;
}
