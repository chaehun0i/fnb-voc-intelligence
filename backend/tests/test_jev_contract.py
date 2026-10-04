from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from src.decision.jev.models import Category, DecisionContext, RequestedMode
from src.domain.config.models import RuntimeConfig
from src.domain.config.resolution import ConfigResolver
from src.domain.incidents.enums import IncidentStatus, Priority, Severity


def context(**changes):
    values = {"tenant_id": "tenant", "incident_id": "incident", "incident_status": IncidentStatus.DETECTED,
        "severity": Severity.MEDIUM, "priority": Priority.P2, "category": Category.GENERAL, "store_id": "store",
        "known_evidence_types": (), "data_availability": (), "recurrence_hint": False,
        "requested_mode": RequestedMode.AUTO, "policy": ConfigResolver().resolve(RuntimeConfig()),
        "config_version": 0, "occurred_at": datetime(2026, 10, 4, tzinfo=UTC)}
    return DecisionContext(**{**values, **changes})


def test_context_is_immutable_and_keeps_version():
    value = context(config_version=3)
    assert value == context(config_version=3)
    with pytest.raises(FrozenInstanceError):
        value.config_version = 4
