"""Actual source timestamps/usage only. Product feedback is not an Approval command."""
from datetime import UTC, datetime
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from src.ai.ax.models import AXMetric, ProductEvent
from src.application.incidents.service import IncidentNotFound
from src.application.security.authorization import require
from src.application.security.principal import AccessError


def metrics(incident, run, steps=(), events=(), approval=None):
    started = datetime.fromisoformat(incident.created_at)
    evidence_times = [s.completed_at for s in steps if s.evidence_refs and s.completed_at >= started]
    decided = datetime.fromisoformat(approval.decided_at) if approval and approval.decided_at else None
    controls = [e for e in events if e.kind == "CONTROL"]
    complete = bool(run and run.status == "COMPLETED" and run.state.verification)
    def metric(name, value, unit, partial=False):
        return AXMetric(name=name, value=value, unit=unit,
            status="UNAVAILABLE" if value is None else "PARTIAL" if partial else "AVAILABLE")
    return (
        metric("end_to_end_completion", float(complete) if run else None, "boolean"),
        metric("time_to_first_useful_evidence", (min(evidence_times)-started).total_seconds() if evidence_times else None, "seconds"),
        metric("time_to_decision", (decided-started).total_seconds() if decided and decided >= started else None, "seconds"),
        metric("human_intervention", len(controls)+int(decided is not None) if run else None, "count", partial=True),
        metric("manual_takeover", float(any(e.control == "MANUAL_TAKEOVER" for e in controls)) if run else None, "boolean"),
        metric("loop_abort", float(run.state.loop.termination not in {None, "COMPLETED"}) if run and run.state.loop else None, "boolean"),
        metric("cost_per_completed_incident", run.state.cost_spent if complete else None, "estimated_usd", partial=True),
    )


class ProductEvents:
    def __init__(self, persistence, clock=None):
        self.persistence, self.clock = persistence, clock or (lambda: datetime.now(UTC))

    def record(self, context, incident_id, event_type):
        principal = context.principal
        require(principal, "read")
        if not context.idempotency_key:
            raise AccessError("IDEMPOTENCY_KEY_REQUIRED", 422)
        with self.persistence.transaction(principal.tenant_id) as uow:
            incident = uow.incidents.get(incident_id)
            if incident is None:
                raise IncidentNotFound()
            require(principal, "read", incident.store)
            feedback = event_type.startswith("recommendation_")
            if feedback:
                require(principal, "operate", incident.store)
            fingerprint = sha256((incident_id+":"+event_type).encode()).hexdigest()
            previous = uow.idempotency.claim(principal.principal_id, "ax_product_event", context.idempotency_key, fingerprint)
            if previous is not None:
                return previous
            runs = uow.agent_runs.history(incident_id, 1, 0)
            run = runs[0] if runs else None
            if feedback and (run is None or not run.state.rca_candidates):
                raise AccessError("AX_FEEDBACK_NOT_AVAILABLE", 409)
            event = ProductEvent(event_id=str(uuid5(NAMESPACE_URL, sha256(
                repr((principal.tenant_id, principal.principal_id, context.idempotency_key)).encode()).hexdigest())),
                tenant_id=principal.tenant_id, incident_id=incident_id, source_run_id=run.agent_run_id if run else None,
                event_type=event_type, occurred_at=self.clock(), feedback_stage="RAW" if feedback else None)
            uow.product_events.append(event)
            uow.idempotency.complete(principal.principal_id, "ax_product_event", context.idempotency_key, event)
            return event
