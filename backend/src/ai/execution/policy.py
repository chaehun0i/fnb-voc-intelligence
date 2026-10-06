"""승인 원본·현재 정책·digest 검증: Workflow runtime에 의존하지 않습니다."""
from datetime import datetime

from src.ai.workflow.policy import approval_policy_digest
from src.application.ports.incident_repository import IncidentConflict
from src.domain.approvals.models import action_digest


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

