"""원문을 복제하지 않고 등록된 증거 타입만 Decision 사실로 변환합니다."""
from datetime import datetime

from src.decision.jev.models import AgentType, Category, DecisionContext, RequestedMode
from src.domain.incidents.enums import EvidenceStatus


def build_context(incident, resolved, config_version, *, requested_mode=RequestedMode.AUTO):
    # category/recurrence가 Incident에 없으므로 제목·VOC에서 추측하지 않습니다.
    present = tuple(agent for agent in AgentType if any(e.type.upper() == agent.value for e in incident.evidence))
    available = tuple(agent for agent in present if any(e.type.upper() == agent.value and e.status == EvidenceStatus.AVAILABLE for e in incident.evidence))
    category = Category.COLD_CHAIN if AgentType.TEMPERATURE in present else (
        Category.SUPPLIER_LOT if AgentType.LOT in present or AgentType.SUPPLIER in present else
        Category.TRANSACTION if AgentType.TRANSACTION in present else Category.UNKNOWN)
    return DecisionContext(incident.tenant_id, incident.id, incident.status, incident.severity,
        incident.priority, category, incident.store, present, available, False, requested_mode,
        resolved, config_version, datetime.fromisoformat(incident.created_at))
