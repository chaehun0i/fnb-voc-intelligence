import type { ReactNode } from "react";
import type { Route } from "./App";

const navigation: Array<[Route, string]> = [["dashboard", "Dashboard"], ["incidents", "Incidents"], ["reviews", "Reviews"], ["trace", "Agent Trace"], ["integrations", "Integrations"], ["queue", "Queue"], ["settings", "Settings"]];

export function AppShell({ route, onNavigate, children }: { route: Route; onNavigate: (route: Route) => void; children: ReactNode }) {
  return <div className="app-shell"><aside><div className="brand">ServIQ <small>v0.4.1</small></div><nav>{navigation.map(([id, label]) => <button key={id} className={route === id ? "active" : ""} onClick={() => onNavigate(id)}>{label}</button>)}</nav></aside><main className="content"><header><span>Control Plane</span><strong>Operations Console</strong></header>{children}</main></div>;
}
