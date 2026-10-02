import { useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Tabs from "@radix-ui/react-tabs";
import { X } from "lucide-react";
import { incidentApi } from "../../api/incidents";
import { mockApi } from "../../api/mockApi";
import { StateMessage } from "../../components/ui";
import { dateTime, percent, statusLabels } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";
import { IncidentCommandPanel } from "./IncidentCommandPanel";
import { Badge } from "./IncidentList";

const tabLabels = { timeline: "진행 이력", evidence: "증거", rca: "원인 분석", capa: "시정·예방 조치", tasks: "담당 작업", verification: "검증", trace: "실행 추적" };
export function IncidentDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const [revision, setRevision] = useState(0);
  const loader = useMemo(() => () => Promise.all([incidentApi.getIncident(id), incidentApi.getWorkspace(id), mockApi.getAgentRunForIncident(id)]), [id, revision]);
  const query = useQuery(loader);
  const [incident, workspace, trace] = query.data ?? [];
  const evidenceName = (evidenceId: string) => incident?.evidence.find((item) => item.id === evidenceId)?.source ?? evidenceId;
  return <Dialog.Root open onOpenChange={(open) => { if (!open) onBack(); }}><Dialog.Portal>
    <Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog-content" aria-describedby="incident-detail-description">
      <header className="dialog-header"><Dialog.Title>인시던트 상세</Dialog.Title><Dialog.Close className="dialog-close" aria-label="상세 팝업 닫기"><X size={19} /></Dialog.Close></header>
      <Dialog.Description id="incident-detail-description" className="sr-only">운영 이슈의 증거, 원인 분석, 조치와 검증 과정을 확인합니다.</Dialog.Description>
      <div className="dialog-body"><section className="page">
        {query.loading ? <StateMessage kind="loading" title="인시던트 상세 정보를 불러오는 중입니다" /> : query.error ? <StateMessage kind="error" title="상세 정보를 불러오지 못했습니다" onRetry={query.reload}>{query.error}</StateMessage> : !incident ? <StateMessage title="인시던트를 찾을 수 없습니다">삭제되었거나 접근할 수 없는 항목입니다.</StateMessage> : <>
          <div className="page-heading"><div><div className="mb-2 flex gap-2"><Badge value={incident.severity} /><Badge value={incident.status} kind="status" /><span className="tag status">{workspace?.priority ?? incident.priority ?? "P2"}</span></div><h1>{incident.title}</h1><p>{incident.display_id} · {incident.store} · 담당 {incident.owner}</p></div></div>
          <div className="metadata"><span className="metadata-item"><strong>발생 시각</strong>{dateTime(incident.created_at)}</span><span className="metadata-item"><strong>SLA 기한</strong>{dateTime(incident.sla_due_at)}</span>{incident.version !== undefined && <span className="metadata-item"><strong>데이터 버전</strong>{incident.version}</span>}</div>
          <Tabs.Root defaultValue="timeline" className="mt-4"><Tabs.List aria-label="인시던트 정보 영역" className="detail-tabs">{Object.entries(tabLabels).map(([value, label]) => <Tabs.Trigger key={value} value={value}>{label}</Tabs.Trigger>)}</Tabs.List>
            <Tabs.Content value="timeline" className="panel"><h2>상태 진행 이력</h2><p>서버에서 기록한 실제 전이 이력입니다. 화면에서 다음 상태를 결정하지 않습니다.</p><ol className="timeline">{incident.timeline.map((event, index) => <li key={`${event.occurred_at}-${index}`}><strong>{statusLabels[event.status]}</strong><small>{dateTime(event.occurred_at)}</small>{event.reason && <small>{event.reason}</small>}</li>)}</ol></Tabs.Content>
            <Tabs.Content value="evidence" className="panel"><h2>수집한 증거 · {incident.evidence.length}건</h2>{incident.evidence.length ? incident.evidence.map((item) => <article className="record-details" key={item.id}><strong>{item.source}</strong><p>{item.summary}</p><p>유형: {item.type} · 신뢰도: {percent(item.confidence)} · {item.status === "AVAILABLE" ? "사용 가능" : item.status === "PENDING" ? "수집 대기" : "사용 제외"}</p><small className="muted">증거 ID: {item.id}</small></article>) : <p>등록된 증거가 없습니다. 조사 단계에서 운영 명령으로 등록할 수 있습니다.</p>}</Tabs.Content>
            <Tabs.Content value="rca" className="panel"><h2>원인 후보</h2>{incident.root_cause_candidates.length ? incident.root_cause_candidates.map((item) => <article className="record-details" key={item.id}><strong>{item.summary}</strong><p>신뢰도: {percent(item.confidence)}</p><p>뒷받침 근거: {item.supporting_evidence_ids.map(evidenceName).join(", ") || "없음"}</p><p>반대 근거: {item.counter_evidence_ids.map(evidenceName).join(", ") || "없음"}</p></article>) : <p>증거를 바탕으로 등록한 원인 후보가 없습니다.</p>}</Tabs.Content>
            <Tabs.Content value="capa" className="panel"><h2>시정·예방 조치(CAPA)</h2>{incident.corrective_actions.length ? incident.corrective_actions.map((item) => <article className="record-details" key={item.id}><strong>{item.summary}</strong><p>위험도: <Badge value={item.risk_level} /> · {item.status === "EXECUTED" ? "실행 완료" : item.status === "APPROVED" ? "승인 완료" : "제안"}</p><p>기대 효과: {item.expected_effect}</p><p>검증 기준: {item.verification_criteria}</p></article>) : <p>등록된 조치안이 없습니다.</p>}</Tabs.Content>
            <Tabs.Content value="tasks" className="panel"><h2>담당 작업</h2>{workspace?.tasks.length ? workspace.tasks.map((task) => <article key={task.id} className="record-details"><strong>{task.title}</strong><p>{task.owner} · 기한 {dateTime(task.due_at)} · {task.status === "COMPLETED" ? "완료" : task.status === "RUNNING" ? "진행 중" : "대기"}</p></article>) : <p>별도 담당 작업이 없습니다. 현재 API는 Incident 운영 명령과 이력을 관리합니다.</p>}</Tabs.Content>
            <Tabs.Content value="verification" className="panel"><h2>검증 결과</h2>{incident.verification ? <><strong>{incident.verification.result === "PASS" ? "통과" : incident.verification.result === "FAIL" ? "실패·재조사 필요" : "판정 보류"}</strong><p>{incident.verification.summary}</p><p>검증 시각: {dateTime(incident.verification.verified_at)}</p></> : <p>실행 후 등록한 검증 결과가 없습니다.</p>}</Tabs.Content>
            <Tabs.Content value="trace" className="panel"><h2>연결된 실행 추적</h2><p className="preview-notice">Agent Runtime은 아직 연결되지 않았습니다. 아래 이력은 화면 검토용 예시입니다.</p>{trace ? <ol className="detail-list">{trace.steps.map((step) => <li key={step.id}><strong>{step.name}</strong><p>{step.decision_summary} · {step.latency_ms}ms · 도구 {step.tool_calls.length}회</p></li>)}</ol> : <p>이 인시던트에 연결된 실행 예시는 없습니다.</p>}</Tabs.Content>
          </Tabs.Root>
          {workspace && <IncidentCommandPanel incident={incident} workspace={workspace} onComplete={() => setRevision((value) => value + 1)} />}
        </>}
      </section></div>
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>;
}
