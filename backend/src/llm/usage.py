"""원문 없는 호출 기록과 실행 전체의 보수적인 예산 예약입니다."""
from dataclasses import dataclass
from datetime import datetime

from src.llm.contracts import LLMUsage
from src.llm.errors import LLMError, LLMErrorCode


@dataclass(frozen=True)
class LLMCallRecord:
    call_id: str
    tenant_id: str
    request_id: str
    correlation_id: str
    incident_id: str | None
    config_version: int
    provider: str
    model: str
    task_type: str
    prompt_template: str
    prompt_version: str
    schema_version: str
    classification: str
    redacted: bool
    input_digest: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    latency_ms: int
    structured_retry: bool
    provider_retry: bool
    fallback: bool
    error_code: str | None
    created_at: datetime


class ExecutionBudget:
    def __init__(self, tokens, cost):
        self.token_limit, self.cost_limit = tokens, cost
        self.charged_tokens = self.input_tokens = self.output_tokens = 0
        self.charged_cost = 0
        self.structured_retries = self.provider_retries = 0

    def reserve(self, request, input_rate, output_rate):
        input_bound = len(request.prompt.encode("utf-8")) + len(request.output_schema_json.encode("utf-8")) + 256
        tokens = input_bound + request.max_output_tokens
        cost = (input_bound * input_rate + request.max_output_tokens * output_rate) / 1_000_000
        if self.charged_tokens + tokens > self.token_limit or self.charged_cost + cost > self.cost_limit:
            raise LLMError(LLMErrorCode.BUDGET_EXHAUSTED)
        return tokens, cost

    def consume(self, usage, reservation, input_rate, output_rate):
        if usage is None:
            self.charged_tokens += reservation[0]
            self.charged_cost += reservation[1]
            return reservation[1]
        cost = (usage.input_tokens * input_rate + usage.output_tokens * output_rate) / 1_000_000
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.charged_tokens += usage.total_tokens
        self.charged_cost += cost
        return cost

    @property
    def usage(self):
        return LLMUsage(input_tokens=self.input_tokens, output_tokens=self.output_tokens)
