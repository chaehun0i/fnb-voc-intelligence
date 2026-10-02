"""외부 서비스 없이 수동 운영 흐름과 저장 격리를 확인합니다."""

from dataclasses import replace
from datetime import UTC, datetime
from itertools import count

import pytest

from src.application.incidents.service import IncidentNotFound, IncidentService
from src.application.ports.incident_repository import IncidentConflict
from src.domain.incidents.enums import IncidentStatus, Severity, VerificationResult
from src.domain.incidents.models import CorrectiveAction, Evidence, RootCauseCandidate
from src.domain.incidents.transitions import DomainRuleViolation
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)

NOW = datetime(2026, 10, 1, 9, tzinfo=UTC)


@pytest.fixture
def service():
    identifiers = count(1)
    return IncidentService(
        InMemoryIncidentRepository(),
        clock=lambda: NOW,
        id_generator=lambda: f"incident-{next(identifiers)}",
    )


def create(service):
    return service.create("온도 이상", Severity.HIGH, "강남점", "운영 담당자")


def ready_for_verification(service):
    item = create(service)
    service.triage(item.id)
    service.investigate(item.id)
    service.add_evidence(
        item.id, Evidence("e1", "센서", "TEMPERATURE", "온도 상승", 0.9)
    )
    service.prepare_rca(item.id, [RootCauseCandidate("r1", "장비 이상", 0.8, ["e1"])])
    service.propose_action(
        item.id,
        [
            CorrectiveAction(
                "a1", "냉장 장비 점검", Severity.HIGH, "온도 정상화", "4도 이하"
            )
        ],
    )
    service.request_approval(item.id)
    service.approve(item.id)
    return service.execute(item.id)


def test_manual_closed_loop(service):
    checking = ready_for_verification(service)
    assert checking.status == IncidentStatus.VERIFYING
    assert checking.corrective_actions[0].status == "EXECUTED"
    resolved = service.verify(checking.id, VerificationResult.PASS, "4도 이하 유지")
    assert resolved.status == IncidentStatus.RESOLVED
    closed = service.close(resolved.id)
    assert closed.status == IncidentStatus.CLOSED
    assert [event.status for event in closed.timeline] == [
        IncidentStatus.DETECTED,
        IncidentStatus.TRIAGED,
        IncidentStatus.INVESTIGATING,
        IncidentStatus.RCA_READY,
        IncidentStatus.ACTION_PROPOSED,
        IncidentStatus.PENDING_APPROVAL,
        IncidentStatus.EXECUTING,
        IncidentStatus.VERIFYING,
        IncidentStatus.RESOLVED,
        IncidentStatus.CLOSED,
    ]


def test_failed_command_does_not_change_severity_or_version(service):
    item = create(service)
    classified = service.triage(item.id)
    with pytest.raises(DomainRuleViolation):
        service.triage(item.id, Severity.CRITICAL)
    assert service.get(item.id) == classified


def test_repository_copies_nested_objects_and_checks_version(service):
    item = create(service)
    first_reader = service.get(item.id)
    first_reader.evidence.append(Evidence("e1", "센서", "TEMP", "관측", 0.8))
    assert service.get(item.id).evidence == []
    service.repo.save(replace(item, owner="새 담당자"))
    with pytest.raises(IncidentConflict):
        service.repo.save(replace(item, owner="오래된 담당자"))
    assert service.get(item.id).owner == "새 담당자"


def test_query_filters_and_not_found(service):
    item = create(service)
    assert service.list(severity=Severity.HIGH, store="강남점") == [item]
    assert service.list(status=IncidentStatus.CLOSED) == []
    with pytest.raises(IncidentNotFound):
        service.get("missing")


def test_rca_rejects_missing_or_rejected_evidence(service):
    item = create(service)
    service.triage(item.id)
    service.investigate(item.id)
    with pytest.raises(DomainRuleViolation):
        service.prepare_rca(
            item.id, [RootCauseCandidate("r1", "장비", 0.8, ["missing"])]
        )
    assert service.get(item.id).root_cause_candidates == []


def test_fail_and_inconclusive_verification(service):
    checking = ready_for_verification(service)
    uncertain = service.verify(
        checking.id, VerificationResult.INCONCLUSIVE, "관찰 시간 부족"
    )
    assert uncertain.status == IncidentStatus.VERIFYING
    reopened = service.verify(checking.id, VerificationResult.FAIL, "온도 재상승")
    assert reopened.status == IncidentStatus.REOPENED
    assert not reopened.approved
    assert reopened.corrective_actions == []
    assert service.investigate(reopened.id).status == IncidentStatus.INVESTIGATING


def test_approval_rejection_returns_to_proposal(service):
    checking = ready_for_verification(service)
    pending = replace(checking, status=IncidentStatus.PENDING_APPROVAL)
    service.repo.save(pending)
    rejected = service.reject(checking.id)
    assert rejected.status == IncidentStatus.ACTION_PROPOSED
    assert not rejected.approved
    assert rejected.corrective_actions[0].status == "PROPOSED"
    revised = service.propose_action(
        checking.id,
        [
            CorrectiveAction(
                "a2",
                "장비 교체 후 재측정",
                Severity.MEDIUM,
                "재발 감소",
                "24시간 안정 유지",
            )
        ],
    )
    assert revised.status == IncidentStatus.ACTION_PROPOSED
    assert revised.corrective_actions[0].id == "a2"
    assert not revised.approved
    assert (
        service.request_approval(revised.id).status == IncidentStatus.PENDING_APPROVAL
    )


def test_expected_version_rejects_stale_command(service):
    item = create(service)
    service.triage(item.id)
    with pytest.raises(IncidentConflict):
        service.investigate(item.id, expected_version=item.version)


def test_permissions_come_from_application_state(service):
    item = create(service)
    workspace = service.workspace(item.id)
    assert workspace["commands"]["triage"]["allowed"]
    assert not workspace["commands"]["execute"]["allowed"]
    service.triage(item.id)
    assert service.workspace(item.id)["commands"]["investigate"]["allowed"]
