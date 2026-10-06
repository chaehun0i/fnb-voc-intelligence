import type { HistoryRun } from "./api";
import { dateTime } from "../../lib/display";

const stance = { SUPPORTING: "지지 근거", CONTRADICTING: "반대 근거", NEUTRAL: "참조만 있음" };
const sufficiency = { SUFFICIENT: "이력 가설의 근거 충분", INSUFFICIENT: "근거 부족 · 원인 미확정", CONFLICTING: "상충 근거 · 추가 검토 필요" };
const reason = { NO_EVIDENCE: "조회 가능한 근거가 없습니다.", INSUFFICIENT_SOURCE_COVERAGE: "독립적인 관련 이력이 부족하거나 참조만 존재합니다.", CONFLICTING_EVIDENCE: "반대 근거가 있어 원인 후보를 생성하지 않았습니다.", SUFFICIENT_HISTORY_SUPPORT: "독립적인 관련 이력이 반복 불만 가설을 지지합니다. 근본 원인 확정은 아닙니다." };
export function EvidenceTrace({ run }: { run: HistoryRun }) {
  const evidence = run.normalized_evidence ?? [];
  const refs = (values: string[]) => values.map((ref) => <button type="button" className="underline mr-3" key={ref} onClick={() => {
    const element = document.getElementById(`evidence-${run.agent_run_id}-${encodeURIComponent(ref)}`);
    if (element instanceof HTMLDetailsElement) { element.open = true; element.scrollIntoView?.({ block: "nearest" }); }
  }}>{ref}</button>);
  return <article className="panel !min-h-0" aria-label="근거와 원인 후보"><h3>근거 충분성 / RCA 후보</h3>
    <p className="preview-notice">{run.sufficiency ? sufficiency[run.sufficiency.status] : "이 실행은 근거 충분성 판정 이전 버전입니다."}</p>
    {run.sufficiency?.reason_codes.map((code) => <p key={code}>{reason[code]}</p>)}
    <h4 className="mt-4">정규화 근거 {evidence.length}건</h4>
    {!evidence.length && <p>원인을 주장할 수 있는 정규화 근거가 없습니다.</p>}
    <div className="space-y-2">{evidence.map((e) => <details key={e.source_ref} id={`evidence-${run.agent_run_id}-${encodeURIComponent(e.source_ref)}`} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
      <summary className="cursor-pointer"><strong>{stance[e.stance]}</strong> · <code>{e.source_ref}</code> · 순위 {e.rank}</summary>
      <dl className="detail-list mt-2"><div><dt>출처 / 원본 ID</dt><dd>{e.source_type} / {e.source_id}</dd></div><div><dt>검색 경로</dt><dd>{e.provenance.join(" + ")}</dd></div><div><dt>관측</dt><dd>{e.observation_code === "RELATED_HISTORY_MATCH" ? "유사 이력 검색 일치 · 원인 확정 아님" : "원본 참조만 있음"}</dd></div><div><dt>검색 / 원본 시각</dt><dd>{dateTime(e.retrieved_at)} / {e.source_at ? dateTime(e.source_at) : "원본 시각 미제공"}</dd></div><div><dt>실행 단계</dt><dd>{e.step_name} · {e.agent_run_id}</dd></div></dl>
    </details>)}</div>
    <h4 className="mt-4">근거 기반 RCA 후보</h4>
    {!(run.rca_candidates ?? []).length ? <p>생성된 RCA 후보가 없습니다. 충분성·정책·실행 제한을 확인해 주세요.</p> : run.rca_candidates?.map((c) => <section className="rounded-xl bg-slate-50 p-4 mt-3 dark:bg-slate-900" key={c.candidate_id}>
      <p><strong>{c.hypothesis}</strong></p><p>미확정 가설 · 점수 {(c.confidence * 100).toFixed(0)}% · {c.generated_by === "LLM_GATEWAY" ? "Gateway 구조화 제안" : "결정적 이력 규칙"}</p>
      <p>지지 근거: {refs(c.supporting_refs)}</p><p>반대 근거: {c.contradicting_refs.length ? refs(c.contradicting_refs) : "없음"}</p>
      {c.unresolved_gaps.length > 0 && <p>미해결 제한: {c.unresolved_gaps.map((g) => g.code).join(" / ")}</p>}
      <p className="muted">설정 v{c.config_version} · Decision {c.jev_decision_id} · 근본 원인 확정이나 Incident 상태 변경이 아닙니다.</p>
    </section>)}
  </article>;
}
