"""Bounded investigation attempts; business ledger, not a second Graph runtime."""
from datetime import timedelta

from src.ai.execution.harness import harness_gate
from src.ai.execution.models import HarnessIntent
from src.ai.workflow.models import EvidenceGap, InvestigationResult, RuntimeEvent
from src.ai.workflow.policy import evidence_digest
from src.application.security.principal import AccessError, Principal


class ControlInterrupted(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def control_state(events):
    return next((e.control for e in reversed(events) if e.kind == "CONTROL"), "RUNNING")


class InvestigationLoop:
    def __init__(self, persistence, run_id, tenant_id, source, clock):
        self.persistence, self.run_id, self.tenant_id = persistence, run_id, tenant_id
        self.source, self.clock = source, clock

    def _terminate(self, uow, run, reason):
        loop = run.state.loop.model_copy(update={"termination": reason})
        uow.agent_runs.save(run.model_copy(update={"state": run.state.model_copy(update={"loop": loop})}))

    def execute(self, pack, branch_id, action):
        while True:
            with self.persistence.transaction(self.tenant_id) as uow:
                run = uow.agent_runs.lock(self.run_id)
                if run is None or pack not in run.state.contexts:
                    raise AccessError()
                events = uow.agent_runs.events(self.run_id)
                control = control_state(events)
                if control != "RUNNING":
                    raise ControlInterrupted(control)
                previous = uow.agent_runs.branch(self.run_id, pack.agent_type)
                completed = [e for e in events if e.kind == "RESULT" and e.agent_type == pack.agent_type]
                attempts = [e for e in events if e.kind == "CLAIM" and e.agent_type == pack.agent_type]
                if len(attempts) != len(completed):
                    # Claim without result: the operation might have happened. Never guess/replay it.
                    raise ControlInterrupted("INCOMPLETE")
                if previous and (not previous.retryable or not previous.evidence_gaps):
                    return previous
                if run.state.loop.termination is not None:
                    return previous or self._gap(pack, branch_id)
                attempt = len(attempts)+1
                if attempt > run.state.loop.policy.max_iterations:
                    self._terminate(uow, run, "ITERATION_LIMIT")
                    return previous or self._gap(pack, branch_id)
                incident, version = uow.incidents.get(run.incident_id), uow.configs.current()
                if incident is None or version is None:
                    raise AccessError()
                principal = Principal(run.requested_by or "", run.tenant_id,
                    frozenset(run.delegated_roles), frozenset(run.delegated_store_scope))
                intent = HarnessIntent(agent_run_id=self.run_id, operation=pack.agent_type+"_LOOKUP",
                    context_digest=pack.digest)
                decision = harness_gate(intent, run=run, incident=incident, principal=principal,
                    config=version.config, now=self.clock(), control=control,
                    capabilities=self.source.capabilities(run.tenant_id, pack.store, self.clock()))
                if not version.config.loop_enabled:
                    raise ControlInterrupted("POLICY_DENIED")
                if not decision.allowed:
                    if decision.reason == "AUTHORIZATION_DENIED":
                        raise AccessError()
                    self._terminate(uow, run, "BUDGET_EXHAUSTED" if decision.reason == "BUDGET_EXHAUSTED" else "POLICY_DENIED")
                    return previous or self._gap(pack, branch_id)
                identity = pack.agent_type+":"+str(attempt)
                uow.agent_runs.append_event(self.run_id, RuntimeEvent(event_id=identity+":claim",
                    kind="CLAIM", agent_type=pack.agent_type, attempt=attempt, created_at=self.clock()))
                state = run.state.model_copy(update={"iteration": max(run.state.iteration, attempt),
                    "tool_call_count": run.state.tool_call_count+1})
                uow.agent_runs.save(run.model_copy(update={"state": state}))
            result = action(pack, branch_id)
            with self.persistence.transaction(self.tenant_id) as uow:
                run = uow.agent_runs.lock(self.run_id)
                uow.agent_runs.append_event(self.run_id, RuntimeEvent(event_id=identity+":result",
                    kind="RESULT", agent_type=pack.agent_type, attempt=attempt,
                    result=result, created_at=self.clock()))
                before = tuple(e.source_ref for e in previous.evidence_candidates) if previous else ()
                refs = tuple(e.source_ref for e in result.evidence_candidates)
                loop = run.state.loop.model_copy(update={"evidence_digest": evidence_digest(refs),
                    "new_evidence": bool(set(refs)-set(before))})
                run = uow.agent_runs.save(run.model_copy(update={"state": run.state.model_copy(update={"loop": loop})}))
                if attempt > 1 and not set(refs)-set(before):
                    self._terminate(uow, run, "NO_NEW_EVIDENCE")
                    return result
                if not result.retryable or not result.evidence_gaps:
                    return result
            # Only unsuccessful, retryable branches with a real gap can reach the next attempt.

    def _gap(self, pack, branch_id):
        now = self.clock()
        return InvestigationResult(agent_type=pack.agent_type, branch_id=branch_id,
            tenant_id=pack.tenant_id, incident_id=pack.incident_id, store=pack.store,
            status="UNAVAILABLE", evidence_gaps=(EvidenceGap(code="BRANCH_BUDGET_EXHAUSTED", agent_type=pack.agent_type),),
            started_at=now, completed_at=now, context_digest=pack.digest, uncertainty="MISSING_EVIDENCE")

    def deadline(self, run):
        return run.started_at+timedelta(seconds=run.state.loop.policy.timeout_seconds)
