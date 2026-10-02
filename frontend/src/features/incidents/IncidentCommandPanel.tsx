import { useState } from "react";
import type { Incident, IncidentWorkspace, Severity } from "../../contracts/types";
import { apiMode, IncidentApiError, incidentCommand } from "../../api/incidents";
import { SelectField } from "../../components/SelectField";
import { Button } from "../../components/ui";
import { severityLabels } from "../../lib/display";

export const commandLabels: Record<string, string> = { triage: "분류 확정", investigate: "조사 시작", evidence: "증거 등록", rca: "원인 분석 등록", actions: "시정·예방 조치 제안", "request-approval": "승인 요청", approve: "조치 승인", reject: "조치 반려", execute: "수동 실행 완료 기록", verify: "검증 결과 등록", close: "종결", reopen: "재발 등록" };

export function IncidentCommandPanel({ incident, workspace, onComplete }: { incident: Incident; workspace: IncidentWorkspace; onComplete: () => void }) {
  const [command, setCommand] = useState("triage");
  const [summary, setSummary] = useState(""); const [source, setSource] = useState(""); const [effect, setEffect] = useState(""); const [criteria, setCriteria] = useState("");
  const [risk, setRisk] = useState<Severity>(incident.severity); const [confidence, setConfidence] = useState("0.8"); const [result, setResult] = useState("PASS");
  const [evidenceIds, setEvidenceIds] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; message: string; code?: string }>();
  const [busy, setBusy] = useState(false);
  const permission = workspace.commands?.[command] ?? { allowed: false, reason: "미리보기에서는 실제 인시던트 명령을 실행하지 않습니다. HTTP 모드로 연결해 주세요." };
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (apiMode !== "http" || !permission.allowed) {
      setFeedback({ kind: "error", message: apiMode !== "http" ? "미리보기에서는 실제 명령을 실행하지 않습니다. HTTP 모드로 연결해 주세요." : permission.reason });
      return;
    }
    setBusy(true);
    setFeedback(undefined);
    const body: Record<string, unknown> = { expected_version: incident.version };
    if (command === "triage") body.severity = risk;
    if (command === "evidence") body.evidence = { id: crypto.randomUUID(), source, type: "MANUAL_RECORD", summary, confidence: Number(confidence) };
    if (command === "rca") body.candidates = [{ id: crypto.randomUUID(), summary, confidence: Number(confidence), supporting_evidence_ids: evidenceIds, counter_evidence_ids: [] }];
    if (command === "actions") body.actions = [{ id: crypto.randomUUID(), summary, risk_level: risk, expected_effect: effect, verification_criteria: criteria }];
    if (command === "verify") Object.assign(body, { result, summary });
    if (command === "reopen") body.reason = summary;
    try {
      await incidentCommand(incident.id, command, body);
      setFeedback({ kind: "success", message: `${commandLabels[command]} 요청이 반영되었습니다.` });
      setSummary("");
      onComplete();
    }
    catch (error) {
      setFeedback(error instanceof IncidentApiError
        ? { kind: "error", code: error.code, message: `${error.message}${error.requestId ? ` (요청 ID: ${error.requestId})` : ""}` }
        : { kind: "error", message: "요청에 실패했습니다. 다시 시도해 주세요." });
    }
    finally { setBusy(false); }
  }
  return <article className="panel mt-4"><h2>운영 명령</h2><p>활성화 여부와 선행 조건은 서버의 Permission Contract를 그대로 표시합니다. 실행 완료 기록은 외부 시스템을 변경하지 않습니다.</p>
    <form onSubmit={(event) => { void submit(event); }} className="command-form">
      <fieldset disabled={busy} className="contents">
      <SelectField label="운영 명령 선택" value={command} options={Object.entries(commandLabels).map(([value, label]) => ({ value, label }))} onValueChange={(value) => { setCommand(value); setFeedback(undefined); }} />
      <p>{permission.reason}</p>
      {["triage", "actions"].includes(command) && <SelectField label="명령 심각도 또는 위험도" value={risk} options={Object.entries(severityLabels).map(([value, label]) => ({ value, label }))} onValueChange={(value) => setRisk(value as Severity)} />}
      {command === "evidence" && <label>증거 출처<input required maxLength={2000} value={source} onChange={(event) => setSource(event.target.value)} placeholder="예: 매장 온도 기록" /></label>}
      {["evidence", "rca", "actions", "verify", "reopen"].includes(command) && <label>{command === "reopen" ? "재발 사유" : "내용 요약"}<textarea required maxLength={2000} value={summary} onChange={(event) => setSummary(event.target.value)} /></label>}
      {["evidence", "rca"].includes(command) && <label>신뢰도 (0~1)<input type="number" required min={0} max={1} step="0.01" value={confidence} onChange={(event) => setConfidence(event.target.value)} /></label>}
      {command === "rca" && <fieldset><legend>뒷받침하는 증거</legend>{incident.evidence.map((item) => <label key={item.id}><input type="checkbox" checked={evidenceIds.includes(item.id)} onChange={(event) => setEvidenceIds((ids) => event.target.checked ? [...ids, item.id] : ids.filter((id) => id !== item.id))} />{item.source} · {item.summary}</label>)}<p>사용 가능한 근거 여부는 서버가 최종 확인합니다.</p></fieldset>}
      {command === "actions" && <><label>기대 효과<input required maxLength={2000} value={effect} onChange={(event) => setEffect(event.target.value)} /></label><label>검증 기준<input required maxLength={2000} value={criteria} onChange={(event) => setCriteria(event.target.value)} /></label></>}
      {command === "verify" && <SelectField label="검증 판정" value={result} options={[{ value: "PASS", label: "통과" }, { value: "FAIL", label: "실패" }, { value: "INCONCLUSIVE", label: "판정 보류" }]} onValueChange={setResult} />}
      {command === "execute" && <p className="preview-notice">매장·담당자가 실제로 수행한 조치만 완료로 기록하세요. 자동 실행이나 외부 API 호출은 없습니다.</p>}
      </fieldset>
      <Button type="submit" disabled={apiMode !== "http" || !permission.allowed || busy}>{busy ? "반영 중…" : commandLabels[command]}</Button>
      {feedback && <p role={feedback.kind === "error" ? "alert" : "status"} className="action-feedback">{feedback.message}</p>}
      {feedback?.code === "CONFLICT" && <Button type="button" onClick={onComplete}>최신 정보 다시 불러오기</Button>}
    </form>
  </article>;
}
