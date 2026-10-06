import { ArrowUpRight, RefreshCw } from "lucide-react";
import { dashboardApi } from "../../api/dashboard";
import { apiMode } from "../../api/client";
import { Button, PageHeading, PreviewNotice, StateMessage, StatCard } from "../../components/ui";
import { dateTime } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";
import { Badge } from "../../components/IncidentBadge";

const load = () => dashboardApi.getSnapshot();
export function Dashboard({ onIncidents, onReviews, onQueue, onIncident }: { onIncidents: () => void; onReviews: () => void; onQueue: () => void; onIncident: (id: string) => void }) {
  const query = useQuery(load);
  if (query.loading) return <section className="page"><StateMessage kind="loading" title="운영 현황을 불러오는 중입니다" /></section>;
  if (query.error || !query.data) return <section className="page"><StateMessage kind="error" title="운영 현황을 불러오지 못했습니다" onRetry={query.reload}>{query.error}</StateMessage></section>;
  const snapshot = query.data;
  const { kpis } = snapshot;
  const maxTrend = Math.max(1, ...snapshot.incident_trend.flatMap((item) => [item.detected, item.resolved]));
  const totalCauses = snapshot.root_cause_distribution.reduce((total, item) => total + item.count, 0);
  const empty = Object.values(kpis).every((n) => n === 0) && snapshot.incident_trend.every((item) => item.detected === 0 && item.resolved === 0) && totalCauses === 0 && snapshot.capa_status.every((item) => item.count === 0);
  return <section className="page">
    <PageHeading title="오늘의 운영 현황" description="현재 조회 권한에 포함된 사건·검토·작업의 서버 집계입니다.">
      <Button onClick={query.reload}><RefreshCw size={15} /> 최신 정보 불러오기</Button>
      <Button variant="primary" onClick={onIncidents}>인시던트 보기 <ArrowUpRight size={15} /></Button>
    </PageHeading>
    {apiMode === "mock" ? <PreviewNotice /> : <p className="preview-notice">실제 서버 운영 현황 · 예시 데이터를 섞지 않습니다.</p>}
    <p className="muted">정보 기준 시각: {dateTime(snapshot.as_of)} · 추세 날짜 기준: UTC · 조회 기간: 최근 7일</p>
    {empty && <StateMessage title="현재 조회 범위에 운영 기록이 없습니다." />}
    <div className="summary-grid">
      <StatCard label="진행 중 인시던트" value={`${kpis.open_incidents}건`} hint="해결·종결 제외" />
      <StatCard label="긴급 인시던트" value={`${kpis.critical_incidents}건`} hint="진행 중 CRITICAL" />
      <StatCard label="승인 대기" value={`${kpis.pending_approvals}건`} />
      <StatCard label="실패 작업" value={`${kpis.failed_jobs}건`} />
      <StatCard label="실패 보관함(DLQ)" value={`${kpis.dlq_jobs}건`} />
      <StatCard label="작업 대기" value={`${kpis.queue_depth}건`} hint={`예약 대기 포함 · 실행 중 ${kpis.running_jobs}건은 별도`} />
    </div>
    <div className="panels">
      <article className="panel"><h2>최근 7일 인시던트 추세</h2><p>생성과 마지막 해결 기록 · 날짜 기준 UTC</p>
        <div className="trend-chart" aria-label="최근 7일 감지·해결 추세">{snapshot.incident_trend.map((item) => <div key={item.day} className="trend-column"><div className="trend-bars"><div className="trend-bar detected" style={{ height: `${item.detected / maxTrend * 110}px` }} title={`감지 ${item.detected}건`} /><div className="trend-bar resolved" style={{ height: `${item.resolved / maxTrend * 110}px` }} title={`해결 ${item.resolved}건`} /></div><small>{item.day.length === 10 ? item.day.slice(5) : item.day}</small><small>{item.detected} / {item.resolved}</small></div>)}</div>
        <p className="chart-legend"><span>● 감지</span><span>● 해결</span></p>
      </article>
      <article className="panel"><h2>원인 분석 분포</h2><p>실제 원인 후보 수 · 분류가 없는 후보는 미분류로 표시합니다.</p>
        {totalCauses ? snapshot.root_cause_distribution.map((item) => <div key={item.label} className="distribution-row"><span>{item.label}</span><div className="progress-track"><div style={{ width: `${item.count / totalCauses * 100}%` }} /></div><strong>{item.count}건</strong></div>) : <p className="muted">아직 등록된 원인 후보가 없습니다.</p>}
        <h2 className="mt-6">시정·예방 조치 현황</h2><div className="flex gap-5">{snapshot.capa_status.map((item) => <div key={item.status}><span className="muted text-xs">{{ PROPOSED: "제안", APPROVED: "승인", EXECUTED: "실행" }[item.status]}</span><div className="font-bold">{item.count}건</div></div>)}</div>
      </article>
    </div>
    <article className="panel"><h2>우선 확인할 인시던트</h2>{snapshot.priority_incidents.length ? snapshot.priority_incidents.map((item) => <div key={item.id} className="record-row"><div><button className="text-link" onClick={() => onIncident(item.id)}>{item.title}</button><p>{item.store} · 담당 {item.owner}</p></div><Badge value={item.severity} /></div>) : <p className="muted">진행 중인 인시던트가 없습니다.</p>}</article>
    <div className="panels"><article className="panel"><h2>운영 처리 상태</h2>
      <div className="record-row"><span>대기 {kpis.queue_depth}건 / 처리 중 {kpis.running_jobs}건</span><Button onClick={onQueue}>대기열 보기</Button></div>
      <div className="record-row"><span>승인 대기 {kpis.pending_approvals}건</span><Button onClick={onReviews}>검토 대기함</Button></div>
    </article><article className="panel"><h2>연동 건강 상태</h2><p className="muted">{snapshot.integration_health.reason}</p><span className="tag">준비 중 · 실제 연동 집계 미구현</span></article></div>
  </section>;
}
