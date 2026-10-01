import { useState } from "react";
import { AppShell } from "./AppShell";

export type Route = "dashboard" | "incidents" | "reviews" | "trace" | "integrations" | "queue" | "settings";

export function App() {
  const [route, setRoute] = useState<Route>("dashboard");
  return <AppShell route={route} onNavigate={setRoute}><section className="placeholder"><h1>{route === "dashboard" ? "Operations Dashboard" : route[0].toUpperCase() + route.slice(1)}</h1><p>ServIQ 운영 콘솔의 {route} 영역입니다.</p></section></AppShell>;
}
