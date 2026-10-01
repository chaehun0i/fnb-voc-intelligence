import { useState } from "react";
import { AppShell } from "./AppShell";
import { IncidentList } from "../features/incidents/IncidentList";
import { IncidentDetail } from "../features/incidents/IncidentDetail";
import { ReviewQueue } from "../features/reviews/ReviewQueue";
import { AgentTrace } from "../features/trace/AgentTrace";
import { ControlPlaneSettings } from "../features/settings/ControlPlaneSettings";

export type Route = "dashboard" | "incidents" | "reviews" | "trace" | "integrations" | "queue" | "settings";

export function App() {
  const [route, setRoute] = useState<Route>("dashboard");
  const [incidentId, setIncidentId] = useState<string>();
  const page = route === "incidents" ? (incidentId ? <IncidentDetail id={incidentId} onBack={()=>setIncidentId(undefined)} /> : <IncidentList onSelect={setIncidentId} />) : route === "reviews" ? <ReviewQueue /> : route === "trace" ? <AgentTrace /> : route === "settings" ? <ControlPlaneSettings /> : <section className="placeholder"><h1>{route === "dashboard" ? "Operations Dashboard" : route[0].toUpperCase() + route.slice(1)}</h1><p>ServIQ operations console.</p></section>;
  return <AppShell route={route} onNavigate={setRoute}>{page}</AppShell>;
}
