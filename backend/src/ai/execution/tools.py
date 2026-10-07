"""Immutable business contracts; no SDK, transport, DB or authorization implementation."""
import json
from types import MappingProxyType
from typing import Literal

from pydantic import Field, model_validator

from src.ai.models import SafeModel

TOOL_BUNDLE_VERSION = "read-tools-1"


class ToolInput(SafeModel):
    incident_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    limit: int = Field(default=10, strict=True, ge=1, le=20)


class ToolItem(SafeModel):
    source_ref: str = Field(pattern=r"^(incident|review|transaction|inventory):[A-Za-z0-9_.:-]{1,128}$")
    source_type: Literal["INCIDENT", "HISTORY", "TRANSACTION", "INVENTORY"]
    observation_code: Literal["REFERENCE_ONLY", "RELATED_HISTORY_MATCH", "REFUND_SIGNAL", "CANCEL_SIGNAL", "STOCK_SHORTAGE", "STOCK_ADJUSTMENT"] = "REFERENCE_ONLY"
    stance: Literal["SUPPORTING", "CONTRADICTING", "NEUTRAL"] = "NEUTRAL"
    source_at: str | None = None
    provenance: tuple[str, ...] = Field(default=(), max_length=4)
    rank: int = Field(default=1, ge=1, le=20)


class ToolResult(SafeModel):
    tool_name: str
    tool_version: Literal["1"] = "1"
    items: tuple[ToolItem, ...] = Field(default=(), max_length=20)


class ToolContract(SafeModel):
    name: str = Field(pattern=r"^[a-z_]{1,64}$")
    version: Literal["1"] = "1"
    description: str = Field(min_length=1, max_length=300)
    agent_type: Literal["HISTORY", "TRANSACTION", "INVENTORY"]
    operation: Literal["HISTORY_LOOKUP", "TRANSACTION_LOOKUP", "INVENTORY_LOOKUP"]
    capability: Literal["HISTORY_DATA", "TRANSACTION_DATA", "INVENTORY_DATA"]
    policy_tool: Literal["voc.search", "transaction.search", "inventory.snapshot"]
    input_schema_json: str = json.dumps(ToolInput.model_json_schema(), sort_keys=True)
    output_schema_json: str = json.dumps(ToolResult.model_json_schema(), sort_keys=True)
    risk_level: Literal["LOW"] = "LOW"
    required_scope: Literal["CURRENT_INCIDENT_STORE"] = "CURRENT_INCIDENT_STORE"
    side_effect: Literal["NONE"] = "NONE"
    timeout_seconds: int = Field(default=10, strict=True, ge=1, le=30)
    retry_policy: Literal["BOUNDED_LOOP_ONLY"] = "BOUNDED_LOOP_ONLY"
    idempotency_mode: Literal["PINNED_READ_RESULT"] = "PINNED_READ_RESULT"
    approval_requirement: Literal["NOT_REQUIRED_READ_ONLY"] = "NOT_REQUIRED_READ_ONLY"
    evidence_semantics: Literal["SOURCE_REFERENCE_NOT_GENERATED_TEXT"] = "SOURCE_REFERENCE_NOT_GENERATED_TEXT"

    @model_validator(mode="after")
    def schemas(self):
        if (json.loads(self.input_schema_json) != ToolInput.model_json_schema()
                or json.loads(self.output_schema_json) != ToolResult.model_json_schema()):
            raise ValueError("TOOL_SCHEMA_MISMATCH")
        return self


class ToolRegistry:
    version = TOOL_BUNDLE_VERSION

    def __init__(self, contracts):
        entries = {}
        for value in contracts:
            item = ToolContract.model_validate(value.model_dump())
            if item.name in entries:
                raise ValueError("TOOL_DUPLICATE")
            entries[item.name] = item
        self._entries = MappingProxyType(entries)

    def resolve(self, name, version="1"):
        item = self._entries.get(name)
        if item is None or item.version != version:
            raise ValueError("TOOL_UNKNOWN_OR_VERSION_MISMATCH")
        return item

    def contracts(self):
        return tuple(self._entries[name] for name in sorted(self._entries))


READ_TOOLS = ToolRegistry((
    ToolContract(name="get_incident", description="현재 사건의 안전한 참조를 확인합니다.", agent_type="HISTORY", operation="HISTORY_LOOKUP", capability="HISTORY_DATA", policy_tool="voc.search"),
    ToolContract(name="search_similar_incidents", description="허용된 같은 매장의 유사 사건 참조를 확인합니다.", agent_type="HISTORY", operation="HISTORY_LOOKUP", capability="HISTORY_DATA", policy_tool="voc.search"),
    ToolContract(name="get_transactions", description="거래 관측을 확인합니다. 실제 POS 거래 원장이 아닙니다.", agent_type="TRANSACTION", operation="TRANSACTION_LOOKUP", capability="TRANSACTION_DATA", policy_tool="transaction.search"),
    ToolContract(name="get_inventory", description="재고 관측을 확인합니다. 실제 ERP 재고 원장이 아닙니다.", agent_type="INVENTORY", operation="INVENTORY_LOOKUP", capability="INVENTORY_DATA", policy_tool="inventory.snapshot"),
))
