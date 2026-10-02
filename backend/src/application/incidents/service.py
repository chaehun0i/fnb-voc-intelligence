"""수동 운영 명령을 검증하고 저장하는 애플리케이션 서비스입니다."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.application.ports.incident_repository import (
    IncidentConflict,
    IncidentRepository,
)
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
from src.domain.incidents.transitions import (
    DomainRuleViolation,
    require_status,
    transition,
)


class IncidentNotFound(LookupError):
    """조회할 인시던트가 없습니다."""


class IncidentService:
    def __init__(
        self,
        repo: IncidentRepository,
        clock: Callable[[], datetime] | None = None,
        id_generator: Callable[[], str] | None = None,
    ) -> None:
        self.repo = repo
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id_generator = id_generator or (lambda: str(uuid4()))

    def _now(self) -> str:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("시계는 시간대가 있는 시각을 반환해야 합니다.")
        return now.isoformat()

    def list(
        self,
        status: IncidentStatus | None = None,
        severity: Severity | None = None,
        store: str | None = None,
    ) -> list[Incident]:
        return self.repo.list(status=status, severity=severity, store=store)

    def get(self, incident_id: str) -> Incident:
        item = self.repo.get(incident_id)
        if item is None:
            raise IncidentNotFound(incident_id)
        return item

    def _load(self, incident_id: str, expected_version: int | None) -> Incident:
        item = self.get(incident_id)
        if expected_version is not None and item.version != expected_version:
            raise IncidentConflict("인시던트의 최신 버전을 다시 확인해 주세요.")
        return item

    def create(
        self,
        title: str,
        severity: Severity,
        store: str,
        owner: str,
        sla_due_at: str | None = None,
        priority: Priority = Priority.P2,
    ) -> Incident:
        now = self._now()
        identifier = self.id_generator()
        if self.repo.get(identifier) is not None:
            raise IncidentConflict("이미 등록된 인시던트입니다.")
        due_at = (
            sla_due_at
            or (datetime.fromisoformat(now) + timedelta(hours=24)).isoformat()
        )
        if datetime.fromisoformat(due_at) <= (datetime.fromisoformat(now)):
            raise DomainRuleViolation("SLA 기한은 발생 시각보다 늦어야 합니다.")
        return self.repo.save(
            Incident(
                id=identifier,
                display_id=f"INC-{identifier[:8].upper()}",
                title=title,
                severity=severity,
                status=IncidentStatus.DETECTED,
                store=store,
                owner=owner,
                created_at=now,
                sla_due_at=due_at,
                timeline=[StateTransition(IncidentStatus.DETECTED, now)],
                priority=priority,
            )
        )

    def triage(
        self,
        incident_id: str,
        severity: Severity | None = None,
        occurred_at: str | None = None,
        expected_version: int | None = None,
    ) -> Incident:
        item = self._load(incident_id, expected_version)
        classified = replace(
            item, severity=Severity(severity) if severity else item.severity
        )
        if occurred_at is not None and datetime.fromisoformat(occurred_at) < (
            datetime.fromisoformat(item.created_at)
        ):
            raise DomainRuleViolation("분류 시각은 발생 시각보다 빠를 수 없습니다.")
        return self.repo.save(
            transition(
                classified,
                IncidentStatus.TRIAGED,
                occurred_at or self._now(),
            )
        )

    def investigate(
        self,
        incident_id: str,
        expected_version: int | None = None,
    ) -> Incident:
        item = self._load(incident_id, expected_version)
        return self.repo.save(
            transition(item, IncidentStatus.INVESTIGATING, self._now())
        )

    def add_evidence(
        self,
        incident_id: str,
        evidence: Evidence,
        expected_version: int | None = None,
    ) -> Incident:
        item = self._load(incident_id, expected_version)
        require_status(item, IncidentStatus.INVESTIGATING)
        if any(existing.id == evidence.id for existing in item.evidence):
            raise DomainRuleViolation("같은 증거 ID를 중복 등록할 수 없습니다.")
        return self.repo.save(replace(item, evidence=[*item.evidence, evidence]))

    def prepare_rca(
        self,
        incident_id: str,
        candidates: list[RootCauseCandidate],
        expected_version: int | None = None,
    ) -> Incident:
        item = self._load(incident_id, expected_version)
        require_status(item, IncidentStatus.INVESTIGATING)
        if len({candidate.id for candidate in candidates}) != len(candidates):
            raise DomainRuleViolation("원인 후보 ID는 서로 달라야 합니다.")
        available = {
            evidence.id
            for evidence in item.evidence
            if evidence.status == EvidenceStatus.AVAILABLE
        }
        for candidate in candidates:
            referenced = set(
                candidate.supporting_evidence_ids + candidate.counter_evidence_ids,
            )
            if not candidate.supporting_evidence_ids or not referenced <= available:
                raise DomainRuleViolation(
                    "원인 후보에는 사용 가능한 근거가 필요합니다."
                )
            if set(candidate.supporting_evidence_ids) & set(
                candidate.counter_evidence_ids
            ):
                raise DomainRuleViolation(
                    "같은 증거를 찬성·반대 근거로 중복할 수 없습니다."
                )
        updated = replace(item, root_cause_candidates=candidates)
        return self.repo.save(
            transition(updated, IncidentStatus.RCA_READY, self._now())
        )

    def propose_action(
        self,
        incident_id: str,
        actions: list[CorrectiveAction],
        expected_version: int | None = None,
    ) -> Incident:
        item = self._load(incident_id, expected_version)
        require_status(item, IncidentStatus.RCA_READY, IncidentStatus.ACTION_PROPOSED)
        if len({action.id for action in actions}) != len(actions):
            raise DomainRuleViolation("조치 ID는 서로 달라야 합니다.")
        proposed = [replace(action, status=ActionStatus.PROPOSED) for action in actions]
        updated = replace(item, corrective_actions=proposed, approved=False)
        if item.status is IncidentStatus.ACTION_PROPOSED:
            return self.repo.save(updated)
        return self.repo.save(
            transition(
                updated,
                IncidentStatus.ACTION_PROPOSED,
                self._now(),
            )
        )

    def request_approval(
        self,
        incident_id: str,
        expected_version: int | None = None,
    ) -> Incident:
        item = self._load(incident_id, expected_version)
        return self.repo.save(
            transition(item, IncidentStatus.PENDING_APPROVAL, self._now())
        )

    def approve(
        self,
        incident_id: str,
        expected_version: int | None = None,
    ) -> Incident:
        item = self._load(incident_id, expected_version)
        require_status(item, IncidentStatus.PENDING_APPROVAL)
        if item.approved:
            raise DomainRuleViolation("이미 승인한 조치입니다.")
        return self.repo.save(
            replace(
                item,
                approved=True,
                corrective_actions=[
                    replace(action, status=ActionStatus.APPROVED)
                    for action in item.corrective_actions
                ],
            )
        )

    def reject(
        self,
        incident_id: str,
        expected_version: int | None = None,
    ) -> Incident:
        item = self._load(incident_id, expected_version)
        require_status(item, IncidentStatus.PENDING_APPROVAL)
        rejected = transition(
            item,
            IncidentStatus.ACTION_PROPOSED,
            self._now(),
            rejected=True,
        )
        return self.repo.save(
            replace(
                rejected,
                corrective_actions=[
                    replace(action, status=ActionStatus.PROPOSED)
                    for action in item.corrective_actions
                ],
            )
        )

    def execute(
        self,
        incident_id: str,
        expected_version: int | None = None,
    ) -> Incident:
        """실제 외부 변경 없이 승인된 조치의 수동 실행을 기록합니다."""
        item = self._load(incident_id, expected_version)
        now = self._now()
        executing = transition(item, IncidentStatus.EXECUTING, now)
        executed = replace(
            executing,
            corrective_actions=[
                replace(action, status=ActionStatus.EXECUTED)
                for action in executing.corrective_actions
            ],
        )
        return self.repo.save(transition(executed, IncidentStatus.VERIFYING, now))

    def verify(
        self,
        incident_id: str,
        result: VerificationResult,
        summary: str,
        expected_version: int | None = None,
    ) -> Incident:
        item = self._load(incident_id, expected_version)
        require_status(item, IncidentStatus.VERIFYING)
        now = self._now()
        verified = replace(
            item,
            verification=Verification(
                result=result,
                summary=summary,
                id=self.id_generator(),
                verified_at=now,
            ),
        )
        if result == VerificationResult.PASS:
            verified = transition(verified, IncidentStatus.RESOLVED, now)
        elif result == VerificationResult.FAIL:
            verified = transition(verified, IncidentStatus.REOPENED, now)
        return self.repo.save(verified)

    def close(
        self,
        incident_id: str,
        expected_version: int | None = None,
    ) -> Incident:
        item = self._load(incident_id, expected_version)
        return self.repo.save(transition(item, IncidentStatus.CLOSED, self._now()))

    def reopen(
        self,
        incident_id: str,
        reason: str,
        expected_version: int | None = None,
    ) -> Incident:
        if not reason.strip():
            raise DomainRuleViolation("재발 사유를 기록해 주세요.")
        item = self._load(incident_id, expected_version)
        return self.repo.save(
            transition(
                item,
                IncidentStatus.REOPENED,
                self._now(),
                recurrence=True,
                reason=reason,
            )
        )

    def workspace(self, incident_id: str) -> dict:
        item = self.get(incident_id)
        actions = {
            "investigate": item.status
            in {IncidentStatus.TRIAGED, IncidentStatus.REOPENED},
            "propose_action": item.status
            in {
                IncidentStatus.RCA_READY,
                IncidentStatus.ACTION_PROPOSED,
            },
            "execute": item.status is IncidentStatus.PENDING_APPROVAL and item.approved,
        }
        commands = {
            "triage": item.status is IncidentStatus.DETECTED,
            "investigate": actions["investigate"],
            "evidence": item.status is IncidentStatus.INVESTIGATING,
            "rca": item.status is IncidentStatus.INVESTIGATING
            and any(
                evidence.status == EvidenceStatus.AVAILABLE
                for evidence in item.evidence
            ),
            "actions": actions["propose_action"],
            "request-approval": item.status is IncidentStatus.ACTION_PROPOSED,
            "approve": item.status is IncidentStatus.PENDING_APPROVAL
            and not item.approved,
            "reject": item.status is IncidentStatus.PENDING_APPROVAL,
            "execute": actions["execute"],
            "verify": item.status is IncidentStatus.VERIFYING,
            "close": item.status is IncidentStatus.RESOLVED,
            "reopen": item.status is IncidentStatus.RESOLVED,
        }

        def permissions(values: dict[str, bool]) -> dict:
            return {
                action: {
                    "allowed": allowed,
                    "reason": "진행할 수 있습니다."
                    if allowed
                    else "현재 단계의 선행 작업을 완료해 주세요.",
                }
                for action, allowed in values.items()
            }

        return {
            "priority": item.priority,
            "tasks": [],
            "actions": permissions(actions),
            "commands": permissions(commands),
        }
