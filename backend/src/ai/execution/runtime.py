"""Bound server session: Registry -> existing Harness -> Application query.

The model supplies only ToolInput. Identity, delegation and scope are loaded from
the current run, never accepted as tool arguments or MCP transport metadata.
"""
from hashlib import sha256
from uuid import uuid4

from src.ai.execution.harness import harness_gate
from src.ai.execution.models import HarnessIntent
from src.ai.execution.tools import (
    READ_TOOLS,
    ToolCall,
    ToolExecutionContext,
    ToolFailure,
    ToolInput,
    tool_error,
)
from src.application.incidents.service import IncidentNotFound
from src.application.security.principal import AccessError, Principal
from src.application.tool_queries import BusinessToolQueries


class ToolHarness:
    def __init__(self, persistence, source, *, tenant_id, run_id, agent_type, clock):
        self.persistence, self.source = persistence, source
        self.tenant_id, self.run_id, self.agent_type = tenant_id, run_id, agent_type
        self.clock = clock

    def execute(self, name, arguments):
        from src.ai.workflow.controller import control_state
        from src.ai.workflow.models import RuntimeEvent
        from src.ai.workflow.policy import validate_manifest

        try:
            contract = READ_TOOLS.resolve(name)
            arguments = ToolInput.model_validate(arguments)
        except ValueError:
            raise ToolFailure(tool_error("INVALID_CONTRACT")) from None
        with self.persistence.transaction(self.tenant_id) as uow:
            run = uow.agent_runs.lock(self.run_id)
            if run is None:
                raise IncidentNotFound()
            validate_manifest(run)
            pack = next((p for p in run.state.contexts if p.agent_type == self.agent_type), None)
            if (pack is None or contract.agent_type != self.agent_type
                    or arguments.incident_id != run.incident_id):
                raise AccessError()
            if run.state.tool_runtime_enabled and (not run.manifest
                    or (contract.name, contract.version) not in run.manifest.tool_versions
                    or READ_TOOLS.version not in run.manifest.tool_bundle_versions):
                raise ToolFailure(tool_error("POLICY_DENIED"))
            incident, version = uow.incidents.get(run.incident_id), uow.configs.current()
            if incident is None or version is None:
                raise AccessError()
            principal = Principal(run.requested_by or "", run.tenant_id,
                frozenset(run.delegated_roles), frozenset(run.delegated_store_scope))
            execution_context = ToolExecutionContext(tenant_id=run.tenant_id, principal_id=principal.principal_id,
                agent_run_id=run.agent_run_id, correlation_id=run.correlation_id, config_version=run.config_version,
                allowed_store=pack.store, tool_version=contract.version,
                manifest_reference=sha256(run.manifest.model_dump_json().encode()).hexdigest())
            events = uow.agent_runs.events(self.run_id)
            claims = [e for e in events if e.kind == "CLAIM" and e.agent_type == self.agent_type]
            results = [e for e in events if e.kind == "RESULT" and e.agent_type == self.agent_type]
            reserved = len(claims) == len(results)+1
            reservation = claims[-1].event_id if reserved else "direct"
            identity = sha256((name+contract.version+arguments.model_dump_json()+pack.digest
                +execution_context.model_dump_json()+reservation).encode()).hexdigest()
            previous = next((c for c in run.state.tool_calls if c.call_id == identity), None)
            # An outer Loop claim already consumed this operation's slot. Never charge twice.
            used = run.state.tool_call_count - int(reserved or previous is not None)
            checked = run.model_copy(update={"state": run.state.model_copy(update={"tool_call_count": max(0, used)})})
            capabilities = self.source.capabilities(run.tenant_id, incident.store, self.clock())
            decision = harness_gate(HarnessIntent(agent_run_id=self.run_id,
                operation=contract.operation, context_digest=pack.digest), run=checked,
                incident=incident, principal=principal, config=version.config, now=self.clock(),
                capabilities=capabilities, control=control_state(events))
            uow.agent_runs.append_event(self.run_id, RuntimeEvent(event_id=str(uuid4()),
                kind="HARNESS", decision=decision, created_at=self.clock()))
            if not decision.allowed:
                if decision.reason == "AUTHORIZATION_DENIED":
                    raise AccessError()
                code = {"CAPABILITY_UNAVAILABLE": "NO_DATA", "BUDGET_EXHAUSTED": "BUDGET_EXHAUSTED"}.get(
                    decision.reason, "POLICY_DENIED")
                raise ToolFailure(tool_error(code))
            if previous:
                if previous.result:
                    return previous.result
                raise ToolFailure(previous.error or tool_error("OUTCOME_UNKNOWN"))
            if any(c.context_digest == pack.digest and c.result is None and c.error is None
                    for c in run.state.tool_calls):
                raise ToolFailure(tool_error("OUTCOME_UNKNOWN"))
            if (run.status != "RUNNING" or reserved and any(c.reservation == reservation
                    and c.call_id != identity for c in run.state.tool_calls)):
                raise ToolFailure(tool_error("POLICY_DENIED"))
            receipt = ToolCall(call_id=identity, tool_name=name, context_digest=pack.digest,
                reservation=reservation)
            state = run.state.model_copy(update={"tool_calls": (*run.state.tool_calls, receipt),
                "tool_call_count": run.state.tool_call_count+int(not reserved)})
            uow.agent_runs.save(run.model_copy(update={"state": state}))
        result, error = None, None
        try:
            result = BusinessToolQueries(self.persistence, self.source).read(name, arguments,
                principal=principal, context=pack)
        except AccessError:
            error = tool_error("ACCESS_DENIED")
        except TimeoutError:
            error = tool_error("SOURCE_TIMEOUT")
        except OSError:
            error = tool_error("SOURCE_UNAVAILABLE")
        except (ValueError, RuntimeError):
            error = tool_error("INVALID_CONTRACT")
        with self.persistence.transaction(self.tenant_id) as uow:
            current = uow.agent_runs.lock(self.run_id)
            calls = tuple(c.model_copy(update={"result": result, "error": error})
                if c.call_id == identity else c for c in current.state.tool_calls)
            uow.agent_runs.save(current.model_copy(update={"state": current.state.model_copy(update={"tool_calls": calls})}))
        if error:
            if error.code == "ACCESS_DENIED":
                raise AccessError()
            raise ToolFailure(error)
        return result
