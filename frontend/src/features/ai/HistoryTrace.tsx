import { useMemo, useState } from "react";
import { agentRunApi, type AgentRunApi, type ControlAction, type InvestigationProgress, type RuntimeAX } from "./api";
import { incidentApi } from "../incidents/api";
import { apiMode } from "../../shared/api";
import { SelectField } from "../../components/SelectField";
import { Button, PageHeading, StateMessage, StatCard } from "../../components/ui";
import { dateTime } from "../../lib/display";
import { useQuery } from "../../lib/useQuery";
import { EvidenceTrace } from "./EvidenceTrace";
import { CAPATrace } from "./CAPATrace";
import { VerificationTrace } from "./VerificationTrace";

const statusLabels = { RUNNING: "조사 중", WAITING_APPROVAL: "사람의 승인 대기", COMPLETED: "Workflow 완료", FAILED: "조사 실패" };
const gapLabels = { CAPABILITY_UNAVAILABLE: "필요한 데이터가 없어 해당 조사를 실행하지 않았습니다.", SOURCE_UNAVAILABLE: "자료를 조회하지 못했습니다. 다른 조사 근거는 유지합니다.", SOURCE_STALE: "자료가 오래되어 최신 근거가 필요합니다.", BRANCH_FAILED: "독립 조사 하나가 실패했습니다. 확보한 다른 근거는 유지합니다.", NO_EVIDENCE_FOUND: "해당 조사에서 관련 근거를 찾지 못했습니다.", BRANCH_BUDGET_EXHAUSTED: "조사 시간 예산이 부족합니다.", NO_AUTHORIZED_HISTORY: "관련 이력이 부족해 추가 근거가 필요합니다.", LLM_POLICY_DENIED: "데이터 정책에 따라 LLM 요청을 차단했습니다. 검색 근거만 확인해 주세요.", LLM_UNAVAILABLE: "LLM 보조 판단을 완료하지 못했습니다. 검색 근거는 유지했습니다.", INSUFFICIENT_SOURCE_COVERAGE: "RCA를 지지할 독립 근거가 부족합니다.", CONFLICTING_EVIDENCE: "상충하는 근거가 있어 추가 검토가 필요합니다.", RCA_DISABLED: "현재 실행의 설정에서는 RCA 자동 초안을 허용하지 않습니다.", RCA_BUDGET_EXHAUSTED: "남은 예산이 부족해 RCA 요청을 시작하지 않았습니다." };
const nodeLabels = { validate_context: "실행 조건 확인", history_investigation: "과거 VOC와 유사 사례 조사", normalize_evidence: "원본 근거 정규화", evaluate_sufficiency: "근거 충분성 판정", rca_investigation: "근거 기반 원인 후보", persist_result: "조사 결과 기록", capa_proposal: "근거 기반 조치 제안", apply_capa: "Incident Command에 조치 반영", request_approval: "실제 승인 요청", approval_interrupt: "사람의 검토에서 Workflow 중단", approval_result: "승인 검증 후 Workflow 재개", internal_execution: "안전한 내부 실행 기록", begin_verification: "검증 상태 진입", verification: "조치 후 근거 기반 검증", apply_verification: "검증 결과를 Incident에 반영" };

const branchLabels = { RUNNING: "조사 중", SUCCESS: "조사 완료", FAILED: "조사 실패 — 확보한 근거 유지", UNAVAILABLE: "데이터 사용 불가", NO_EVIDENCE: "관련 근거 부족", STALE: "최신 근거 필요" };
const coverageLabels = { CONFIRMED: "근거 확보", MISSING: "근거 부족", CONFLICTING: "상충 근거", STALE: "오래된 근거" };
export function InvestigationProgressPanel({ progress }: { progress: InvestigationProgress }) {
  return <article className="panel !min-h-0" aria-label="조사 진행과 근거 범위"><h3>독립 조사 진행</h3>
    <p>근거 {progress.evidence_count}개 확보 · {progress.status === "PARTIAL" ? "일부 조사 근거가 부족합니다. 확보한 근거는 유지합니다." : progress.status === "RUNNING" ? "사용 가능한 데이터를 조사하고 있습니다." : "선택된 조사를 완료했습니다."}</p>
    <ul>{progress.agents.map((agent) => <li key={agent.agent_type}><strong>{agent.business_label} · {branchLabels[agent.status]}</strong> · 근거 {agent.evidence_count}개{agent.agent_type !== "HISTORY" && <small> · 합성 운영 관측 자료 · 실제 POS/ERP 연결 아님</small>}</li>)}</ul>
    <ul>{progress.coverage.map((item) => <li key={item.dimension}>{progress.agents.find((agent) => agent.agent_type === item.dimension)?.business_label} · {coverageLabels[item.status]}</li>)}</ul>
    <p>{progress.uncertainty}</p><small>갱신 {dateTime(progress.updated_at)}</small>
  </article>;
}

function RunDetail({ incidentId, runId, api }: { incidentId: string; runId: string; api: AgentRunApi }) {
  const loader = useMemo(() => () => api.detail(incidentId, runId), [api, incidentId, runId]);
  const { data: run, loading, error, reload } = useQuery(loader);
  if (loading) return <StateMessage kind="loading" title="조사 상세 기록을 불러오는 중입니다" />;
  if (error) return <StateMessage kind="error" title="조사 상세 기록을 불러오지 못했습니다" onRetry={reload}>{error}</StateMessage>;
  if (!run) return null;
  return <div className="space-y-4 mt-4">
    {run.runtime && <RuntimeControls runtime={run.runtime} onControl={api.control ? async (action, key) => {
      await api.control!(incidentId, runId, action, run.runtime!.control_version, key); reload();
    } : undefined} />}
    {run.investigation && <InvestigationProgressPanel progress={run.investigation} />}
    <details open={!run.investigation}><summary>기술 실행 상세</summary>
    <div className="summary-grid"><StatCard label="조사 상태" value={statusLabels[run.status]} /><StatCard label="근거 후보" value={`${run.evidence_candidates.length}건`} /><StatCard label="사용 토큰" value={run.token_spent.toLocaleString()} /><StatCard label="예상 비용" value={`$${run.cost_spent.toFixed(4)}`} hint="Gateway 기록 기준 · 실제 청구액 아님" /></div>
    <article className="panel !min-h-0"><h3>History Investigation</h3><p>{run.findings.length ? "과거 VOC와 유사 사례를 조사했습니다." : "관련 이력이 부족해 추가 근거가 필요합니다."}</p><p>{run.token_spent ? "LLM Gateway의 구조화 보조 판단을 사용했습니다." : "기록된 LLM 사용량이 없습니다. 검색 근거와 아래 실패·제한 사항을 확인하세요."}</p>
      <dl className="detail-list"><div><dt>Jev 경로 / 위험</dt><dd>{run.route} / {run.risk_level}</dd></div><div><dt>설정 / Workflow 버전</dt><dd>v{run.config_version} / {run.workflow_version}</dd></div><div><dt>시작 / 완료</dt><dd>{dateTime(run.started_at)} / {dateTime(run.completed_at ?? undefined)}</dd></div><div><dt>상관관계 ID</dt><dd><code>{run.correlation_id}</code></dd></div><div><dt>Decision / Job</dt><dd><code>{run.jev_decision_id} / {run.job_id}</code></dd></div></dl>
      {run.safe_error_summary && <p role="alert">{run.safe_error_summary} · {run.error_code}</p>}
      <h4 className="mt-4">원본 증거 후보</h4>{run.evidence_candidates.length ? <ol>{run.evidence_candidates.map((e) => <li key={e.source_ref}><code>{e.source_ref}</code> · 검색 순위 {e.rank} · {dateTime(e.retrieved_at)}</li>)}</ol> : <p>허용된 원본 출처에서 찾은 근거가 없습니다.</p>}
      {run.evidence_gaps.map((g, index) => <p className="preview-notice" key={`${g.code}-${index}`}>{gapLabels[g.code]}</p>)}
    </article>
    </details>
    <EvidenceTrace run={run} />
    <CAPATrace run={run} />
    <VerificationTrace run={run} />
    <article className="panel !min-h-0"><h3>실행 단계</h3><ol className="timeline">{run.steps.map((s) => <li key={`${s.sequence}-${s.attempt}`}><strong>{nodeLabels[s.node_name]} · {statusLabels[s.status]}</strong><small>시도 {s.attempt} · {s.latency_ms.toFixed(0)}ms · 토큰 {s.token_spent}</small></li>)}</ol>{!run.steps.length && <p>아직 완료된 단계 기록이 없습니다.</p>}</article>
  </div>;
}

export function RuntimeControls({ runtime, onControl }: { runtime: RuntimeAX; onControl?: (action: ControlAction, key: string) => Promise<void> }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [retry, setRetry] = useState<{ action: ControlAction; key: string }>();
  const labels: Record<ControlAction, string> = { pause: "일시정지", resume: "자동 조사 재개", stop: "자동 조사 중단", takeover: "담당자 수동 인계" };
  async function execute(action: ControlAction) {
    if (!onControl || !runtime.permissions[action] || pending) return;
    const key = retry?.action === action ? retry.key : crypto.randomUUID();
    setPending(true); setError(undefined); setRetry({ action, key });
    try { await onControl(action, key); setRetry(undefined); }
    catch (value) { setError(value instanceof Error ? value.message : "제어 요청을 처리하지 못했습니다. 상태를 새로고침해 주세요."); }
    finally { setPending(false); }
  }
  return <article className="panel !min-h-0" aria-label="자동 조사 제어">
    <h3>자동 조사 상태</h3><p>{runtime.message}</p><p>{runtime.budget_summary}</p><p>{runtime.new_evidence ? "추가 조사에서 새 근거를 확보했습니다." : "새 근거 발견 여부는 서버 조사 결과를 확인해 주세요."}</p><p>{runtime.human_action}</p>
    {error && <p role="alert">{error}</p>}
    <div className="flex flex-wrap gap-2">{(Object.keys(labels) as ControlAction[]).map((action) =>
      <Button key={action} disabled={pending || !onControl || !runtime.permissions[action]} onClick={() => void execute(action)}>{labels[action]}</Button>)}</div>
    {pending && <p role="status">제어 요청을 처리하고 있습니다.</p>}
    <details><summary>실행 정책 버전</summary><dl>{Object.entries(runtime.versions).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl></details>
  </article>;
}

export function HistoryTracePanel({ incidentId, api = agentRunApi }: { incidentId: string; api?: AgentRunApi }) {
  const loader = useMemo(() => () => api.list(incidentId), [api, incidentId]);
  const { data, loading, error, reload } = useQuery(loader);
  const [selected, setSelected] = useState<string>();
  const [detailRevision, setDetailRevision] = useState(0);
  if (loading) return <StateMessage kind="loading" title="실제 History 조사 기록을 불러오는 중입니다" />;
  if (error) return <StateMessage kind="error" title="실제 조사 기록을 불러오지 못했습니다" onRetry={reload}>{error}</StateMessage>;
  return <section aria-label="실제 History 조사 기록"><div className="flex items-center justify-between gap-3"><h2>실제 History 조사 기록</h2><Button onClick={() => { reload(); setDetailRevision((value) => value + 1); }}>조사 기록 새로고침</Button></div><p className="muted">{apiMode === "http" ? "서버 실행 기록" : "예시 모드 · 실제 실행 없음"} · History와 Evidence/RCA, 정책에서 허용한 CAPA 제안·사람의 승인을 표시합니다. 사용 가능한 데이터에 한해 독립 조사를 표시합니다. 자동 조사는 서버 안전 정책을 따릅니다. 외부 조치·MCP는 실행하지 않습니다.</p>
    {!data?.runs.length ? <StateMessage title="아직 실행된 History 조사가 없습니다">명시적으로 등록한 History Job의 실행 결과가 여기에 표시됩니다.</StateMessage> : <><SelectField label="조사 실행 선택" value={selected ?? data.runs[0].agent_run_id} options={data.runs.map((r) => ({ value: r.agent_run_id, label: `${statusLabels[r.status]} · ${dateTime(r.started_at)} · v${r.config_version}` }))} onValueChange={setSelected} /><RunDetail key={`${selected ?? data.runs[0].agent_run_id}-${detailRevision}`} incidentId={incidentId} runId={selected ?? data.runs[0].agent_run_id} api={api} />{data.has_more && <p>최근 20건을 표시합니다. 이전 기록은 조회 API로 확인할 수 있습니다.</p>}</>}
  </section>;
}

export function HistoryTracePage() {
  const query = useQuery(incidentApi.listIncidents);
  const [selected, setSelected] = useState<string>();
  const id = selected ?? query.data?.[0]?.id;
  return <section className="page"><PageHeading title="실행 추적" description="실제 Incident의 독립 조사 진행과 원본 근거를 확인하세요." />
    {query.loading ? <StateMessage kind="loading" title="인시던트를 불러오는 중입니다" /> : query.error ? <StateMessage kind="error" title="인시던트를 불러오지 못했습니다" onRetry={query.reload}>{query.error}</StateMessage> : !id ? <StateMessage title="조회할 인시던트가 없습니다" /> : <><SelectField label="조사 대상 인시던트" value={id} options={(query.data ?? []).map((i) => ({ value: i.id, label: `${i.display_id} · ${i.title}` }))} onValueChange={setSelected} /><HistoryTracePanel key={id} incidentId={id} /></>}
  </section>;
}
