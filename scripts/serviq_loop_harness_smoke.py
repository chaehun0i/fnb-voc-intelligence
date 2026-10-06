"""Real PostgreSQL/Worker/checkpoint/control Golden slice; no external Provider/write."""
import argparse
import json
import os
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import psycopg
from scripts.serviq_langgraph_smoke import FailHistoryCheckpoint
from scripts.serviq_multi_agent_smoke import CountHistory, FailInventory, seed

from src.ai.ax.service import AgentRunQueries
from src.ai.workflow.agents import SourceUnavailable
from src.ai.workflow.runtime import (
    HistoryProcessor,
    HistoryWorkflows,
    postgres_checkpoint,
)
from src.application.agent_controls import CONTINUE_JOB, AgentControls
from src.application.security.principal import RequestContext
from src.infrastructure.investigation_source import PostgresInvestigationSource
from src.infrastructure.jobs.job_worker import JobWorker
from src.infrastructure.jobs.runtime import snapshot_processor
from src.infrastructure.repositories.job_repository import PostgresJobRepository


class RecoverInventory(PostgresInvestigationSource):
    def __init__(self, dsn):
        super().__init__(dsn)
        self.attempts = 0

    def observations(self, context):
        if context.agent_type == "INVENTORY":
            self.attempts += 1
            if self.attempts == 1:
                raise SourceUnavailable()
        return super().observations(context)


def verify(dsn):
    for case in ("normal", "retry-success", "no-new-evidence", "budget", "pause-resume", "stop", "takeover", "restart"):
        p, source, principal, job, incident = seed(dsn, loop=True, max_operations=1 if case == "budget" else 20)
        run = HistoryWorkflows(p, source=source).prepare(job)[0]
        search = CountHistory(dsn)
        if case == "no-new-evidence":
            source = FailInventory(dsn)
        elif case == "retry-success":
            source = RecoverInventory(dsn)
        @contextmanager
        def checkpoint():
            with postgres_checkpoint(dsn) as saver:
                yield saver
        processor = HistoryProcessor(p, search, checkpoint, source=source, dsn=dsn)
        context = RequestContext(principal, "loop-control", "loop-control", "loop-control")
        commands = AgentControls(p)
        if case in {"pause-resume", "stop", "takeover"}:
            action = {"pause-resume": "pause", "stop": "stop", "takeover": "takeover"}[case]
            event = commands.execute(context, incident.id, run.agent_run_id, action, 0)
            assert commands.execute(context, incident.id, run.agent_run_id, action, 0) == event
        if case == "restart":
            @contextmanager
            def broken():
                with postgres_checkpoint(dsn) as saver:
                    yield FailHistoryCheckpoint(saver)
            failing = HistoryProcessor(p, search, broken, source=source, dsn=dsn)
            with psycopg.connect(dsn, autocommit=True) as connection:
                worker = JobWorker(connection, snapshot_processor(p.incidents, history=failing),
                    tenant_id=principal.tenant_id, retry_seconds=.001)
                assert worker.run_once() and worker.run_once()
                assert PostgresJobRepository(connection, principal.tenant_id).get(job.job_id).status == "PENDING"
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = JobWorker(connection, snapshot_processor(p.incidents, history=processor),
                tenant_id=principal.tenant_id, clock=lambda: datetime.now(UTC)+timedelta(seconds=1))
            assert worker.run_once()
            if case != "restart":
                assert worker.run_once()
            assert PostgresJobRepository(connection, principal.tenant_id).get(job.job_id).status == "COMPLETED"
        if case in {"pause-resume", "stop", "takeover"}:
            assert search.calls == 0
            if case == "pause-resume":
                commands.execute(replace(context, idempotency_key="resume"), incident.id, run.agent_run_id, "resume", 1)
                with psycopg.connect(dsn, autocommit=True) as connection:
                    worker = JobWorker(connection, snapshot_processor(p.incidents, history=processor), tenant_id=principal.tenant_id)
                    assert worker.run_once()
                    jobs = PostgresJobRepository(connection, principal.tenant_id).list(job_type=CONTINUE_JOB)
                    assert len(jobs) == 1 and jobs[0].status == "COMPLETED"
        with p.transaction(principal.tenant_id) as uow:
            result = uow.agent_runs.get(run.agent_run_id)
            events = uow.agent_runs.events(run.agent_run_id)
            assert result.manifest == run.manifest
            claims = [e for e in events if e.kind == "CLAIM"]
            assert len(claims) == result.state.tool_call_count
            assert len(claims) <= run.state.loop.policy.max_operations
            assert len({(e.agent_type, e.attempt) for e in claims}) == len(claims)
        with p.transaction(principal.tenant_id+"-other") as uow:
            assert uow.agent_runs.get(run.agent_run_id) is None
            assert uow.agent_runs.events(run.agent_run_id) == []
        detail = AgentRunQueries(p, principal).execute(incident.id, run_id=run.agent_run_id)
        assert detail["runtime"] is not None
        if case in {"stop", "takeover"}:
            assert not any(detail["runtime"]["permissions"].values())
        else:
            assert result.status == "COMPLETED"
            expected = "NO_NEW_EVIDENCE" if case == "no-new-evidence" else "BUDGET_EXHAUSTED" if case == "budget" else "COMPLETED"
            assert result.state.loop.termination == expected
            assert result.state.normalized_evidence
            if case in {"normal", "restart", "pause-resume", "retry-success"}:
                assert len(result.state.normalized_evidence) == 4
            if case == "no-new-evidence":
                assert len(result.state.normalized_evidence) == 3 and result.state.iteration == 2
            if case == "retry-success":
                assert result.state.tool_call_count == 4 and result.state.loop.new_evidence
            before = len(events)
            with psycopg.connect(dsn, autocommit=True) as connection:
                duplicate = JobWorker(connection, snapshot_processor(p.incidents, history=processor), tenant_id=principal.tenant_id)
                assert not duplicate.run_once()
            with p.transaction(principal.tenant_id) as uow:
                assert uow.agent_runs.get(run.agent_run_id) == result
                assert len(uow.agent_runs.events(run.agent_run_id)) == before
            assert search.calls <= 1
        assert p.incidents.get(incident.id).status == incident.status
        print("[통과] PostgreSQL Loop/Harness "+case)
    for statement in (
        "UPDATE serviq_runtime_events SET document=document WHERE tenant_id=%s AND agent_run_id=%s",
        "DELETE FROM serviq_runtime_events WHERE tenant_id=%s AND agent_run_id=%s",
        "UPDATE serviq_agent_runs SET document=jsonb_set(document,'{manifest}','null'::jsonb) WHERE tenant_id=%s AND agent_run_id=%s",
    ):
        try:
            with psycopg.connect(dsn) as connection:
                connection.execute(statement, (principal.tenant_id, run.agent_run_id))
        except psycopg.Error:
            pass
        else:
            raise AssertionError("append-only ledger / immutable manifest must reject mutation")
    print("[통과] PostgreSQL append-only runtime ledger·immutable Manifest·tenant isolation")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-http", action="store_true")
    args = parser.parse_args()
    dsn = os.environ.get("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("격리된 SERVIQ_TEST_DATABASE_URL을 설정해 주세요.")
    if args.seed_http:
        cases = []
        for action in ("resume", "stop", "takeover"):
            p, source, principal, job, incident = seed(dsn, loop=True, tenant="legacy-local")
            run = HistoryWorkflows(p, source=source).prepare(job)[0]
            AgentControls(p).execute(RequestContext(principal, "http-loop-seed", "http-loop-seed", "pause-seed-"+run.agent_run_id),
                incident.id, run.agent_run_id, "pause", 0)
            cases.append({"incident_id": incident.id, "agent_run_id": run.agent_run_id, "action": action})
        print(json.dumps(cases))
    else:
        verify(dsn)


if __name__ == "__main__":
    main()
