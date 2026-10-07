"""Immutable business contracts; no SDK, transport, DB or authorization implementation."""
import json
from types import MappingProxyType
from typing import Literal

from pydantic import Field, model_validator

from src.ai.models import SafeModel

TOOL_BUNDLE_VERSION = "read-tools-1"

ToolErrorCategory = Literal["TOOL_TEMPORARY", "TOOL_PERMANENT", "CONTRACT_ERROR",
    "AUTHORIZATION_DENIED", "APPROVAL_REQUIRED", "DATA_NOT_AVAILABLE", "UNKNOWN_EXTERNAL_RESULT"]


class ToolError(SafeModel):
    code: Literal["SOURCE_TIMEOUT", "SOURCE_UNAVAILABLE", "INVALID_CONTRACT", "ACCESS_DENIED",
        "APPROVAL_REQUIRED", "NO_DATA", "OUTCOME_UNKNOWN", "POLICY_DENIED", "BUDGET_EXHAUSTED"]
    category: ToolErrorCategory
    retryable: bool
    safe_message: str = Field(max_length=200)
    suggested_action: Literal["BOUNDED_RETRY", "FIX_INPUT", "REQUEST_ACCESS", "HUMAN_REVIEW", "ADD_EVIDENCE", "STOP"]
    human_action: Literal["NONE", "MORE_EVIDENCE_REQUIRED", "POLICY_BLOCKED", "MANUAL_REVIEW_REQUIRED"]
    details_ref: str | None = Field(default=None, pattern=r"^tool:[a-f0-9]{64}$")


ERRORS = MappingProxyType({
    "SOURCE_TIMEOUT": ("TOOL_TEMPORARY", True, "자료 확인 응답이 지연되고 있습니다.", "BOUNDED_RETRY", "NONE"),
    "SOURCE_UNAVAILABLE": ("TOOL_TEMPORARY", True, "자료 저장소를 일시적으로 사용할 수 없습니다.", "BOUNDED_RETRY", "NONE"),
    "INVALID_CONTRACT": ("CONTRACT_ERROR", False, "입력 또는 결과 계약을 확인해 주세요.", "FIX_INPUT", "MANUAL_REVIEW_REQUIRED"),
    "ACCESS_DENIED": ("AUTHORIZATION_DENIED", False, "현재 권한으로 자료를 확인할 수 없습니다.", "REQUEST_ACCESS", "POLICY_BLOCKED"),
    "APPROVAL_REQUIRED": ("APPROVAL_REQUIRED", False, "사람의 승인이 필요합니다.", "HUMAN_REVIEW", "MANUAL_REVIEW_REQUIRED"),
    "NO_DATA": ("DATA_NOT_AVAILABLE", False, "필요한 자료가 없습니다.", "ADD_EVIDENCE", "MORE_EVIDENCE_REQUIRED"),
    "OUTCOME_UNKNOWN": ("UNKNOWN_EXTERNAL_RESULT", False, "이전 요청의 결과를 확인할 수 없어 재호출하지 않습니다.", "HUMAN_REVIEW", "MANUAL_REVIEW_REQUIRED"),
    "POLICY_DENIED": ("TOOL_PERMANENT", False, "현재 정책에서 자료 확인을 허용하지 않습니다.", "STOP", "POLICY_BLOCKED"),
    "BUDGET_EXHAUSTED": ("TOOL_PERMANENT", False, "설정된 자료 확인 한도에 도달했습니다.", "STOP", "MANUAL_REVIEW_REQUIRED"),
})


def tool_error(code, details_ref=None):
    category, retryable, message, action, human = ERRORS[code]
    return ToolError(code=code, category=category, retryable=retryable, safe_message=message,
        suggested_action=action, human_action=human, details_ref=details_ref)


class ToolFailure(Exception):
    def __init__(self, error):
        self.error = error
        super().__init__(error.code)


class ToolInput(SafeModel):
    incident_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
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


class ToolCall(SafeModel):
    """Reference-only effect receipt. A missing result is uncertain, never replayed."""
    call_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    tool_name: str = Field(pattern=r"^[a-z_]{1,64}$")
    tool_version: Literal["1"] = "1"
    context_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    reservation: str = Field(default="direct", max_length=64)
    result: ToolResult | None = None
    error: ToolError | None = None

    @model_validator(mode="after")
    def receipt(self):
        if self.result and (self.error or self.result.tool_name != self.tool_name):
            raise ValueError("TOOL_RECEIPT_INVALID")
        return self


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
    when_to_use: str = Field(default="현재 사건의 조사 목적에 맞는 허용된 자료 참조를 확인할 때", min_length=1, max_length=200)
    when_not_to_use: str = Field(default="원문 전체 조회, 다른 매장 조회, 원인 확정 또는 외부 변경에는 사용하지 않음", min_length=1, max_length=200)
    preconditions: tuple[Literal["ACTIVE_RUN", "CURRENT_AUTHORIZATION", "FRESH_CAPABILITY", "BOUNDED_BUDGET"], ...] = ("ACTIVE_RUN", "CURRENT_AUTHORIZATION", "FRESH_CAPABILITY", "BOUNDED_BUDGET")
    common_errors: tuple[str, ...] = tuple(ERRORS)
    retry_guidance: Literal["TEMPORARY_ONLY_WITH_LOOP_BUDGET_NO_RETRY_ON_AUTH_OR_NO_DATA"] = "TEMPORARY_ONLY_WITH_LOOP_BUDGET_NO_RETRY_ON_AUTH_OR_NO_DATA"

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
