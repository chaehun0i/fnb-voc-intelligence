"""ai/workflow/runtime: 통합된 기능 책임, 기존 실행 계약 유지."""
import json
import logging
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

import psycopg
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Interrupt, Send

from src.ai.decision.models import AgentType, DecisionRoute
from src.ai.execution.policy import validate_approval
from src.ai.execution.service import VerificationCommands
from src.ai.intelligence.service import configured_llm_executor
from src.ai.workflow.agents import (
    CAPAInvestigation,
    HistoryInvestigation,
    OperationalInvestigation,
    RCAInvestigation,
    SourceUnavailable,
    investigation_fan_in,
    isolated_branch,
    normalize_evidence,
)
from src.ai.workflow.controller import InvestigationLoop
from src.ai.workflow.graph import history_graph, invoke_or_resume
from src.ai.workflow.models import (
    AgentContextPack,
    AgentRun,
    AgentStep,
    ApprovalTrace,
    InvestigationResult,
    LoopTrace,
    WorkflowState,
    WorkflowStatus,
    finish_run,
)
from src.ai.workflow.policy import (
    approval_policy_digest,
    build_context,
    evaluate_sufficiency,
    loop_policy,
    run_manifest,
    select_agents,
    server_risk,
)
from src.application.approvals.service import ApprovalService
from src.application.incidents.service import IncidentNotFound, IncidentService
from src.application.ports.repositories import IncidentConflict
from src.application.security.authorization import require
from src.application.security.principal import AccessError, Principal, RequestContext
from src.domain.approvals.audit import AuditRecord
from src.domain.config.resolution import ConfigResolver
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import CorrectiveAction, Evidence, RootCauseCandidate
from src.domain.jobs.models import Job
from src.infrastructure.jobs.job_worker import RetryableJobError

RESUME_JOB = "incident.history_resume"




def enqueue_resume(uow, approval, now):
    run, item = validate_approval(uow, approval, now, decided=True)
    job_id = str(uuid5(NAMESPACE_URL, "approval-resume:"+run.agent_run_id+":"+approval.approval_id))
    existing = uow.jobs.get(job_id)
    if existing:
        return existing
    original = uow.jobs.get(run.job_id)
    if original is None:
        raise IncidentConflict()
    return uow.jobs.save(Job(job_id, run.tenant_id, RESUME_JOB, run.correlation_id, now, now,
        incident_id=item.id, store=item.store, payload_ref=approval.approval_id, parent_job_id=run.job_id,
        config_version=run.config_version, max_attempts=original.max_attempts))


HISTORY_JOB = "incident.history_investigation"


class WorkflowNotAllowed(Exception):
    """명시적인 조사 실행 조건을 충족하지 못했습니다."""


def validate_start(incident, decision, version):
    if (version is None or decision is None or decision.error_code is not None
            or decision.tenant_id != incident.tenant_id or decision.incident_id != incident.id
            or decision.incident_version != incident.version
            or version.config_version != decision.result.config_version
            or decision.result.workflow_profile != "incident-investigation-v1"
            or decision.result.route == DecisionRoute.MANUAL_REVIEW
            or AgentType.HISTORY not in decision.result.investigation_agents
            or incident.status not in {IncidentStatus.TRIAGED, IncidentStatus.INVESTIGATING}):
        raise WorkflowNotAllowed()
    resolved = ConfigResolver().resolve(version.config)
    config = resolved.effective
    if (not config.jev_enabled or not config.auto_investigation
            or "HISTORY" not in config.allowed_agent_types or "voc.search" not in config.allowed_tools):
        raise WorkflowNotAllowed()
    return resolved


def decision_for_job(uow, job):
    # payload_ref는 공개 prompt가 아니라 생성 시 검증된 Decision ID입니다.
    decision = uow.decisions.get(job.payload_ref)
    return decision if decision and decision.incident_id == job.incident_id else None


class HistoryWorkflows:
    def __init__(self, persistence, clock=None, source=None):
        self.persistence = persistence
        self.source = source
        self.clock = clock or (lambda: datetime.now(UTC))

    def enqueue(self, context, incident_id, decision_id):
        principal = context.principal
        require(principal, "operate")
        with self.persistence.transaction(principal.tenant_id) as uow:
            incident = uow.incidents.get(incident_id)
            if incident is None:
                raise IncidentNotFound()
            require(principal, "operate", incident.store)
            decision = uow.decisions.get(decision_id)
            # 신규 실행은 최신 Tenant 정책에 일치하는 Decision만 허용합니다.
            version = uow.configs.current()
            validate_start(incident, decision, version)
            job_id = str(uuid5(NAMESPACE_URL, "history:"+principal.tenant_id+":"+decision_id))
            existing = uow.jobs.get(job_id)
            if existing:
                return existing
            now = self.clock()
            job = uow.jobs.save(Job(job_id, principal.tenant_id, HISTORY_JOB,
                context.correlation_id, now, now, incident_id=incident.id, store=incident.store,
                payload_ref=decision_id, config_version=version.config_version,
                max_attempts=version.config.retry_limit+1, delegated_principal_id=principal.principal_id,
                delegated_roles=tuple(sorted(principal.roles)), delegated_store_scope=tuple(sorted(principal.store_scope))))
            uow.audit.append(AuditRecord(str(uuid5(NAMESPACE_URL, "history-audit:"+job_id)),
                principal.tenant_id, principal.principal_id, "history_enqueue", "job", job_id,
                "SUCCESS", context.request_id, context.correlation_id, now.isoformat(), incident.version))
            return job

    def prepare(self, job):
        if job.job_type == RESUME_JOB:
            with self.persistence.transaction(job.tenant_id) as uow:
                approval = uow.approvals.get(job.payload_ref)
                if approval is None:
                    raise WorkflowNotAllowed()
                run = uow.agent_runs.get(approval.agent_run_id) if approval.agent_run_id else None
                if run and run.state.execution:
                    from src.domain.approvals.models import action_digest
                    record = uow.executions.get(run.agent_run_id)
                    incident = uow.incidents.get(run.incident_id)
                    result = run.state.verification
                    if (record != run.state.execution or incident is None or approval.status != "APPROVED"
                            or record.approval_id != approval.approval_id or record.action_digest != approval.action_digest
                            or incident.version != record.incident_version+int(run.state.resulting_incident_status != "EXECUTING")+int(result is not None)
                            or (result and (incident.verification is None or incident.verification.id != result.verification_id))
                            or (not result and action_digest(incident) != record.action_digest)):
                        raise WorkflowNotAllowed()
                else:
                    run, incident = validate_approval(uow, approval, self.clock(), decided=True)
                version = uow.configs.get(run.config_version)
                decision = uow.decisions.get(run.jev_decision_id)
                if (version is None or decision is None or run.job_id != job.parent_job_id
                        or run.config_version != job.config_version or incident.id != job.incident_id
                        or incident.store != job.store):
                    raise WorkflowNotAllowed()
                return run, ConfigResolver().resolve(version.config), decision
        if job.job_type != HISTORY_JOB:
            raise WorkflowNotAllowed()
        with self.persistence.transaction(job.tenant_id) as uow:
            previous = uow.agent_runs.by_job(job.job_id)
            if previous:
                version = uow.configs.get(previous.config_version)
                decision = decision_for_job(uow, job)
                if version is None or decision is None:
                    raise WorkflowNotAllowed()
                return previous, ConfigResolver().resolve(version.config), decision
            incident = uow.incidents.get(job.incident_id)
            if incident is None or incident.store != job.store:
                raise WorkflowNotAllowed()
            decision = decision_for_job(uow, job)
            version = uow.configs.get(job.config_version)
            resolved = validate_start(incident, decision, version)
            rid = str(uuid5(NAMESPACE_URL, "run:"+job.tenant_id+":"+job.job_id))
            wid = str(uuid5(NAMESPACE_URL, "workflow:"+rid))
            state = WorkflowState(tenant_id=job.tenant_id, incident_id=job.incident_id,
                workflow_id=wid, agent_run_id=rid, risk_level=decision.result.risk_level,
                route=decision.result.route, config_version=version.config_version)
            if resolved.effective.multi_agent_enabled:
                if self.source is None:
                    raise WorkflowNotAllowed()
                from src.ai.decision.engine import build_context as decision_context
                category = decision_context(incident, resolved, version.config_version).category
                now = self.clock()
                tool_agents = tuple(a for a, tool in (("HISTORY", "voc.search"),
                    ("TRANSACTION", "transaction.search"), ("INVENTORY", "inventory.snapshot"))
                    if a in resolved.effective.allowed_agent_types and tool in resolved.effective.allowed_tools)
                selection = select_agents(decision.result.investigation_agents,
                    self.source.capabilities(job.tenant_id, job.store, now), tenant_id=job.tenant_id,
                    store=job.store, category=category, allowed_agents=tool_agents, now=now)
                if len(selection.selected) > resolved.effective.max_tool_calls and not resolved.effective.loop_enabled:
                    raise WorkflowNotAllowed()
                contexts = tuple(build_context(a.agent_type, tenant_id=job.tenant_id,
                    incident_id=job.incident_id, store=job.store, category=category,
                    severity=incident.severity, window_start=datetime.fromisoformat(incident.created_at)-timedelta(hours=24),
                    window_end=now, now=now, budget_bytes=min(4096, resolved.effective.token_budget))
                    for a in selection.selected)
                state = WorkflowState.model_validate(state.model_copy(update={"selection": selection,
                    "contexts": contexts}).model_dump(mode="json"))
                if resolved.effective.loop_enabled:
                    state = state.model_copy(update={"loop": LoopTrace(policy=loop_policy(resolved.effective))})
            run = AgentRun(agent_run_id=rid, tenant_id=job.tenant_id, incident_id=incident.id,
                workflow_id=wid, job_id=job.job_id, correlation_id=job.correlation_id,
                config_version=version.config_version, jev_decision_id=decision.decision_id,
                started_at=self.clock(), state=state,
                workflow_version="multi-investigation-v5" if resolved.effective.multi_agent_enabled else (
                    ("history-verification-v4" if resolved.effective.internal_execution_enabled else "history-capa-v3")
                    if resolved.effective.auto_capa_draft and job.delegated_principal_id else "history-evidence-v2"
                ),
                requested_by=job.delegated_principal_id, delegated_roles=job.delegated_roles,
                delegated_store_scope=job.delegated_store_scope, initial_incident_version=incident.version)
            run = AgentRun.model_validate(run.model_copy(update={"manifest": run_manifest(run)}).model_dump(mode="json"))
            return uow.agent_runs.save(run), resolved, decision


class CAPACommands:
    def __init__(self, persistence, run_id, tenant_id, clock=None):
        self.persistence, self.run_id, self.tenant_id = persistence, run_id, tenant_id
        self.clock = clock or (lambda: datetime.now(UTC))

    def apply(self, state):
        WorkflowState.model_validate(state.model_dump(mode="json"))
        with self.persistence.transaction(self.tenant_id) as uow:
            run = uow.agent_runs.get(self.run_id)
            if run is None or not run.requested_by or state.agent_run_id != run.agent_run_id:
                raise AccessError()
            principal = Principal(run.requested_by, run.tenant_id, frozenset(run.delegated_roles),
                                  frozenset(run.delegated_store_scope), "workflow-delegation")
            incident = uow.incidents.get(run.incident_id)
            if incident is None:
                raise IncidentNotFound()
            require(principal, "operate", incident.store)
            if run.state.capa_proposals and all(p.status == "APPLIED" for p in run.state.capa_proposals):
                return run.state
            version = uow.configs.get(run.config_version)
            if (version is None or not version.config.auto_capa_draft or not state.sufficiency
                    or not state.sufficiency.allows_rca or not state.capa_proposals):
                raise AccessError("CAPA_NOT_ALLOWED", 409)
            if incident.version != run.initial_incident_version:
                raise IncidentConflict()
            if state.rca_candidates != run.state.rca_candidates or state.normalized_evidence != run.state.normalized_evidence:
                raise AccessError("CAPA_LINEAGE_MISMATCH", 409)
            if any(p.store != incident.store or p.decision_reference != run.jev_decision_id
                   for p in state.capa_proposals) or any(e.store != incident.store for e in state.normalized_evidence):
                raise AccessError()
            service = IncidentService(uow.incidents, clock=self.clock, principal=principal)
            if incident.status == IncidentStatus.TRIAGED:
                incident = service.investigate(incident.id, incident.version)
            for e in state.normalized_evidence:
                incident = service.add_evidence(incident.id, Evidence(e.source_ref, e.source_ref,
                    e.source_type, "관련 과거 사례 참조", 1.0), incident.version)
            incident = service.prepare_rca(incident.id, [RootCauseCandidate(c.candidate_id,
                c.hypothesis, c.confidence, list(c.supporting_refs), list(c.contradicting_refs))
                for c in state.rca_candidates], incident.version)
            proposals = tuple(p.model_copy(update={"risk_level": server_risk(incident.severity,
                state.risk_level, p.risk_level), "required_approval": True, "status": "APPLIED"})
                for p in state.capa_proposals)
            incident = service.propose_action(incident.id, [CorrectiveAction(p.capa_proposal_id,
                p.summary, Severity(p.risk_level), p.expected_effect, p.verification_criteria,
                action_type=p.proposed_action_type, target_reference=p.target_reference)
                for p in proposals], incident.version)
            result = WorkflowState.model_validate(state.model_copy(update={"capa_proposals": proposals}).model_dump(mode="json"))
            uow.agent_runs.save(run.model_copy(update={"state": result}))
            uow.audit.append(AuditRecord(str(uuid5(NAMESPACE_URL, "capa:"+run.agent_run_id)),
                run.tenant_id, principal.principal_id, "workflow_capa", "incident", incident.id,
                "SUCCESS", run.agent_run_id, run.correlation_id, self.clock().isoformat(), incident.version))
            return result

    def request_approval(self, state):
        with self.persistence.transaction(self.tenant_id) as uow:
            run = uow.agent_runs.get(self.run_id)
            if run is None or not run.requested_by:
                raise AccessError()
            principal = Principal(run.requested_by, run.tenant_id, frozenset(run.delegated_roles),
                                  frozenset(run.delegated_store_scope), "workflow-delegation")
            incident = uow.incidents.get(run.incident_id)
            if incident is None:
                raise IncidentNotFound()
            require(principal, "operate", incident.store)
            if run.state.approval:
                return run.state
            if state != run.state or any(p.status != "APPLIED" for p in state.capa_proposals) or not state.capa_proposals:
                raise AccessError("CAPA_NOT_ALLOWED", 409)
            pinned, current = uow.configs.get(run.config_version), uow.configs.current()
            if pinned is None or current is None:
                raise IncidentConflict()
            policy = pinned.config
            if approval_policy_digest(policy) != approval_policy_digest(current.config):
                raise IncidentConflict()
            risk = server_risk(incident.severity, *(p.risk_level for p in state.capa_proposals))
            if any(server_risk(p.risk_level) != risk for p in state.capa_proposals):
                raise IncidentConflict()
            if risk == "CRITICAL" and policy.critical_approver_count != 1:
                raise AccessError("APPROVAL_POLICY_UNSUPPORTED", 409)
            aid = str(uuid5(NAMESPACE_URL, "workflow-approval:"+run.agent_run_id))
            service = IncidentService(uow.incidents, clock=self.clock, principal=principal)
            ApprovalService(service, uow.approvals, RequestContext(principal, run.agent_run_id,
                run.correlation_id)).request(incident.id, incident.version, approval_id=aid,
                workflow_metadata={"agent_run_id": run.agent_run_id, "config_version": run.config_version,
                    "policy_digest": approval_policy_digest(policy), "required_roles": policy.required_roles,
                    "separation_of_duties": policy.separation_of_duties})
            approval = uow.approvals.get(aid)
            trace = ApprovalTrace(approval_id=aid, action_ids=approval.action_ids,
                action_digest=approval.action_digest, config_version=run.config_version,
                incident_version=approval.incident_version, waiting_since=self.clock())
            result = WorkflowState.model_validate(state.model_copy(update={"approval": trace}).model_dump(mode="json"))
            uow.agent_runs.save(run.model_copy(update={"state": result}))
            uow.audit.append(AuditRecord(str(uuid5(NAMESPACE_URL, "approval-request:"+run.agent_run_id)),
                run.tenant_id, principal.principal_id, "workflow_approval_request", "approval", aid,
                "SUCCESS", run.agent_run_id, run.correlation_id, self.clock().isoformat(), approval.version))
            return result

    def approval_result(self, state):
        with self.persistence.transaction(self.tenant_id) as uow:
            existing = uow.agent_runs.get(self.run_id)
            if existing and existing.state.execution and state.approval and existing.state.approval.approval_id == state.approval.approval_id:
                return existing.state
            if state.approval is None:
                raise IncidentConflict()
            approval = uow.approvals.get(state.approval.approval_id)
            if approval is None:
                raise IncidentConflict()
            run, _ = validate_approval(uow, approval, self.clock(), decided=True)
            if run.agent_run_id != self.run_id:
                raise AccessError()
            trace = state.approval.model_copy(update={"status": approval.status,
                "phase": "READY_TO_EXECUTE" if approval.status == "APPROVED" else "REJECTED",
                "resumed_at": self.clock(), "decision_actor": approval.decided_by,
                "decision_reason_code": "HUMAN_APPROVED" if approval.status == "APPROVED" else "HUMAN_REJECTED"})
            result = WorkflowState.model_validate(state.model_copy(update={"approval": trace,
                "status": WorkflowStatus.RUNNING}).model_dump(mode="json"))
            uow.agent_runs.save(run.model_copy(update={"state": result, "status": WorkflowStatus.RUNNING}))
            uow.audit.append(AuditRecord(str(uuid5(NAMESPACE_URL, "approval-resumed:"+run.agent_run_id)),
                run.tenant_id, approval.decided_by, "workflow_resume", "agent_run", run.agent_run_id,
                "SUCCESS", run.agent_run_id, run.correlation_id, self.clock().isoformat(), approval.version))
            return result


class SafeJsonSerializer:
    def dumps_typed(self, value):
        def encode(item):
            # SDK의 고정 Interrupt 한 타입만 허용합니다. pickle/동적 클래스 import는 금지합니다.
            if isinstance(item, Interrupt) and item.response_schema is None:
                return {"__serviq_interrupt__": {"id": item.id, "value": item.value}}
            if isinstance(item, Send) and item.node == "investigate_branch":
                if set(item.arg) != {"context", "branch_id"}:
                    raise ValueError("INVALID_BRANCH_CHECKPOINT")
                AgentContextPack.model_validate(item.arg["context"])
                return {"__serviq_branch__": item.arg}
            raise TypeError("지원하지 않는 Checkpoint 값입니다.")
        return "json", json.dumps(value, ensure_ascii=False, allow_nan=False, default=encode).encode()

    def loads_typed(self, value):
        kind, data = value
        if kind != "json":
            raise ValueError("알 수 없는 Checkpoint 직렬화 형식입니다.")
        def decode(item):
            if set(item) == {"__serviq_branch__"}:
                arg = item["__serviq_branch__"]
                if not isinstance(arg, dict) or set(arg) != {"context", "branch_id"}:
                    raise ValueError("INVALID_BRANCH_CHECKPOINT")
                AgentContextPack.model_validate(arg["context"])
                return Send("investigate_branch", arg)
            if set(item) == {"__serviq_interrupt__"}:
                safe = item["__serviq_interrupt__"]
                if not isinstance(safe, dict) or set(safe) != {"id", "value"} or not isinstance(safe["id"], str):
                    raise ValueError("유효한 승인 중단 Checkpoint가 아닙니다.")
                return Interrupt(id=safe["id"], value=safe["value"])
            return item
        return json.loads(data, object_hook=decode)


def memory_checkpoint():
    return InMemorySaver(serde=SafeJsonSerializer())


@contextmanager
def postgres_checkpoint(dsn):
    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.serde = SafeJsonSerializer()
        saver.setup()
        yield saver


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
                 executor_factory=configured_llm_executor, clock=None, lease_seconds=60, source=None):
        self.persistence, self.search, self.checkpoint_factory = persistence, search, checkpoint_factory
        self.dsn, self.executor_factory, self.lease_seconds = dsn, executor_factory, lease_seconds
        self.clock = clock or (lambda: datetime.now(UTC))
        self.source = source

    def __call__(self, job):
        with execution_lease(self.dsn, job, self.lease_seconds) as check:
            run, resolved, decision = HistoryWorkflows(self.persistence, self.clock, self.source).prepare(job)
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
                if run.workflow_version == "multi-investigation-v5":
                    return state
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
                    if run.workflow_version == "multi-investigation-v5":
                        policy = uow.configs.current()
                        if policy is None or not policy.config.auto_rca_draft:
                            return RCAInvestigation.gap(state, "RCA_DISABLED")
                        if decision.result.requires_llm and (not policy.config.hosted_ai_allowed
                                or not set(resolved.effective.llm_enabled_providers) <= set(policy.config.llm_enabled_providers)):
                            return RCAInvestigation.gap(state, "LLM_POLICY_DENIED")
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
                            15 if run.workflow_version in {"history-verification-v4", "multi-investigation-v5"} else
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
                    multi = run.workflow_version == "multi-investigation-v5"
                    if multi:
                        if self.source is None or run.state.selection is None:
                            raise WorkflowNotAllowed()
                        with self.persistence.transaction(job.tenant_id) as uow:
                            current = uow.configs.current()
                            tools = {"HISTORY": "voc.search", "TRANSACTION": "transaction.search", "INVENTORY": "inventory.snapshot"}
                            if (current is None or not current.config.multi_agent_enabled or not current.config.auto_investigation
                                    or any(c.agent_type not in current.config.allowed_agent_types or tools[c.agent_type] not in current.config.allowed_tools
                                        or c.category in current.config.blocked_categories for c in run.state.contexts)):
                                raise WorkflowNotAllowed()
                            require(Principal(run.requested_by or "", job.tenant_id, frozenset(run.delegated_roles),
                                frozenset(run.delegated_store_scope)), "operate", job.store)

                        def branch(pack, branch_id):
                            check()
                            if (pack not in run.state.contexts
                                    or branch_id != str(uuid5(NAMESPACE_URL, run.agent_run_id+":"+pack.agent_type))):
                                raise AccessError()
                            with self.persistence.transaction(job.tenant_id) as uow:
                                previous = uow.agent_runs.branch(run.agent_run_id, pack.agent_type)
                                if previous and run.state.loop is None:
                                    return previous
                            def action(context, bid):
                                if context.agent_type != "HISTORY":
                                    return OperationalInvestigation(self.source, self.clock)(context, bid)
                                # 이 branch는 참조 검색만 수행합니다. LLM 요약은 불필요하며 RCA는 기존 Gateway를 사용합니다.
                                started = self.clock()
                                try:
                                    found = HistoryInvestigation(self.search, store=pack.store, query=incident.title,
                                        resolved=resolved, requires_llm=False, clock=self.clock)(run.state)
                                except psycopg.Error:
                                    raise SourceUnavailable() from None
                                return InvestigationResult(agent_type="HISTORY", branch_id=bid, tenant_id=pack.tenant_id,
                                    incident_id=pack.incident_id, store=pack.store,
                                    status="SUCCESS" if found.evidence_refs else "NO_EVIDENCE",
                                    findings=found.findings, evidence_candidates=found.evidence_candidates,
                                    evidence_gaps=found.evidence_gaps, started_at=started, completed_at=self.clock(),
                                    uncertainty="OBSERVATIONS_NOT_CAUSE", context_digest=pack.digest)
                            def bounded_action(context, bid):
                                return isolated_branch(action, context, bid, clock=self.clock,
                                    deadline=run.started_at+timedelta(seconds=resolved.effective.timeout_seconds))
                            if run.state.loop:
                                return InvestigationLoop(self.persistence, run.agent_run_id, job.tenant_id,
                                    self.source, self.clock).execute(pack, branch_id, bounded_action)
                            result = bounded_action(pack, branch_id)
                            check()
                            with self.persistence.transaction(job.tenant_id) as uow:
                                return uow.agent_runs.append_branch(run.agent_run_id, result)

                        def collect(state):
                            result = investigation_fan_in(state)
                            if run.state.loop:
                                with self.persistence.transaction(job.tenant_id) as uow:
                                    stored = uow.agent_runs.get(run.agent_run_id).state
                                loop = stored.loop.model_copy(update={"termination": stored.loop.termination or "COMPLETED"})
                                result = result.model_copy(update={"iteration": stored.iteration,
                                    "tool_call_count": stored.tool_call_count, "loop": loop})
                            persist(result)
                            observe("history_investigation", state, result, 0)
                            return result
                        stages.update(investigate_branch=branch, fan_in=collect)
                    if run.workflow_version in {"history-capa-v3", "history-verification-v4"} or (multi and resolved.effective.auto_capa_draft):
                        commands = CAPACommands(self.persistence, run.agent_run_id, job.tenant_id, self.clock)
                        def request_approval(state):
                            check()
                            result = commands.request_approval(state).model_copy(update={"status": WorkflowStatus.WAITING_APPROVAL})
                            persist(result)
                            return result
                        stages.update(capa=CAPAInvestigation(resolved, run.jev_decision_id,
                            store=job.store, incident_severity=incident.severity), apply_capa=commands.apply,
                            request_approval=request_approval, approval_result=commands.approval_result)
                        if run.workflow_version == "history-verification-v4" or (multi and resolved.effective.internal_execution_enabled):
                            vc = VerificationCommands(self.persistence, run.agent_run_id, job.tenant_id, self.clock)
                            stages.update(internal_execution=vc.execute, begin_verification=vc.begin_verification,
                                verification=vc.evaluate, apply_verification=vc.apply)
                    graph = history_graph(saver, investigate, persist, observe=observe, **stages)
                    result = invoke_or_resume(graph, run.state,
                        approval_id=job.payload_ref if job.job_type == RESUME_JOB else None,
                        parallelism=resolved.effective.parallelism)
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
