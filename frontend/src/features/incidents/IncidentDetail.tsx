import { useEffect, useState } from "react";
import { mockApi } from "../../api/mockApi";
import type { Incident } from "../../contracts/types";
import { Badge } from "./IncidentList";

export function IncidentDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const [incident, setIncident] = useState<Incident>();
  useEffect(() => { void mockApi.getIncident(id).then(setIncident); }, [id]);
  if (!incident) return <section>Loading incident...</section>;
  return <section><button onClick={onBack}>Back to incidents</button><h1>{incident.display_id}: {incident.title}</h1><div className="metadata"><Badge value={incident.severity}/><span>{incident.status}</span><span>Store: {incident.store}</span><span>Owner: {incident.owner}</span><span>Detected: {new Date(incident.created_at).toLocaleString()}</span></div><h2>Status timeline</h2><ol className="timeline">{incident.timeline.map(event => <li key={event.occurred_at}><strong>{event.status}</strong><small>{new Date(event.occurred_at).toLocaleString()}</small></li>)}</ol><div className="panels"><article><h2>Evidence</h2>{incident.evidence.map(e => <p key={e.id}><strong>{e.source}</strong> / {e.type} / {e.summary} ({e.confidence})</p>)}</article><article><h2>Root Cause Analysis</h2>{incident.root_cause_candidates.map(r => <p key={r.id}>{r.summary} / confidence {r.confidence}<br/>Supporting: {r.supporting_evidence_ids.join(", ") || "None"}<br/>Counter: {r.counter_evidence_ids.join(", ") || "None"}</p>)}</article><article><h2>CAPA</h2>{incident.corrective_actions.map(c => <p key={c.id}><strong>{c.summary}</strong> / risk {c.risk_level}<br/>Effect: {c.expected_effect}<br/>Criteria: {c.verification_criteria}</p>)}</article><article><h2>Verification</h2><p>{incident.verification?.result ?? "INCONCLUSIVE"}: {incident.verification?.summary ?? "Not verified"}</p></article></div></section>;
}
