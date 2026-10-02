"""인시던트 도메인 객체와 저장용 JSON 사이를 변환합니다."""

from dataclasses import asdict

from src.domain.incidents.enums import (
    ActionStatus,
    EvidenceStatus,
    IncidentStatus,
    Priority,
    Severity,
    VerificationResult,
)
from src.domain.incidents.models import (
    CorrectiveAction,
    Evidence,
    Incident,
    RootCauseCandidate,
    StateTransition,
    Verification,
)


def incident_document(incident: Incident) -> dict:
    return asdict(incident)


def incident_from_document(document: dict) -> Incident:
    values = dict(document)
    values["status"] = IncidentStatus(values["status"])
    values["severity"] = Severity(values["severity"])
    values["priority"] = Priority(values.get("priority", "P2"))
    values["evidence"] = [Evidence(**{**item, "status": EvidenceStatus(item["status"])}) for item in values.get("evidence", [])]
    values["root_cause_candidates"] = [RootCauseCandidate(**item) for item in values.get("root_cause_candidates", [])]
    values["corrective_actions"] = [CorrectiveAction(**{**item, "risk_level": Severity(item["risk_level"]), "status": ActionStatus(item["status"])}) for item in values.get("corrective_actions", [])]
    values["timeline"] = [StateTransition(**{**item, "status": IncidentStatus(item["status"])}) for item in values.get("timeline", [])]
    if values.get("verification"):
        values["verification"] = Verification(**{**values["verification"], "result": VerificationResult(values["verification"]["result"])})
    return Incident(**values)
