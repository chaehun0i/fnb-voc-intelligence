"""Fixed operation metadata + deterministic gate; no MCP/SDK or arbitrary executor."""
from datetime import timedelta

from src.ai.execution.models import HarnessDecision, HarnessIntent
from src.application.security.authorization import allowed

READ_OPERATIONS = {
    "HISTORY_LOOKUP": ("HISTORY", "voc.search", "HISTORY_DATA"),
    "TRANSACTION_LOOKUP": ("TRANSACTION", "transaction.search", "TRANSACTION_DATA"),
    "INVENTORY_LOOKUP": ("INVENTORY", "inventory.snapshot", "INVENTORY_DATA"),
}


def harness_gate(intent, *, run, incident, principal, config, now, capabilities=(),
                 control="RUNNING", cached=False, approval_valid=False):
    intent = HarnessIntent.model_validate(intent.model_dump())
    read = READ_OPERATIONS.get(intent.operation)
    risk = "LOW" if read else "HIGH" if intent.operation == "INTERNAL_EXECUTION" else "MEDIUM"
    reason = "ALLOWED"
    if (intent.agent_run_id != run.agent_run_id or principal.tenant_id != run.tenant_id
            or incident.tenant_id != run.tenant_id or incident.id != run.incident_id
            or not allowed(principal, "operate", incident.store)):
        reason = "AUTHORIZATION_DENIED"
    elif not run.manifest:
        reason = "MANIFEST_INCOMPATIBLE"
    elif control != "RUNNING":
        reason = control if control in {"PAUSED", "STOPPED", "MANUAL_TAKEOVER"} else "POLICY_DENIED"
    elif (not config.auto_investigation or (run.state.selection and not config.multi_agent_enabled)
            or (run.state.loop is not None and not config.loop_enabled)):
        reason = "POLICY_DENIED"
    elif read:
        agent, tool, capability = read
        pack = next((c for c in run.state.contexts if c.agent_type == agent), None)
        if (agent not in config.allowed_agent_types or tool not in config.allowed_tools
                or (run.state.selection is not None and pack is None)
                or (pack and (pack.store != incident.store or pack.category in config.blocked_categories
                    or pack.digest != intent.context_digest))):
            reason = "POLICY_DENIED"
        elif any(c.tenant_id != run.tenant_id or c.store != incident.store for c in capabilities):
            reason = "AUTHORIZATION_DENIED"
        elif not cached and not any(c.capability == capability and c.available
                and c.health == "HEALTHY" and c.freshness == "FRESH"
                and timedelta(0) <= now-c.checked_at <= timedelta(minutes=5) for c in capabilities):
            reason = "CAPABILITY_UNAVAILABLE"
    elif ((intent.operation == "RCA_DRAFT" and not config.auto_rca_draft)
            or (intent.operation in {"CAPA_DRAFT", "CAPA_APPLY", "APPROVAL_REQUEST"} and not config.auto_capa_draft)):
        reason = "POLICY_DENIED"
    elif intent.operation == "INTERNAL_EXECUTION" and (not config.internal_execution_enabled or not approval_valid):
        reason = "APPROVAL_REQUIRED"
    if reason == "ALLOWED" and cached:
        reason = "REPLAY_CACHED"
    elif reason == "ALLOWED" and run.state.loop:
        policy, state = run.state.loop.policy, run.state
        if (now-run.started_at >= timedelta(seconds=min(policy.timeout_seconds, config.timeout_seconds))
                or state.token_spent >= min(policy.token_budget, config.token_budget)
                or state.cost_spent >= min(policy.cost_budget, config.cost_budget_usd)
                or (read and state.tool_call_count >= min(policy.max_operations, config.max_tool_calls))):
            reason = "BUDGET_EXHAUSTED"
    return HarnessDecision(agent_run_id=run.agent_run_id, operation=intent.operation,
        allowed=reason in {"ALLOWED", "REPLAY_CACHED"}, reason=reason, risk=risk)
