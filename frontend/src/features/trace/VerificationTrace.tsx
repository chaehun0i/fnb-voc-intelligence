import type { HistoryRun } from "../../api/agentRuns";
import { dateTime } from "../../lib/display";

const messages = { PASS: "검증 기준을 충족했습니다.", FAIL: "검증 기준을 충족하지 못해 사건이 재조사 상태로 전환되었습니다.", INCONCLUSIVE: "검증 근거가 부족해 검증 상태를 유지합니다." };
export function VerificationTrace({ run }: { run: HistoryRun }) {
  if (run.workflow_version !== "history-verification-v4") return null;
  return <article className="panel !min-h-0" aria-label="내부 실행과 검증 결과">
    <h3>내부 실행 기록과 Verification</h3>
    <p className="preview-notice">내부 실행 기록 / 시뮬레이션입니다. 외부 시스템 변경은 수행하지 않았습니다. 실제 현장 조치의 효과를 입증하지 않습니다.</p>
    {!run.execution ? <p>아직 내부 실행 기록이 없습니다. 유효한 사람의 승인과 서버 정책 확인이 필요합니다.</p> : <dl className="detail-list">
      <div><dt>실행 모드 / 상태</dt><dd>{run.execution.execution_mode} / {run.execution.status}</dd></div>
      <div><dt>실행 기록</dt><dd><code>{run.execution.execution_id}</code> · {dateTime(run.execution.completed_at)}</dd></div>
      <div><dt>기록 의미</dt><dd>{run.execution.safe_result_summary}</dd></div>
    </dl>}
    {run.verification ? <section><h4>{run.verification.result} — {messages[run.verification.result]}</h4>
      <dl className="detail-list"><div><dt>검증 범위</dt><dd>{run.verification.observation_mode} · 내부 검토 기록 기준</dd></div><div><dt>검증 기준</dt><dd>{run.verification.criteria}</dd></div>
        <div><dt>기준별 결과</dt><dd>{run.verification.criterion_results.map((c) => <p key={c.code}>{c.code}: {c.result}</p>)}</dd></div>
        <div><dt>사유</dt><dd>{run.verification.reason_codes.join(" · ")}</dd></div><div><dt>Incident 결과</dt><dd>{run.resulting_incident_status}</dd></div>
        <div><dt>검증 시각 / 설정</dt><dd>{dateTime(run.verification.verified_at)} · v{run.verification.config_version}</dd></div></dl>
      <h4>조치 후 검증 근거</h4>{run.verification_evidence?.length ? <ul>{run.verification_evidence.map((e) => <li key={e.evidence_id}><code>{e.source_ref}</code> · {e.observation_mode} · {dateTime(e.observed_at)}<p>연결된 원본 근거: {e.additional_evidence_refs.join(" · ") || "없음"}</p></li>)}</ul> : <p>조치 후 검증 근거가 없습니다. 과거 History 근거만으로 PASS를 만들지 않습니다.</p>}
    </section> : <p>아직 완료된 검증 결과가 없습니다.</p>}
  </article>;
}
