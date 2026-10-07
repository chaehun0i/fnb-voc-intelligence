"""Official MCP + LangChain + Harness over real PG/Worker/checkpoint, no network AI/write."""
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import psycopg
from scripts.serviq_langgraph_smoke import FailHistoryCheckpoint
from scripts.serviq_multi_agent_smoke import CountHistory, FailInventory, seed

from src.ai.ax.service import AgentRunQueries
from src.ai.workflow.runtime import (
    HistoryProcessor,
    HistoryWorkflows,
    postgres_checkpoint,
)
from src.application.incidents.service import IncidentNotFound
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.jobs.job_worker import JobWorker
from src.infrastructure.jobs.runtime import snapshot_processor
from src.infrastructure.repositories.job_repository import PostgresJobRepository
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)


def verify(dsn):
    for case in ("normal", "partial", "filter", "restart"):
        p, source, principal, job, incident = seed(dsn, loop=True, inventory=case != "filter")
        search = CountHistory(dsn)
        if case == "partial":
            source = FailInventory(dsn)
        @contextmanager
        def checkpoint():
            with postgres_checkpoint(dsn) as saver:
                yield saver
        processor = HistoryProcessor(p, search, checkpoint, source=source, dsn=dsn)
        if case == "restart":
            @contextmanager
            def broken():
                with postgres_checkpoint(dsn) as saver:
                    yield FailHistoryCheckpoint(saver)
            failed = HistoryProcessor(p, search, broken, source=source, dsn=dsn)
            with psycopg.connect(dsn, autocommit=True) as connection:
                worker = JobWorker(connection, snapshot_processor(p.incidents, history=failed),
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
        with p.transaction(principal.tenant_id) as uow:
            run = uow.agent_runs.by_job(job.job_id)
            assert run.state.sufficiency.allows_rca
            assert run.manifest.tool_bundle_versions == ("read-tools-1",)
            assert run.state.tool_calls and all(c.result or c.error for c in run.state.tool_calls)
            assert run.state.tool_call_count <= run.state.loop.policy.max_operations
            before = run.state.tool_calls
            if case == "partial":
                assert any(c.error and c.error.code == "SOURCE_UNAVAILABLE" for c in before)
                assert any(e.source_type == "TRANSACTION" for e in run.state.normalized_evidence)
            if case == "filter":
                assert all(c.tool_name != "get_inventory" for c in before)
            assert uow.llm_calls.history(incident.id, 20) == []
        # New persistence/processor objects restore the same effect receipts and completed work.
        restored = AccessPersistence(PostgresIncidentRepository(dsn))
        completed = HistoryWorkflows(restored, source=source).prepare(job)[0]
        assert completed.state.tool_calls == before and search.calls == 1
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = JobWorker(connection, snapshot_processor(restored.incidents, history=processor),
                tenant_id=principal.tenant_id)
            assert not worker.run_once()  # a completed job cannot acquire a new execution lease.
        detail = AgentRunQueries(restored, principal).execute(incident.id, run_id=run.agent_run_id)
        assert detail["tools"] and "MULTI-RAW-SENTINEL" not in str(detail)
        assert "context_digest" not in str(detail) and "tool_calls" not in detail
        with restored.transaction("other") as uow:
            assert uow.agent_runs.get(run.agent_run_id) is None
        try:
            AgentRunQueries(restored, principal).execute(incident.id, run_id="00000000-0000-0000-0000-000000000000")
        except IncidentNotFound:
            pass
        else:
            raise AssertionError("unknown run must stay 404")
        print("[통과] MCP/LangChain/Harness PostgreSQL "+case)


def main():
    dsn = os.environ.get("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("격리된 SERVIQ_TEST_DATABASE_URL을 설정해 주세요.")
    verify(dsn)


if __name__ == "__main__":
    main()
