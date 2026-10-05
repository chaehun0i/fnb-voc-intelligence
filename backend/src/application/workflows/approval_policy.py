"""실행 도중 Provider 설정은 바뀌어도 승인 안전 정책은 약화할 수 없습니다."""
import hashlib
import json
from dataclasses import asdict


def approval_policy_digest(config):
    policy = {"risk": asdict(config.approval_policy_by_risk),
              "roles": sorted(config.required_roles), "separation": config.separation_of_duties,
              "critical_count": config.critical_approver_count, "auto_capa_draft": config.auto_capa_draft}
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
