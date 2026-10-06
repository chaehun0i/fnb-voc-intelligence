from dataclasses import replace

import pytest

from src.agents.capa_commands import CAPACommands
from src.agents.capa_node import CAPAInvestigation
from src.application.ports.incident_repository import IncidentConflict
from tests.test_history_application import setup_history
from tests.test_rca_investigation import ready


def prepared(*, internal_execution=False):
    persistence, workflows, context, decision = setup_history()
    with persistence.transaction("t") as uow:
        version = uow.configs.current()
        uow.configs.append(replace(version, config_version=2, parent_version=1,
            config=replace(version.config, auto_capa_draft=True, auto_rca_draft=True,
                internal_execution_enabled=internal_execution)), 1)
    # 테스트는 같은 Config/Jev lineage를 고정하며 enqueue 권한을 우회하지 않습니다.
    from src.ai.decision.service import ShadowDecisions
    from src.domain.jobs.models import Job
    now = workflows.clock()
    decision = ShadowDecisions(persistence, clock=lambda: now).record(
        Job("snapshot2", "t", "incident.snapshot", "c", now, now, incident_id="i", store="store"))
    job = workflows.enqueue(context, "i", decision.decision_id)
    run, resolved, _ = workflows.prepare(job)
    base = ready()
    items = tuple(e.model_copy(update={"tenant_id": "t", "store": "store", "agent_run_id": run.agent_run_id})
                  for e in base.normalized_evidence)
    from src.agents.models import EvidenceCandidate
    candidates = tuple(EvidenceCandidate.model_validate(e.model_dump(exclude={"agent_run_id", "source_id", "step_name"})) for e in items)
    state = run.state.model_copy(update={"normalized_evidence": items, "sufficiency": base.sufficiency,
        "evidence_candidates": candidates, "evidence_refs": tuple(e.source_ref for e in items)})
    from src.agents.rca_node import RCAInvestigation
    state = RCAInvestigation(resolved, decision.decision_id, requires_llm=False, clock=lambda: now)(state)
    state = CAPAInvestigation(resolved, decision.decision_id, store="store", incident_severity="MEDIUM")(state)
    with persistence.transaction("t") as uow:
        uow.agent_runs.save(run.model_copy(update={"state": state}))
    return persistence, run, state, job, decision


def test_application_uses_domain_commands_and_deduplicates():
    p, run, state, _, _ = prepared()
    commands = CAPACommands(p, run.agent_run_id, "t")
    result = commands.apply(state)
    assert commands.apply(state) == result
    with p.transaction("t") as uow:
        incident = uow.incidents.get("i")
        assert incident.status == "ACTION_PROPOSED" and len(incident.corrective_actions) == 1
        assert len(incident.evidence) == 3 and not incident.approved
        assert uow.agent_runs.get(run.agent_run_id).state == result


def test_application_stale_version_is_atomic():
    p, run, state, _, _ = prepared()
    with p.transaction("t") as uow:
        incident = uow.incidents.get("i")
        uow.incidents.save(replace(incident, owner="changed"))
    with pytest.raises(IncidentConflict):
        CAPACommands(p, run.agent_run_id, "t").apply(state)
    with p.transaction("t") as uow:
        assert not uow.incidents.get("i").corrective_actions
