"""예약 Runtime 계약은 HTTP와 독립적으로 왕복·복사할 수 있습니다."""
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from src.domain.config.models import (
    ConfigVersion,
    RuntimeConfig,
    version_document,
    version_from_document,
)


def test_immutable_config_version_roundtrip():
    original = ConfigVersion(1, "tenant-a", RuntimeConfig(), "초기 설정", "admin", datetime(2026, 10, 4, tzinfo=UTC))
    assert version_from_document(version_document(original)) == original
    with pytest.raises(FrozenInstanceError):
        original.config.max_tool_calls = 100
    with pytest.raises(FrozenInstanceError):
        original.config.approval_policy_by_risk.HIGH = False
    assert original.config.default_llm_provider == "gemini"
    assert original.config.allowed_tools == ()
