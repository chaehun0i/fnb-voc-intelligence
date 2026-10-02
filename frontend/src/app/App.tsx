import { useState } from "react";
import { AppShell } from "./AppShell";
import { Dashboard } from "../features/dashboard/Dashboard";
import { IncidentList } from "../features/incidents/IncidentList";
import { IncidentDetail } from "../features/incidents/IncidentDetail";
import { ReviewQueue } from "../features/reviews/ReviewQueue";
import { AgentTrace } from "../features/trace/AgentTrace";
import { ControlPlaneSettings } from "../features/settings/ControlPlaneSettings";
import { Integrations } from "../features/operations/Integrations";
import { Queue } from "../features/operations/Queue";

export type Route = "dashboard" | "incidents" | "reviews" | "trace" | "integrations" | "queue" | "settings";
export function App() {
  const [route, setRoute] = useState<Route>("dashboard");
  const [incidentId, setIncidentId] = useState<string>();
  const [refresh, setRefresh] = useState(0);
  const navigate = (next: Route) => { setIncidentId(undefined); setRoute(next); };
  return <AppShell route={route} onNavigate={navigate}>
    {route === "dashboard" && <Dashboard onIncidents={() => navigate("incidents")} onReviews={() => navigate("reviews")} onQueue={() => navigate("queue")} onIncident={setIncidentId} />}
    {route === "incidents" && <IncidentList onSelect={setIncidentId} refresh={refresh} />}
    {route === "reviews" && <ReviewQueue />}{route === "trace" && <AgentTrace />}{route === "settings" && <ControlPlaneSettings />}{route === "integrations" && <Integrations />}{route === "queue" && <Queue />}
    {incidentId && <IncidentDetail key={incidentId} id={incidentId} onBack={() => { setIncidentId(undefined); setRefresh((value) => value + 1); }} />}
  </AppShell>;
}
