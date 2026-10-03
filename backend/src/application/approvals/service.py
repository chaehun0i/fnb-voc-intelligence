"""승인 요청과 결정은 기존 Incident 규칙을 재사용합니다."""

from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

from src.application.ports.incident_repository import IncidentConflict
from src.application.security.authorization import require
from src.application.security.principal import AccessError
from src.domain.approvals.models import Approval, action_digest
from src.domain.incidents.enums import Severity
from src.domain.incidents.transitions import DomainRuleViolation


class ApprovalService:
    def __init__(self, incidents, approvals, context):
        self.incidents, self.approvals, self.context = incidents, approvals, context

    def request(self, incident_id, expected_version=None):
        item = self.incidents.request_approval(incident_id, expected_version)
        now = self.incidents._now()
        ranks = list(Severity)
        risk = max((action.risk_level for action in item.corrective_actions),
                   key=ranks.index)
        self.approvals.save(Approval(
            str(uuid4()), item.tenant_id, item.id,
            tuple(action.id for action in item.corrective_actions),
            action_digest(item), item.version, risk,
            self.context.principal.principal_id, now,
            (datetime.fromisoformat(now)+timedelta(hours=24)).isoformat(),
        ))
        return item

    def decide(self, approval_id, decision, reason, expected_version=None):
        approval = self.approvals.get(approval_id)
        if approval is None:
            from src.application.incidents.service import IncidentNotFound
            raise IncidentNotFound()
        item = self.incidents.get(approval.incident_id)
        require(self.context.principal, "review", item.store)
        if approval.status != "PENDING" or (
            expected_version is not None and approval.version != expected_version
        ):
            raise IncidentConflict()
        now = self.incidents._now()
        if (action_digest(item) != approval.action_digest
                or item.version != approval.incident_version
                or datetime.fromisoformat(now) >= datetime.fromisoformat(approval.expires_at)):
            raise IncidentConflict()
        if decision == "approve" and approval.risk_level == Severity.CRITICAL and (
            approval.requested_by == self.context.principal.principal_id
        ):
            raise AccessError()
        if decision not in {"approve", "reject"} or not reason.strip():
            raise ValueError("승인 또는 반려 사유가 필요합니다.")
        saved = getattr(self.incidents, decision)(item.id, item.version)
        self.approvals.save(replace(
            approval, status="APPROVED" if decision == "approve" else "REJECTED",
            decided_by=self.context.principal.principal_id,
            decided_at=now, decision_reason=reason.strip(),
        ))
        return saved

    def decide_incident(self, incident_id, decision, expected_version=None):
        item = self.incidents._load(incident_id, expected_version, "review")
        approvals = self.approvals.list(item.id)
        if not approvals:
            raise IncidentConflict()
        return self.decide(approvals[0].approval_id, decision,
                           "기존 Incident 호환 명령: 별도 사유 미입력")

    def require_effective(self, item):
        approvals = self.approvals.list(item.id)
        if not approvals or approvals[0].status != "APPROVED":
            raise DomainRuleViolation("실행 전에 승인 기록이 필요합니다.")
        approval = approvals[0]
        if (approval.status != "APPROVED" or approval.action_digest != action_digest(item)
                or item.version != approval.incident_version+1
                or datetime.fromisoformat(self.incidents._now()) >= datetime.fromisoformat(approval.expires_at)):
            raise IncidentConflict()
