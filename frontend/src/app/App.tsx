import { lazy, Suspense, useEffect, useState } from "react";
import { AppShell } from "./AppShell";
import { PageErrorBoundary } from "../components/PageErrorBoundary";
import { StateMessage } from "../components/ui";

const Dashboard = lazy(() => import("../features/dashboard/Dashboard").then((module) => ({ default: module.Dashboard })));
const IncidentList = lazy(() => import("../features/incidents/IncidentList").then((module) => ({ default: module.IncidentList })));
const IncidentDetail = lazy(() => import("../features/incidents/IncidentDetail").then((module) => ({ default: module.IncidentDetail })));
const ReviewQueue = lazy(() => import("../features/reviews/ReviewQueue").then((module) => ({ default: module.ReviewQueue })));
const AgentTrace = lazy(() => import("../features/trace/AgentTrace").then((module) => ({ default: module.AgentTrace })));
const ControlPlaneSettings = lazy(() => import("../features/settings/ControlPlaneSettings").then((module) => ({ default: module.ControlPlaneSettings })));
const Integrations = lazy(() => import("../features/operations/Integrations").then((module) => ({ default: module.Integrations })));
const Queue = lazy(() => import("../features/operations/Queue").then((module) => ({ default: module.Queue })));

export type Route = "dashboard" | "incidents" | "reviews" | "trace" | "integrations" | "queue" | "settings";
const routes: Route[] = ["dashboard", "incidents", "reviews", "trace", "integrations", "queue", "settings"];
function currentPage(): { route: Route; incidentId?: string } {
  const [path, query] = window.location.hash.replace(/^#\/?/, "").split("?");
  return { route: routes.includes(path as Route) ? path as Route : "dashboard", incidentId: new URLSearchParams(query).get("incident") ?? undefined };
}
export function App() {
  const [page, setPage] = useState(currentPage);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => { const update = () => { setPage(currentPage()); setRefresh((value) => value + 1); }; window.addEventListener("hashchange", update); return () => window.removeEventListener("hashchange", update); }, []);
  function navigate(route: Route, incidentId?: string) {
    const next = { route, incidentId }; setPage(next);
    window.location.hash = `/${route}${incidentId ? `?incident=${encodeURIComponent(incidentId)}` : ""}`;
  }
  const selectIncident = (id: string) => navigate(page.route, id);
  return <AppShell route={page.route} onNavigate={(route) => navigate(route)}><PageErrorBoundary key={page.route}><Suspense fallback={<section className="page"><StateMessage kind="loading" title="화면을 준비하는 중입니다" /></section>}>
    {page.route === "dashboard" && <Dashboard onIncidents={() => navigate("incidents")} onReviews={() => navigate("reviews")} onQueue={() => navigate("queue")} onIncident={selectIncident} />}
    {page.route === "incidents" && <IncidentList onSelect={selectIncident} refresh={refresh} />}
    {page.route === "reviews" && <ReviewQueue />}{page.route === "trace" && <AgentTrace />}{page.route === "settings" && <ControlPlaneSettings />}{page.route === "integrations" && <Integrations />}{page.route === "queue" && <Queue />}
    {page.incidentId && <IncidentDetail key={page.incidentId} id={page.incidentId} onBack={() => { navigate(page.route); setRefresh((value) => value + 1); }} />}
  </Suspense></PageErrorBoundary></AppShell>;
}
