import { useState } from "react";
import { AppShell } from "./AppShell";
import { IncidentList } from "../features/incidents/IncidentList";

export type Route = "dashboard" | "incidents" | "reviews" | "trace" | "integrations" | "queue" | "settings";

export function App() {
  const [route, setRoute] = useState<Route>("dashboard");
  const [incidentId, setIncidentId] = useState<string>();
  const page = route === "incidents" ? <IncidentList onSelect={setIncidentId} /> : <section className="placeholder"><h1>{route === "dashboard" ? "Operations Dashboard" : route[0].toUpperCase() + route.slice(1)}</h1><p>{incidentId ? `선택한 Incident: ${incidentId}` : `ServIQ 운영 콘솔의 ${route} 영역입니다.`}</p></section>;
  return <AppShell route={route} onNavigate={setRoute}>{page}</AppShell>;
}
