import { useEffect, useMemo, useRef, useState } from "react";
import { Button, StateMessage } from "../../components/ui";
import { useQuery } from "../../lib/useQuery";
import { getIncidentAX, recordAXEvent, type IncidentAX, type ProductEventType } from "./ax";
import { apiMode } from "../../shared/api";
import { agentRunApi } from "./api";
import { RuntimeControls } from "./HistoryTrace";
import { useValidation } from "./ValidationMode";

const dimensions = { HISTORY: "과거 사례", TRANSACTION: "거래 내역", INVENTORY: "재고" };
const progress = { RUNNING: "조사 중", SUCCESS: "확인 완료", FAILED: "확인 실패 · 확보 근거 유지", UNAVAILABLE: "데이터 부족", NO_EVIDENCE: "관련 근거 부족", STALE: "최신 근거 필요" };
const human = { NONE: "처리 결과 확인", REVIEW_REQUIRED: "담당자 검토 필요", APPROVAL_REQUIRED: "사람의 승인 필요", MORE_EVIDENCE_REQUIRED: "추가 근거 필요", MANUAL_TAKEOVER_RECOMMENDED: "담당자 직접 확인 권장", POLICY_BLOCKED: "정책 확인 필요", BUDGET_INCREASE_REQUIRED: "조사 범위 검토 필요", VERIFICATION_REQUIRED: "검증 근거 확인 필요" };
export function IncidentAXPanel({ incidentId, onAction, load = getIncidentAX, record = apiMode === "http" ? recordAXEvent : undefined }: {
  incidentId: string; onAction: (action: string) => void; load?: (id: string) => Promise<IncidentAX>;
  record?: typeof recordAXEvent;
}) {
  const loader = useMemo(() => () => load(incidentId), [load, incidentId]);
  const { data: view, loading, error, reload } = useQuery(loader);
  const viewKey = useRef(crypto.randomUUID());
  const [feedback, setFeedback] = useState("");
  const validation = useValidation();
  const [pending, setPending] = useState(false);
  const retry = useRef<{ type: ProductEventType; key: string } | null>(null);
  useEffect(() => {
    if (view && !loading && !error && record) void record(incidentId, "ai_brief_viewed", viewKey.current).catch(() => setFeedback("요약 열람 기록을 저장하지 못했습니다. 업무 결과는 유지됩니다."));
  }, [view, loading, error, incidentId, record]);
  useEffect(() => {
    if (!view || loading || error || !validation.active || !view.source_run_id) return;
    const milestones = ["AI_BRIEF_VIEWED", ...(view.human_action !== "NONE" ? ["HUMAN_ACTION_PRESENTED"] : []), ...(["RESOLVED", "REOPENED", "VERIFYING"].includes(view.current_phase) ? ["FINAL_STATUS_VIEWED"] : [])] as const;
    for (const milestone of milestones) void validation.signal({ surface: "INCIDENT", incident_id: incidentId, milestone: milestone as "AI_BRIEF_VIEWED" | "HUMAN_ACTION_PRESENTED" | "FINAL_STATUS_VIEWED" }).catch(() => {});
  }, [view, loading, error, incidentId, validation.active, validation.signal]);
  async function send(type: ProductEventType) {
    if (!record || pending) return;
    const key = retry.current?.type === type ? retry.current.key : crypto.randomUUID();
    retry.current = { type, key }; setPending(true);
    try {
      if (validation.active) await validation.signal({ surface: "INCIDENT", incident_id: incidentId,
        feedback_decision: ({ recommendation_accepted: "ACCEPT", recommendation_edited: "EDIT", recommendation_rejected: "REJECT" } as const)[type as "recommendation_accepted" | "recommendation_edited" | "recommendation_rejected"] }, key);
      else await record(incidentId, type, key);
      retry.current = null; setFeedback("의견을 기록했습니다. 승인이나 조치 실행은 변경하지 않았습니다."); }
    catch { setFeedback("피드백을 기록하지 못했습니다. 같은 버튼으로 다시 시도할 수 있습니다."); }
    finally { setPending(false); }
  }
  if (loading) return <StateMessage kind="loading" title="AI 업무 요약을 불러오는 중입니다" />;
  if (error) return <StateMessage kind="error" title="AI 업무 요약을 불러오지 못했습니다" onRetry={reload}>{error}</StateMessage>;
  if (!view) return <StateMessage title="아직 업무 요약이 없습니다" />;
  return <section aria-label="AI 업무 요약" className="space-y-4 mt-4">
    <article className="panel !min-h-0"><div className="flex items-center justify-between gap-2"><h2>{view.brief.headline}</h2><Button onClick={reload}>업무 요약 새로고침</Button></div>
      <p>{view.brief.summary}</p>{view.brief.primary_hypothesis && <p>검토 중인 원인 후보: {view.brief.primary_hypothesis}</p>}
      {!view.source_run_id && <p>아직 자동 조사 결과가 없습니다. 아래 운영 명령에서 조사 준비를 진행해 주세요.</p>}
      <h3>{human[view.human_action as keyof typeof human]}</h3><p>{view.next_action.reason}</p>
      <Button disabled={!view.next_action.permission} onClick={() => onAction(view.next_action.action_type)}>{view.next_action.label}</Button>
      {view.next_action.blocking_reason && <p>{view.next_action.blocking_reason}</p>}
    </article>
    {view.runtime && <RuntimeControls runtime={view.runtime} onControl={view.source_run_id && agentRunApi.control ? async (action, key) => {
      await agentRunApi.control!(incidentId, view.source_run_id!, action, view.runtime!.control_version, key);
      reload();
    } : undefined} />}
    {!!view.progress.length && <article className="panel !min-h-0"><h3>조사 진행</h3><ul>{view.progress.map((p) => <li key={p.agent_type}>{p.label} · {progress[p.status]} · 근거 {p.evidence_count}개</li>)}</ul></article>}
    <article className="panel !min-h-0"><h3>근거 범위 · {view.coverage.evidence_count}개</h3>
      {([ ["confirmed", "확인"], ["missing", "부족"], ["conflicting", "상충"], ["stale", "오래된 근거"] ] as const).map(([key, label]) => <p key={key}>{label}: {view.coverage[key].map((d) => dimensions[d]).join(" · ") || "보고된 항목 없음"}</p>)}
      <h3>불확실성</h3>{view.uncertainties.map((text) => <p key={text}>{text}</p>)}
      {view.execution_mode && <p>내부 실행 기록 · 외부 시스템 변경 없음</p>}
      {view.verification_result && <p>검증: {{ PASS: "검증 기준 충족", FAIL: "검증 실패 · 재조사 필요", INCONCLUSIVE: "판정 보류 · 검증 상태 유지" }[view.verification_result]}</p>}
      <details onToggle={(event) => { if (event.currentTarget.open) { if (validation.active) void validation.signal({ surface: "EXPLANATION", incident_id: incidentId, friction: "EXPLANATION_EXPANDED" }).catch(() => {}); if (record) void record(incidentId, "explanation_opened", crypto.randomUUID()).catch(() => setFeedback("설명 열람 기록을 저장하지 못했습니다.")); } }}><summary>판단 근거와 한계 확인</summary><p>지지 근거: {view.explanation.supporting_refs.join(" · ") || "없음"}</p><p>반대 근거: {view.explanation.contradicting_refs.join(" · ") || "없음"}</p><p>부족 근거: {view.explanation.missing_codes.join(" · ") || "보고된 항목 없음"}</p>{[...view.explanation.assumptions, ...view.explanation.cannot_verify].map((text) => <p key={text}>{text}</p>)}
        {view.explanation.technical_trace_available && <Button onClick={() => onAction("TECHNICAL_TRACE")}>기술 실행 상세 열기</Button>}</details>
    </article>
    {view.feedback_allowed && record && <article className="panel !min-h-0"><h3>제안에 대한 의견</h3><p>의견은 RAW 피드백으로만 저장됩니다. 승인·반려 결정이나 조치안 수정은 기존 업무 화면에서 진행합니다.</p>
      <div className="flex flex-wrap gap-2">{([["recommendation_accepted", "제안 수용 의견"], ["recommendation_edited", "수정 필요 의견"], ["recommendation_rejected", "비수용 의견"]] as const).map(([type, label]) => <Button key={type} disabled={pending} onClick={() => void send(type)}>{label}</Button>)}</div></article>}
    {validation.active && (view.human_action === "MORE_EVIDENCE_REQUIRED" || view.runtime?.control_status === "MANUAL_TAKEOVER") && <article className="panel !min-h-0"><h3>과업 의견</h3><p>기존 업무 상태를 확인한 RAW 의견입니다. 상태를 변경하거나 정답으로 승격하지 않습니다.</p><Button disabled={pending} onClick={() => {
      setPending(true); void validation.signal({ surface: "INCIDENT", incident_id: incidentId,
        feedback_decision: view.runtime?.control_status === "MANUAL_TAKEOVER" ? "MANUAL_TAKEOVER" : "REQUEST_MORE_EVIDENCE" }, `${viewKey.current}:task-feedback`)
        .then(() => setFeedback("의견을 기록했습니다. 승인이나 조치 실행은 변경하지 않았습니다."))
        .catch(() => setFeedback("과업 의견을 기록하지 못했습니다. 다시 시도해 주세요."))
        .finally(() => setPending(false));
    }}>{view.runtime?.control_status === "MANUAL_TAKEOVER" ? "담당자 인계 확인 의견" : "추가 근거 필요 의견"}</Button></article>}
    {feedback && <p role="status">{feedback}</p>}
    {!!view.metrics?.length && <details><summary>측정 가능한 업무 지표</summary><p>현재 실행 기준 · 일부 지표만 관측되며 비용은 실제 청구액이 아닙니다.</p><dl>{view.metrics.map((m) => <div key={m.name}><dt>{{ end_to_end_completion: "전체 흐름 완료", time_to_first_useful_evidence: "첫 유효 근거까지", time_to_decision: "승인 결정까지", human_intervention: "사람 개입", manual_takeover: "수동 인계", loop_abort: "자동 조사 종료", cost_per_completed_incident: "완료 실행의 추정 비용" }[m.name] ?? m.name}</dt><dd>{m.value === null ? "측정 불가" : `${m.value} ${m.unit}`} · {m.status === "PARTIAL" ? "일부 관측" : m.status === "UNAVAILABLE" ? "자료 없음" : "관측됨"}</dd></div>)}</dl></details>}
  </section>;
}
