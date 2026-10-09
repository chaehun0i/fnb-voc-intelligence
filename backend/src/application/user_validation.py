"""Opt-in task observation; reuses AX, ProductEvent, security and transactional stores."""
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import Field, model_validator

from src.ai.ax.measurement import validation_metrics
from src.ai.ax.models import (
    Friction,
    ProductEvent,
    SafeModel,
    ValidationReason,
    ValidationSurface,
)
from src.ai.ax.service import IncidentAXQueries
from src.ai.ax.validation import (
    Milestone,
    Scenario,
    ValidationSession,
    project_journey,
    validation_task,
)
from src.application.data_intake import DataIntake
from src.application.incidents.service import IncidentNotFound
from src.application.security.authorization import require
from src.application.security.principal import AccessError


class ValidationSignal(SafeModel):
    milestone: Milestone | None = None
    friction: Friction | None = None
    surface: ValidationSurface
    safe_reason_code: ValidationReason | None = None
    incident_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def not_empty(self):
        if self.milestone is None and self.friction is None:
            raise ValueError("VALIDATION_SIGNAL_REQUIRED")
        return self


class UserValidation:
    def __init__(self, persistence, context, clock=None):
        self.persistence, self.context = persistence, context
        self.clock = clock or (lambda: datetime.now(UTC))

    def owner(self):
        p = self.context.principal
        return hashlib.sha256(json.dumps([p.tenant_id, p.principal_id]).encode()).hexdigest()

    def claim(self, uow, operation, body):
        c = self.context
        if not c.idempotency_key:
            raise AccessError("IDEMPOTENCY_KEY_REQUIRED", 422)
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        return uow.idempotency.claim(c.principal.principal_id, operation, c.idempotency_key, digest)

    def complete(self, uow, operation, value):
        c = self.context
        uow.idempotency.complete(c.principal.principal_id, operation, c.idempotency_key, value)
        return value

    def load(self, uow, identifier, *, write=False):
        row = uow.product_events.get_session(identifier, lock=write)
        if row is None:
            raise IncidentNotFound()
        s, owner = row
        p = self.context.principal
        require(p, "operate" if write else "read", s.store_id)
        if owner != self.owner():
            raise AccessError("VALIDATION_SESSION_OWNER_REQUIRED", 403)
        return s

    def start(self, store, scenario: Scenario, *, consent, kind="USER_OBSERVATION"):
        p = self.context.principal
        require(p, "operate", store)
        if not consent:
            raise AccessError("VALIDATION_CONSENT_REQUIRED", 422)
        if store not in DataIntake(self.persistence, self.context).status()["stores"]:
            raise IncidentNotFound()
        with self.persistence.transaction(p.tenant_id) as uow:
            cached = self.claim(uow, "validation_start", [store, scenario, kind])
            if cached is not None:
                return cached
            now = self.clock()
            item = ValidationSession(session_id=uuid4(), tenant_id=p.tenant_id, store_id=store,
                scenario_id=scenario, participant_ref=uuid4(), started_at=now, created_at=now,
                validation_kind=kind)
            uow.product_events.save_session(item, self.owner())
            return self.complete(uow, "validation_start", item)

    def get(self, identifier):
        with self.persistence.transaction(self.context.principal.tenant_id) as uow:
            item = self.load(uow, identifier)
        row = self.observation(item)
        return {"session": item, "task": validation_task(item.scenario_id),
            "journey": row["journey"], "event_limit_reached": len(row["events"]) >= 500}

    def observation(self, item):
        with self.persistence.transaction(self.context.principal.tenant_id) as uow:
            events = uow.product_events.session_events(item.session_id)
            decision_at = self.decision_time(uow, item)
            steps = uow.agent_runs.steps(item.agent_run_id) if item.agent_run_id else ()
            evidence_times = [s.completed_at for s in steps if s.evidence_refs and s.completed_at >= item.started_at]
        ax = IncidentAXQueries(self.persistence, self.context, self.clock).get(item.incident_id) if item.incident_id else None
        return {"session": item, "events": events, "ax": ax,
            "journey": project_journey(item, events, ax, decision_at),
            "first_evidence_at": min(evidence_times, default=None)}

    def summary(self, store, kind):
        require(self.context.principal, "admin", store)
        now = self.clock()
        with self.persistence.transaction(self.context.principal.tenant_id) as uow:
            items = uow.product_events.sessions(store)
        scoped = [s for s in items[:100] if s.validation_kind == kind and s.started_at >= now-timedelta(days=7)]
        rows = [self.observation(s) for s in scoped]
        truncated = len(items) > 100 or any(len(row["events"]) >= 500 for row in rows)
        friction = Counter(e.friction for row in rows for e in row["events"] if e.friction)
        return {"validation_kind": kind, "window": "7d", "window_started_at": now-timedelta(days=7),
            "window_ended_at": now, "sessions": len(scoped),
            "completed": sum(s.status == "COMPLETED" for s in scoped),
            "abandoned": sum(s.status == "ABANDONED" for s in scoped), "truncated": truncated,
            "metrics": validation_metrics(rows, truncated=truncated),
            "top_friction": [{"reason": name, "count": count} for name, count in sorted(friction.items(), key=lambda v: (-v[1], v[0]))],
            "recent_sessions": [{"session_id": s.session_id, "scenario_id": s.scenario_id,
                "status": s.status, "started_at": s.started_at} for s in scoped[:20]]}

    def finish(self, identifier):
        with self.persistence.transaction(self.context.principal.tenant_id) as uow:
            item = self.load(uow, identifier, write=True)
            cached = self.claim(uow, "validation_finish", [str(identifier)])
            if cached is not None:
                return cached
            if item.status != "ACTIVE" or not self.observation(item)["journey"].task_success:
                raise AccessError("VALIDATION_TASK_NOT_COMPLETE", 409)
            item = item.model_copy(update={"status": "COMPLETED", "completed_at": self.clock()})
            uow.product_events.save_session(item, self.owner())
            return self.complete(uow, "validation_finish", item)

    def decision_time(self, uow, item):
        if not item.incident_id:
            return None
        dates = [datetime.fromisoformat(a.decided_at) for a in uow.approvals.list(item.incident_id)
            if a.decided_at and a.decided_by == self.context.principal.principal_id]
        return min((at for at in dates if at >= item.started_at), default=None)

    def signal(self, identifier, body):
        p = self.context.principal
        with self.persistence.transaction(p.tenant_id) as uow:
            item = self.load(uow, identifier, write=True)
            payload = body.model_dump(mode="json")
            cached = self.claim(uow, "validation_signal", [str(identifier), payload])
            if cached is not None:
                return cached
            if item.status != "ACTIVE":
                raise AccessError("VALIDATION_SESSION_TERMINAL", 409)
            if len(uow.product_events.session_events(identifier)) >= 500:
                raise AccessError("VALIDATION_EVENT_LIMIT", 429)
            if body.incident_id:
                incident = uow.incidents.get(body.incident_id)
                if incident is None:
                    raise IncidentNotFound()
                require(p, "operate", incident.store)
                if incident.store != item.store_id or item.incident_id not in {None, incident.id}:
                    raise AccessError("VALIDATION_INCIDENT_SCOPE", 403)
                item = item.model_copy(update={"incident_id": incident.id})
            run = None
            if item.incident_id:
                runs = uow.agent_runs.history(item.incident_id, 1, 0)
                run = runs[0] if runs else None
                if item.agent_run_id and run and item.agent_run_id != run.agent_run_id:
                    raise AccessError("VALIDATION_RUN_CHANGED", 409)
                if run:
                    item = item.model_copy(update={"agent_run_id": run.agent_run_id})
            # Never accept a click as an actual Review decision.
            if body.milestone == "DECISION_SUBMITTED" and self.decision_time(uow, item) is None:
                raise AccessError("VALIDATION_DECISION_NOT_RECORDED", 409)
            if body.milestone == "DATA_READY":
                has_data = bool(uow.incidents.list(store=item.store_id) or
                    any(i["store"] == item.store_id for i in uow.intake.list("IMPORT")))
                if not has_data:
                    raise AccessError("VALIDATION_DATA_NOT_READY", 409)
            if body.milestone in {"INCIDENT_OPENED", "REVIEW_OPENED", "FINAL_STATUS_VIEWED"} and not item.incident_id:
                raise AccessError("VALIDATION_INCIDENT_REQUIRED", 409)
            now = self.clock()
            event = ProductEvent(event_id=str(uuid5(NAMESPACE_URL, self.owner()+":validation:"+self.context.idempotency_key)),
                tenant_id=p.tenant_id, incident_id=item.incident_id or "", source_run_id=item.agent_run_id,
                event_type="user_validation", session_id=item.session_id, task_id="incident-understanding",
                occurred_at=now, milestone=body.milestone, friction=body.friction,
                surface=body.surface, safe_reason_code=body.safe_reason_code)
            if body.friction == "TASK_ABANDONED":
                item = item.model_copy(update={"status": "ABANDONED", "completed_at": now})
            uow.product_events.save_session(item, self.owner())
            uow.product_events.append(event)
            return self.complete(uow, "validation_signal", event)
