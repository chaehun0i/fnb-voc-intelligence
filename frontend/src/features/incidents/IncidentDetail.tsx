import { useEffect, useState } from "react";
import { mockApi } from "../../api/mockApi";
import type { Incident } from "../../contracts/types";
import { Badge } from "./IncidentList";

export function IncidentDetail({ id, onBack }: { id:string; onBack:()=>void }) { const [incident,setIncident]=useState<Incident>(); useEffect(()=>{void mockApi.getIncident(id).then(setIncident)},[id]); if (!incident) return <section>Loading incident…</section>; return <section><button onClick={onBack}>← Incidents</button><h1>{incident.display_id}: {incident.title}</h1><div className="metadata"><span><Badge value={incident.severity}/></span><span>{incident.status}</span><span>Store: {incident.store}</span><span>Owner: {incident.owner}</span><span>Detected: {new Date(incident.created_at).toLocaleString()}</span></div><h2>Status timeline</h2><ol className="timeline">{incident.timeline.map(event=><li key={event.occurred_at}><strong>{event.status}</strong><small>{new Date(event.occurred_at).toLocaleString()}</small></li>)}</ol></section> }
