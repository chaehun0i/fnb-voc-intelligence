"""화면과 API가 공유하는 인시던트 상태와 분류 값입니다."""

from enum import StrEnum


class IncidentStatus(StrEnum):
    DETECTED = "DETECTED"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    RCA_READY = "RCA_READY"
    ACTION_PROPOSED = "ACTION_PROPOSED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    ESCALATED = "ESCALATED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    REOPENED = "REOPENED"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


class ActionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"


class VerificationResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class Priority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
