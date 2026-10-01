import { useEffect, useState } from "react";
import { mockApi } from "../../api/mockApi";
import type { AgentRun } from "../../contracts/types";

export function AgentTrace() { const [run,setRun]=useState<AgentRun>(); useEffect(()=>{void mockApi.getAgentRun().then(setRun)},[]); if(!run)return <section>Loading trace...</section>; return <section><h1>Agent Trace</h1><p>Run {run.id} / {run.status}</p><table><thead><tr><th>Step</th><th>Status</th><th>Latency</th><th>Retries</th><th>Tokens</th><th>Cost</th><th>Tool calls</th><th>Decision summary</th></tr></thead><tbody>{run.steps.map(s=><tr key={s.id}><td>{s.name}</td><td>{s.status}</td><td>{s.latency_ms}ms</td><td>{s.retry_count}</td><td>{s.token_usage}</td><td>${s.cost_usd.toFixed(3)}</td><td>{s.tool_calls.map(t=>`${t.name} (${t.status})`).join(", ") || "-"}</td><td>{s.decision_summary}</td></tr>)}</tbody></table></section> }
