import { useMemo } from "react";
import { Button, StateMessage } from "../../components/ui";
import { useQuery } from "../../lib/useQuery";
import { getIncidentAX, type IncidentAX } from "./ax";
import { agentRunApi } from "./api";
import { RuntimeControls } from "./HistoryTrace";

const dimensions = { HISTORY: "과거 사례", TRANSACTION: "거래 내역", INVENTORY: "재고" };
const progress = { RUNNING: "조사 중", SUCCESS: "확인 완료", FAILED: "확인 실패 · 확보 근거 유지", UNAVAILABLE: "데이터 부족", NO_EVIDENCE: "관련 근거 부족", STALE: "최신 근거 필요" };
const human = { NONE: "처리 결과 확인", REVIEW_REQUIRED: "담당자 검토 필요", APPROVAL_REQUIRED: "사람의 승인 필요", MORE_EVIDENCE_REQUIRED: "추가 근거 필요", MANUAL_TAKEOVER_RECOMMENDED: "담당자 직접 확인 권장", POLICY_BLOCKED: "정책 확인 필요", BUDGET_INCREASE_REQUIRED: "조사 범위 검토 필요", VERIFICATION_REQUIRED: "검증 근거 확인 필요" };
export function IncidentAXPanel({ incidentId, onAction, load = getIncidentAX }: {
  incidentId: string; onAction: (action: string) => void; load?: (id: string) => Promise<IncidentAX>;
}) {
  const loader = useMemo(() => () => load(incidentId), [load, incidentId]);
  const { data: view, loading, error, reload } = useQuery(loader);
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
      <details><summary>판단 근거와 한계 확인</summary><p>지지 근거: {view.explanation.supporting_refs.join(" · ") || "없음"}</p><p>반대 근거: {view.explanation.contradicting_refs.join(" · ") || "없음"}</p><p>부족 근거: {view.explanation.missing_codes.join(" · ") || "보고된 항목 없음"}</p>{[...view.explanation.assumptions, ...view.explanation.cannot_verify].map((text) => <p key={text}>{text}</p>)}
        {view.explanation.technical_trace_available && <Button onClick={() => onAction("TECHNICAL_TRACE")}>기술 실행 상세 열기</Button>}</details>
    </article>
  </section>;
}
