"""실제 Approval과 Incident에서 검토 화면의 자료를 구성합니다."""
from dataclasses import asdict
from datetime import datetime

from src.application.incidents.service import IncidentNotFound
from src.application.security.authorization import allowed, require
from src.application.workflows.approval_policy import approval_policy_digest
from src.domain.approvals.models import action_digest
from src.domain.incidents.enums import Severity


class ReviewQueries:
    def __init__(self, incidents, approvals, context, current_config=None):
        self.incidents, self.approvals, self.context = incidents, approvals, context
        self.current_config = current_config

    def list(self, status=None, limit=100, offset=0):
        require(self.context.principal, "read")
        rows = []
        for approval in self.approvals.list():
            if status and approval.status != status:
                continue
            item = self.incidents.repo.get(approval.incident_id)
            if item and allowed(self.context.principal, "read", item.store):
                rows.append(self._project(approval, item)["approval"])
        return rows[offset:offset+limit]

    def get(self, approval_id):
        approval = self.approvals.get(approval_id)
        if approval is None:
            raise IncidentNotFound()
        return self._project(approval, self.incidents.get(approval.incident_id))

    def _project(self, approval, item):
        actions = [action for action in item.corrective_actions if action.id in approval.action_ids]
        now = datetime.fromisoformat(self.incidents._now())
        reason = "조치안과 근거를 확인한 뒤 결정할 수 있습니다."
        available = True
        if not allowed(self.context.principal, "review", item.store):
            available, reason = False, "현재 역할 또는 매장 범위에서는 검토할 수 없습니다."
        elif approval.status != "PENDING":
            available, reason = False, "이미 검토 결과가 기록되었습니다."
        elif approval.required_roles and not set(approval.required_roles) & self.context.principal.roles:
            available, reason = False, "이 조치의 승인 정책에서 지정한 검토자 역할이 필요합니다."
        elif approval.agent_run_id and (self.current_config is None or
                approval.policy_digest != approval_policy_digest(self.current_config.config)):
            available, reason = False, "승인 정책이 변경되어 이 요청을 재검토해야 합니다."
        elif now >= datetime.fromisoformat(approval.expires_at):
            available, reason = False, "검토 기한이 지나 새 승인 요청이 필요합니다."
        elif item.version != approval.incident_version or action_digest(item) != approval.action_digest:
            available, reason = False, "조치안이 변경되어 새 승인 요청이 필요합니다."
        approve = available and not ((approval.risk_level == Severity.CRITICAL or approval.separation_of_duties)
                                    and approval.requested_by == self.context.principal.principal_id)
        permissions = {
            "approve": {"allowed": approve, "reason": reason if approve or not available else "최고 위험 조치는 요청자와 다른 검토자가 승인해야 합니다."},
            "reject": {"allowed": available, "reason": reason},
            "edit": {"allowed": False, "reason": "현재 HTTP 계약은 승인·반려만 지원합니다."},
            "request_more_evidence": {"allowed": False, "reason": "추가 증거 요청 명령은 다음 확장 단계에서 연결합니다."},
        }
        history = [{"occurred_at": approval.requested_at, "actor": approval.requested_by,
                    "summary": "조치 검토를 요청했습니다."}]
        if approval.decided_at:
            history.append({"occurred_at": approval.decided_at, "actor": approval.decided_by,
                            "summary": approval.decision_reason})
        return {
            "approval": {"id": approval.approval_id, "incident_id": item.id,
                         "type": "Corrective Action", "risk_level": approval.risk_level,
                         "requester": approval.requested_by, "requested_at": approval.requested_at,
                         "evidence_completeness": round(100*sum(e.status == "AVAILABLE" for e in item.evidence)/len(item.evidence)) if item.evidence else 0,
                         "status": approval.status, "version": approval.version, "actions": permissions},
            "detail": {"approval_id": approval.approval_id, "incident_display_id": item.display_id,
                       "incident_title": item.title, "proposed_action": "\n".join(a.summary for a in actions),
                       "expected_effect": "\n".join(a.expected_effect for a in actions),
                       "verification_criteria": "\n".join(a.verification_criteria for a in actions),
                       "due_at": approval.expires_at, "evidence": [asdict(e) for e in item.evidence],
                       "history": history},
        }
