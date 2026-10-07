"""Human controls share tenant/auth/idempotency/audit and the operation-start row lock."""
import hashlib
import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from src.ai.workflow.controller import control_state
from src.ai.workflow.models import RuntimeEvent
from src.ai.workflow.policy import validate_manifest
from src.application.incidents.service import IncidentNotFound
from src.application.security.authorization import require
from src.application.security.principal import AccessError
from src.domain.approvals.audit import AuditRecord
from src.domain.jobs.models import Job

CONTINUE_JOB = "incident.investigation_continue"
CONTROL_TARGET = {"pause": "PAUSED", "resume": "RUNNING", "stop": "STOPPED", "takeover": "MANUAL_TAKEOVER"}


class AgentControls:
    def __init__(self, persistence, clock=None):
        self.persistence, self.clock = persistence, clock or (lambda: datetime.now(UTC))

    def execute(self, context, incident_id, run_id, action, expected_version):
        principal = context.principal
        require(principal, "operate")
        if action not in CONTROL_TARGET or type(expected_version) is not int or expected_version < 0:
            raise AccessError("VALIDATION_ERROR", 422)
        if context.idempotency_key is None:
            raise AccessError("IDEMPOTENCY_KEY_REQUIRED", 422)
        with self.persistence.transaction(principal.tenant_id) as uow:
            incident = uow.incidents.get(incident_id)
            if incident is None:
                raise IncidentNotFound()
            require(principal, "operate", incident.store)
            run = uow.agent_runs.lock(run_id)
            if run is None or run.incident_id != incident_id:
                raise IncidentNotFound()
            operation = "agent_"+action
            fingerprint = hashlib.sha256(json.dumps([incident_id, run_id, action, expected_version]).encode()).hexdigest()
            replay = uow.idempotency.claim(principal.principal_id, operation, context.idempotency_key, fingerprint)
            if replay is not None:
                return replay
            events = uow.agent_runs.events(run_id)
            controls = [e for e in events if e.kind == "CONTROL"]
            current = control_state(events)
            if len(controls) != expected_version:
                raise AccessError("AGENT_CONTROL_CONFLICT", 409)
            if run.state.loop is None or run.status in {"COMPLETED", "FAILED"}:
                raise AccessError("AGENT_CONTROL_NOT_ALLOWED", 409)
            valid = current == "PAUSED" if action == "resume" else current == "RUNNING" if action == "pause" else current in {"RUNNING", "PAUSED"}
            if not valid:
                raise AccessError("AGENT_CONTROL_NOT_ALLOWED", 409)
            target = CONTROL_TARGET[action]
            identity = str(uuid5(NAMESPACE_URL, run_id+":"+str(len(controls)+1)))
            if action == "resume":
                validate_manifest(run)
                config = uow.configs.current()
                if config is None or not config.config.loop_enabled or not config.config.auto_investigation:
                    raise AccessError("AGENT_POLICY_DENIED", 409)
                require(principal, "operate", incident.store)
                if uow.agent_runs.automation_blocked(incident_id):
                    raise AccessError("AGENT_CONTROL_NOT_ALLOWED", 409)
                loop = run.state.loop.model_copy(update={"termination": None})
                uow.agent_runs.save(run.model_copy(update={"state": run.state.model_copy(update={"loop": loop})}))
                original = uow.jobs.get(run.job_id)
                if original is None:
                    raise AccessError("AGENT_CONTROL_NOT_ALLOWED", 409)
                uow.jobs.save(Job(identity, run.tenant_id, CONTINUE_JOB, context.correlation_id,
                    self.clock(), self.clock(), incident_id=incident_id, store=incident.store,
                    payload_ref=run_id, parent_job_id=run.job_id, config_version=run.config_version,
                    max_attempts=original.max_attempts))
            event = RuntimeEvent(event_id=identity, kind="CONTROL", control=target,
                actor_id=principal.principal_id, created_at=self.clock(),
                reason=target if target != "RUNNING" else None)
            uow.agent_runs.append_event(run_id, event)
            uow.audit.append(AuditRecord(identity, run.tenant_id, principal.principal_id,
                operation, "agent_run", run_id, "SUCCESS", context.request_id, context.correlation_id,
                self.clock().isoformat(), incident.version))
            uow.idempotency.complete(principal.principal_id, operation, context.idempotency_key, event)
            return event
