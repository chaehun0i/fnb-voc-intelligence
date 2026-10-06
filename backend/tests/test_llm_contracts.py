"""외부 모델 없이 공통 계약의 입력과 불변성을 확인합니다."""
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.ai.intelligence.models import LLMIntent


def intent(**changes):
    values = {"request_id": "request", "correlation_id": "correlation", "tenant_id": "tenant",
        "task_type": "SUMMARY", "payload_json": '{"count":1}',
        "output_schema_json": json.dumps({"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}),
        "schema_version": "1", "prompt_template": "safe-summary", "prompt_version": "1",
        "config_version": 1, "deadline": datetime(2030, 1, 1, tzinfo=UTC)}
    return LLMIntent(**{**values, **changes})


def test_frozen_intent():
    item = intent()
    with pytest.raises(ValidationError):
        item.tenant_id = "other"
    assert "count" not in repr(item)


@pytest.mark.parametrize("change", [{"task_type": "OTHER"}, {"model_class": "OTHER"},
    {"payload_json": "[]"}, {"output_schema_json": "broken"}, {"token_budget": 0},
    {"cost_budget_usd": float("nan")}, {"deadline": datetime(2030, 1, 1, tzinfo=UTC).replace(tzinfo=None)}])
def test_invalid_contract(change):
    with pytest.raises(ValidationError):
        intent(**change)
