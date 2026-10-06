import type { HistoryRun } from "../../api/agentRuns";
import { dateTime } from "../../lib/display";

const phases = { WAITING_APPROVAL: "승인 대기 — 사람의 검토가 필요합니다", READY_TO_EXECUTE: "승인 완료 — 실행 단계 대기", REJECTED: "조치안 반려" };
const decisions = { PENDING: "검토 대기", APPROVED: "사람이 승인함", REJECTED: "사람이 반려함" };
export function CAPATrace({ run }: { run: HistoryRun }) {
  if (run.workflow_version !== "history-capa-v3") return null;
  return <article className="panel !min-h-0" aria-label="CAPA와 사람의 승인">
    <h3>근거 기반 조치 제안과 사람의 승인</h3><p className="preview-notice">CAPA는 제안입니다. 승인되어도 외부 조치는 아직 실행하지 않습니다.</p>
    {!run.capa_proposals?.length ? <p>충분한 RCA 근거가 없거나 정책에서 허용하지 않아 조치안을 생성하지 않았습니다.</p> : run.capa_proposals.map((p) => <section key={p.capa_proposal_id} className="mb-4 border-b pb-3">
      <h4>{p.summary}</h4><dl className="detail-list"><div><dt>위험 / 승인</dt><dd>{p.risk_level} / {p.required_approval ? "사람의 승인 필요" : "서버 정책 확인"}</dd></div>
        <div><dt>기대 효과</dt><dd>{p.expected_effect}</dd></div><div><dt>검증 기준</dt><dd>{p.verification_criteria}</dd></div>
        <div><dt>연결된 RCA</dt><dd><code>{p.rca_candidate_id}</code></dd></div><div><dt>지지 근거</dt><dd>{p.supporting_evidence_ids.map((id) => <code key={id} className="mr-2">{id}</code>)}</dd></div>
        <div><dt>불확실성</dt><dd>과거 이력에 기반한 가설이며 물리적 원인은 아직 확정하지 않았습니다.</dd></div></dl>
    </section>)}
    {run.approval && <section><h4>{phases[run.approval.phase]}</h4><p>{decisions[run.approval.status]}</p>
      <dl className="detail-list"><div><dt>승인 요청</dt><dd><code>{run.approval.approval_id}</code></dd></div><div><dt>대기 / 재개 시각</dt><dd>{dateTime(run.approval.waiting_since)} / {dateTime(run.approval.resumed_at ?? undefined)}</dd></div>
        <div><dt>검토자 / 결과</dt><dd>{run.approval.decision_actor ?? "아직 결정되지 않음"} / {run.approval.decision_reason_code ?? "검토 대기"}</dd></div><div><dt>고정 설정 / 조치 digest</dt><dd>v{run.approval.config_version} · <code>{run.approval.action_digest}</code></dd></div></dl>
      <a className="text-blue-700 hover:underline" href={`#/reviews?approval=${encodeURIComponent(run.approval.approval_id)}`}>기존 검토 대기함에서 조치안과 결정 사유 확인</a>
      <p>추가 근거 요청 명령은 아직 지원하지 않습니다. 정책 또는 조치가 변경되면 서버가 stale 승인을 차단합니다.</p>
    </section>}
  </article>;
}
