"""Job 재인수와 Graph 복구를 연결하며 외부 호출 불확실성은 fail-closed로 남깁니다."""
import logging
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import psycopg

from src.agents.capa_commands import CAPACommands
from src.agents.capa_node import CAPAInvestigation
from src.agents.evidence import normalize_evidence
from src.agents.graph import history_graph, invoke_or_resume
from src.agents.history import HistoryWorkflows
from src.agents.history_node import HistoryInvestigation
from src.agents.models import AgentStep, WorkflowStatus, finish_run
from src.agents.rca_node import RCAInvestigation
from src.agents.resume import RESUME_JOB
from src.agents.sufficiency import evaluate_sufficiency
from src.agents.verification_commands import VerificationCommands
from src.infrastructure.jobs.job_worker import RetryableJobError
from src.llm.runtime import configured_llm_executor

logger = logging.getLogger(__name__)


class UncertainHistoryCall(Exception):
    """외부 호출 직후 중단된 실행은 중복 과금 방지를 위해 자동 재호출하지 않습니다."""


@contextmanager
def execution_lease(dsn, job, lease_seconds):
    if not dsn:
        yield lambda: None
        return
    stop, lost = threading.Event(), threading.Event()
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as connection:
        lock = "history:"+job.tenant_id+":"+(job.parent_job_id if job.job_type == RESUME_JOB else job.job_id)
        if not connection.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0))", (lock,)).fetchone()[0]:
            raise RetryableJobError("WORKFLOW_BUSY")

        def renew():
            with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as heartbeat:
                until = datetime.now(UTC)+timedelta(seconds=lease_seconds)
                row = heartbeat.execute("""UPDATE serviq_jobs SET lease_until=%s,
                    document=jsonb_set(document,'{lease_until}',to_jsonb(%s::text))
                    WHERE tenant_id=%s AND job_id=%s AND version=%s AND attempt=%s
                    AND status='RUNNING' AND document->>'worker_id'=%s AND lease_until>CURRENT_TIMESTAMP
                    RETURNING job_id""", (until, until.isoformat(), job.tenant_id, job.job_id,
                    job.version, job.attempt, job.worker_id)).fetchone()
                if row is None:
                    lost.set()

        def check():
            if lost.is_set():
                raise RetryableJobError("WORKFLOW_LEASE_LOST")
            renew()
            if lost.is_set():
                raise RetryableJobError("WORKFLOW_LEASE_LOST")

        def background():
            while not stop.wait(max(.1, lease_seconds/3)):
                try:
                    renew()
                except psycopg.Error:
                    lost.set()
                    return

        thread = threading.Thread(target=background, daemon=True)
        try:
            check()
            thread.start()
            yield check
        finally:
            stop.set()
            if thread.is_alive():
                thread.join(timeout=10)
            connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (lock,))


class HistoryProcessor:
    def __init__(self, persistence, search, checkpoint_factory, *, dsn=None,
                 executor_factory=configured_llm_executor, clock=None, lease_seconds=60):
        self.persistence, self.search, self.checkpoint_factory = persistence, search, checkpoint_factory
        self.dsn, self.executor_factory, self.lease_seconds = dsn, executor_factory, lease_seconds
        self.clock = clock or (lambda: datetime.now(UTC))

    def __call__(self, job):
        with execution_lease(self.dsn, job, self.lease_seconds) as check:
            run, resolved, decision = HistoryWorkflows(self.persistence, self.clock).prepare(job)
            if run.status == WorkflowStatus.COMPLETED:
                return run
            if run.status == WorkflowStatus.WAITING_APPROVAL and job.job_type != RESUME_JOB:
                return run
            def record(call):
                check()
                with self.persistence.transaction(job.tenant_id) as uow:
                    uow.llm_calls.append(call)

            executor = self.executor_factory(record) if decision.result.requires_llm else None
            with self.persistence.transaction(job.tenant_id) as uow:
                incident = uow.incidents.get(job.incident_id)
                if incident is None or incident.store != job.store:
                    raise ValueError("WORKFLOW_TARGET_INVALID")
            node = HistoryInvestigation(self.search, store=job.store, query=incident.title,
                resolved=resolved, requires_llm=decision.result.requires_llm,
                clock=self.clock, executor=executor)
            memoized = set()

            def investigate(state):
                check()
                with self.persistence.transaction(job.tenant_id) as uow:
                    current = uow.agent_runs.get(run.agent_run_id)
                    if current.state.iteration:
                        memoized.add("history_investigation")
                        return current.state
                    if executor is not None:
                        if uow.connection:
                            claimed = uow.connection.execute("""INSERT INTO serviq_history_effects(tenant_id,agent_run_id,claimed_at)
                                VALUES(%s,%s,%s) ON CONFLICT DO NOTHING RETURNING agent_run_id""",
                                (job.tenant_id, run.agent_run_id, self.clock())).fetchone()
                            if claimed is None:
                                raise UncertainHistoryCall()
                        else:
                            key = (job.tenant_id, run.agent_run_id)
                            effects = self.persistence.memory.data.setdefault("history_effects", set())
                            if key in effects:
                                raise UncertainHistoryCall()
                            effects.add(key)
                result = node(state)
                check()
                with self.persistence.transaction(job.tenant_id) as uow:
                    current = uow.agent_runs.get(run.agent_run_id)
                    uow.agent_runs.save(current.model_copy(update={"state": result}))
                return result

            def persist(state):
                check()
                with self.persistence.transaction(job.tenant_id) as uow:
                    current = uow.agent_runs.get(run.agent_run_id)
                    updates = {"state": state}
                    if state.status == WorkflowStatus.WAITING_APPROVAL:
                        updates.update(status=WorkflowStatus.WAITING_APPROVAL, completed_at=None)
                    uow.agent_runs.save(current.model_copy(update=updates))

            def normalize(state):
                result = normalize_evidence(state.evidence_candidates, tenant_id=job.tenant_id,
                    store=job.store, agent_run_id=run.agent_run_id)
                return state.model_copy(update={"normalized_evidence": result,
                    "evidence_refs": tuple(e.source_ref for e in result)})

            def evaluate(state):
                result = evaluate_sufficiency(state.normalized_evidence, state.evidence_gaps)
                return state.model_copy(update={"sufficiency": result, "evidence_gaps": result.evidence_gaps})

            def rca(state):
                check()
                with self.persistence.transaction(job.tenant_id) as uow:
                    current = uow.agent_runs.get(run.agent_run_id)
                    if current.state.rca_completed:
                        memoized.add("rca_investigation")
                        return current.state
                    if resolved.effective.auto_rca_draft and executor is not None:
                        if uow.connection:
                            claimed = uow.connection.execute("""INSERT INTO serviq_rca_effects(tenant_id,agent_run_id,claimed_at)
                                VALUES(%s,%s,%s) ON CONFLICT DO NOTHING RETURNING agent_run_id""",
                                (job.tenant_id, run.agent_run_id, self.clock())).fetchone()
                            if claimed is None:
                                raise UncertainHistoryCall()
                        else:
                            key = (job.tenant_id, run.agent_run_id)
                            effects = self.persistence.memory.data.setdefault("rca_effects", set())
                            if key in effects:
                                raise UncertainHistoryCall()
                            effects.add(key)
                result = RCAInvestigation(resolved, run.jev_decision_id,
                    requires_llm=decision.result.requires_llm, clock=self.clock, executor=executor,
                    deadline=run.started_at+timedelta(seconds=resolved.effective.timeout_seconds))(state)
                result = result.model_copy(update={"rca_completed": True})
                persist(result)
                return result

            def observe(name, before, after, latency_ms, *, failed=False):
                check()
                now = self.clock()
                step = AgentStep(agent_run_id=run.agent_run_id,
                    sequence={"validate_context": 1, "history_investigation": 2, "normalize_evidence": 3,
                        "evaluate_sufficiency": 4, "rca_investigation": 5,
                        "capa_proposal": 6, "apply_capa": 7, "request_approval": 8,
                        "approval_interrupt": 9, "approval_result": 10,
                        "internal_execution": 11, "begin_verification": 12,
                        "verification": 13, "apply_verification": 14,
                        "persist_result": 3 if run.workflow_version == "history-v1" else
                            15 if run.workflow_version == "history-verification-v4" else
                            11 if run.workflow_version == "history-capa-v3" else 6}[name],
                    node_name=name, attempt=job.attempt or 1,
                    status=WorkflowStatus.FAILED if failed else
                        WorkflowStatus.WAITING_APPROVAL if name == "approval_interrupt" else WorkflowStatus.COMPLETED,
                    started_at=now-timedelta(milliseconds=latency_ms), completed_at=now,
                    latency_ms=max(0, latency_ms),
                    token_spent=0 if name in memoized else after.token_spent-before.token_spent,
                    cost_spent=0 if name in memoized else max(0, after.cost_spent-before.cost_spent),
                    evidence_refs=after.evidence_refs, error_code="WORKFLOW_FAILED" if failed else None,
                    result=after if run.workflow_version != "history-v1" else None)
                with self.persistence.transaction(job.tenant_id) as uow:
                    uow.agent_runs.append_step(step)

            try:
                with self.checkpoint_factory() as saver:
                    stages = {} if run.workflow_version == "history-v1" else {
                        "normalize": normalize, "evaluate": evaluate, "rca": rca}
                    if run.workflow_version in {"history-capa-v3", "history-verification-v4"}:
                        commands = CAPACommands(self.persistence, run.agent_run_id, job.tenant_id, self.clock)
                        def request_approval(state):
                            check()
                            result = commands.request_approval(state).model_copy(update={"status": WorkflowStatus.WAITING_APPROVAL})
                            persist(result)
                            return result
                        stages.update(capa=CAPAInvestigation(resolved, run.jev_decision_id,
                            store=job.store, incident_severity=incident.severity), apply_capa=commands.apply,
                            request_approval=request_approval, approval_result=commands.approval_result)
                        if run.workflow_version == "history-verification-v4":
                            vc = VerificationCommands(self.persistence, run.agent_run_id, job.tenant_id, self.clock)
                            stages.update(internal_execution=vc.execute, begin_verification=vc.begin_verification,
                                verification=vc.evaluate, apply_verification=vc.apply)
                    graph = history_graph(saver, investigate, persist, observe=observe, **stages)
                    result = invoke_or_resume(graph, run.state,
                        approval_id=job.payload_ref if job.job_type == RESUME_JOB else None)
                check()
                with self.persistence.transaction(job.tenant_id) as uow:
                    current = uow.agent_runs.get(run.agent_run_id)
                    if result.status == WorkflowStatus.WAITING_APPROVAL:
                        return uow.agent_runs.save(current.model_copy(update={"state": result,
                            "status": WorkflowStatus.WAITING_APPROVAL, "completed_at": None}))
                    return uow.agent_runs.save(finish_run(current, result, self.clock()))
            except Exception as error:
                logger.error("History 조사 실패 code=WORKFLOW_FAILED job_id=%s", job.job_id)
                with self.persistence.transaction(job.tenant_id) as uow:
                    current = uow.agent_runs.get(run.agent_run_id)
                    if current.status != WorkflowStatus.COMPLETED:
                        uow.agent_runs.save(finish_run(current, current.state, self.clock(), failed=True))
                if isinstance(error, (psycopg.Error, RetryableJobError)):
                    raise RetryableJobError("WORKFLOW_PERSISTENCE_UNAVAILABLE") from None
                raise
