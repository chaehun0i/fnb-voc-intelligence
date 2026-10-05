"""승인은 조치 내용과 검토자의 의사결정을 보존합니다."""

import hashlib
import json
from dataclasses import asdict, dataclass

from src.domain.incidents.enums import Severity
from src.domain.incidents.models import Incident


def action_digest(incident: Incident) -> str:
    actions = [{key: value for key, value in asdict(action).items() if key != "status"
                and not (key in {"action_type", "target_reference"} and value is None)}
               for action in incident.corrective_actions]
    canonical = json.dumps(sorted(actions, key=lambda action: action["id"]),
                           sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class Approval:
    approval_id: str
    tenant_id: str
    incident_id: str
    action_ids: tuple[str, ...]
    action_digest: str
    incident_version: int
    risk_level: Severity
    requested_by: str
    requested_at: str
    expires_at: str
    status: str = "PENDING"
    decided_by: str | None = None
    decided_at: str | None = None
    decision_reason: str | None = None
    version: int = 1
    agent_run_id: str | None = None
    config_version: int | None = None
    policy_digest: str | None = None
    required_roles: tuple[str, ...] = ()
    separation_of_duties: bool = False

    def __post_init__(self):
        object.__setattr__(self, "action_ids", tuple(self.action_ids))
        object.__setattr__(self, "required_roles", tuple(self.required_roles))
        object.__setattr__(self, "risk_level", Severity(self.risk_level))
        if self.status not in {"PENDING", "APPROVED", "REJECTED"}:
            raise ValueError("유효한 승인 상태가 필요합니다.")
