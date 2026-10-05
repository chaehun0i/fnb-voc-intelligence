"""권한과 고정 Config/Jev 원본을 확인한 뒤에만 History Job을 등록합니다."""
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from src.application.incidents.service import IncidentNotFound
from src.application.security.authorization import require
from src.decision.jev.models import AgentType, DecisionRoute
from src.domain.approvals.audit import AuditRecord
from src.domain.config.resolution import ConfigResolver
from src.domain.incidents.enums import IncidentStatus
from src.domain.jobs.models import Job
from src.domain.workflows.models import AgentRun, WorkflowState

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
    def __init__(self, persistence, clock=None):
        self.persistence = persistence
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
                max_attempts=version.config.retry_limit+1))
            uow.audit.append(AuditRecord(str(uuid5(NAMESPACE_URL, "history-audit:"+job_id)),
                principal.tenant_id, principal.principal_id, "history_enqueue", "job", job_id,
                "SUCCESS", context.request_id, context.correlation_id, now.isoformat(), incident.version))
            return job

    def prepare(self, job):
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
            run = AgentRun(agent_run_id=rid, tenant_id=job.tenant_id, incident_id=incident.id,
                workflow_id=wid, job_id=job.job_id, correlation_id=job.correlation_id,
                config_version=version.config_version, jev_decision_id=decision.decision_id,
                started_at=self.clock(), state=state)
            return uow.agent_runs.save(run), resolved, decision
