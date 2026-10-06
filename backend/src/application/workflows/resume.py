"""HTTP 결정은 승인 원본만 변경하고 재개는 기존 durable Job으로 전달합니다."""
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from src.application.ports.incident_repository import IncidentConflict
from src.application.workflows.approval_policy import approval_policy_digest
from src.domain.approvals.models import action_digest
from src.domain.jobs.models import Job

RESUME_JOB = "incident.history_resume"


def validate_approval(uow, approval, now, *, decided=False):
    run = uow.agent_runs.get(approval.agent_run_id) if approval.agent_run_id else None
    item = uow.incidents.get(approval.incident_id)
    current = uow.configs.current()
    trace = run.state.approval if run else None
    if (run is None or trace is None or item is None or current is None
            or run.workflow_version not in {"history-capa-v3", "history-verification-v4"}
            or run.config_version != approval.config_version
            or trace.approval_id != approval.approval_id or trace.action_digest != approval.action_digest
            or set(approval.action_ids) != {a.id for a in item.corrective_actions}
            or action_digest(item) != approval.action_digest
            or item.version != approval.incident_version+int(decided)
            or approval.policy_digest != approval_policy_digest(current.config)
            or now >= datetime.fromisoformat(approval.expires_at)):
        raise IncidentConflict()
    if decided:
        if not ((approval.status == "APPROVED" and item.status == "PENDING_APPROVAL" and item.approved
                 and all(a.status == "APPROVED" for a in item.corrective_actions))
                or (approval.status == "REJECTED" and item.status == "ACTION_PROPOSED" and not item.approved)):
            raise IncidentConflict()
    elif approval.status != "PENDING" or item.status != "PENDING_APPROVAL" or item.approved:
        raise IncidentConflict()
    return run, item


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
