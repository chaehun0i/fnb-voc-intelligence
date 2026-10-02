import type { IncidentStatus, Severity } from "../contracts/types";
import { severityLabels, statusLabels } from "../lib/display";

export function Badge({ value, kind = "severity" }: { value: string; kind?: "severity" | "status" }) {
  const label = kind === "status" ? statusLabels[value as IncidentStatus] : severityLabels[value as Severity];
  return <span className={`tag ${kind === "status" ? "status" : value.toLowerCase()}`}>{label ?? value}</span>;
}
