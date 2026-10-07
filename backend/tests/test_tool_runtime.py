import json

import pytest
from pydantic import ValidationError

from src.ai.execution.tools import READ_TOOLS, ToolContract, ToolInput, ToolRegistry


def test_registry_is_versioned_immutable_and_unique():
    assert READ_TOOLS.version == "read-tools-1"
    assert len(READ_TOOLS.contracts()) == 4
    contract = READ_TOOLS.resolve("get_inventory")
    with pytest.raises(ValidationError):
        contract.risk_level = "HIGH"
    with pytest.raises(ValueError, match="TOOL_DUPLICATE"):
        ToolRegistry((contract, contract))


@pytest.mark.parametrize("name,version", [("shell", "1"), ("get_inventory", "2")])
def test_unknown_tool_or_version_fails_closed(name, version):
    with pytest.raises(ValueError, match="TOOL_UNKNOWN"):
        READ_TOOLS.resolve(name, version)


def test_tool_schema_is_canonical_and_rejects_scope_or_unbounded_input():
    contract = READ_TOOLS.resolve("get_incident")
    assert json.loads(contract.input_schema_json) == ToolInput.model_json_schema()
    with pytest.raises(ValidationError):
        ToolContract.model_validate({**contract.model_dump(), "input_schema_json": "{}"})
    for extra in ({"tenant_id": "other"}, {"actor_id": "admin"}, {"limit": 21}):
        with pytest.raises(ValidationError):
            ToolInput(incident_id="a"*36, **extra)


def test_errors_and_ax_are_machine_readable_without_raw_exception():
    from src.ai.execution.tools import ERRORS, ToolFailure, tool_error
    for code in ERRORS:
        error = tool_error(code)
        assert str(ToolFailure(error)) == code
        assert error.safe_message and error.suggested_action
        assert error.retryable == (error.category == "TOOL_TEMPORARY")
        assert "password" not in error.model_dump_json()
    for contract in READ_TOOLS.contracts():
        assert contract.when_to_use and contract.when_not_to_use and contract.preconditions
        assert "NO_DATA" in contract.common_errors
        assert "NO_RETRY_ON_AUTH" in contract.retry_guidance
