import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { createIncident, type IncidentCreateInput } from "../../api/incidents";
import { SelectField } from "../../components/SelectField";
import { Button } from "../../components/ui";
import { severityLabels } from "../../lib/display";

export function CreateIncident({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [input, setInput] = useState<IncidentCreateInput>({ title: "", severity: "MEDIUM", store: "", owner: "", priority: "P2" });
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit(event: React.FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { const incident = await createIncident(input); onCreated(incident.id); } catch (error) { setError(error instanceof Error ? error.message : "등록하지 못했습니다."); } finally { setBusy(false); } }
  return <Dialog.Root open onOpenChange={(open) => { if (!open && !busy) onClose(); }}><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="dialog-content create-dialog"><header className="dialog-header"><Dialog.Title>인시던트 등록</Dialog.Title><Dialog.Close className="dialog-close" disabled={busy} aria-label="등록 팝업 닫기"><X size={19} /></Dialog.Close></header><div className="page"><Dialog.Description>접수한 운영 이슈를 등록하면 서버가 최초 상태와 SLA를 기록합니다.</Dialog.Description><form className="command-form" onSubmit={(event) => { void submit(event); }}>
    <label>제목<input required maxLength={2000} value={input.title} onChange={(event) => setInput({ ...input, title: event.target.value })} /></label><label>매장<input required maxLength={100} value={input.store} onChange={(event) => setInput({ ...input, store: event.target.value })} /></label><label>담당자<input required maxLength={100} value={input.owner} onChange={(event) => setInput({ ...input, owner: event.target.value })} /></label>
    <SelectField label="신규 인시던트 심각도" value={input.severity} options={Object.entries(severityLabels).map(([value, label]) => ({ value, label }))} onValueChange={(severity) => setInput({ ...input, severity: severity as IncidentCreateInput["severity"] })} />
    <SelectField label="신규 인시던트 우선순위" value={input.priority} options={[{ value: "P1", label: "P1 · 최우선" }, { value: "P2", label: "P2 · 일반" }, { value: "P3", label: "P3 · 낮음" }]} onValueChange={(priority) => setInput({ ...input, priority: priority as IncidentCreateInput["priority"] })} />
    <Button disabled={busy} type="submit">{busy ? "등록 중…" : "등록"}</Button>{error && <p role="alert">{error}</p>}
  </form></div></Dialog.Content></Dialog.Portal></Dialog.Root>;
}
