"""정책·예산·deadline·repair·안전한 사용 기록을 모든 호출에 적용합니다."""
import asyncio
import hashlib
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from src.llm.contracts import LLMResult, ProviderRequest
from src.llm.data_policy import evaluate_policy
from src.llm.errors import LLMError, LLMErrorCode
from src.llm.structured import schema_validator, validate_output
from src.llm.usage import ExecutionBudget, LLMCallRecord


class LLMGateway:
    def __init__(self, provider, *, clock=lambda: datetime.now(UTC), recorder=None, sleep=asyncio.sleep):
        self.provider, self.clock, self.recorder, self.sleep = provider, clock, recorder, sleep

    async def execute(self, intent, *, model, timeout_seconds=60, repair_limit=0, domain_validator=None,
        hosted_ai_allowed=False, budget=None, input_rate=0, output_rate=0, retry_limit=0, fallback=False):
        policy = evaluate_policy(intent, self.provider.capability, hosted_ai_allowed=hosted_ai_allowed)
        validator = schema_validator(intent.output_schema_json)
        budget = budget or ExecutionBudget(intent.token_budget, intent.cost_budget_usd)
        request = ProviderRequest(request_id=intent.request_id, tenant_id=intent.tenant_id,
            model=model, prompt=policy.payload_json, output_schema_json=intent.output_schema_json,
            timeout_seconds=min(timeout_seconds, self.remaining(intent)), max_output_tokens=intent.max_output_tokens)
        while True:
            response = await self.invoke(request, intent, budget, policy, input_rate, output_rate, retry_limit, fallback, domain_validator)
            if response.finish_reason == "BLOCKED":
                raise LLMError(LLMErrorCode.POLICY_DENIED)
            try:
                if response.finish_reason == "LIMIT":
                    raise LLMError(LLMErrorCode.OUTPUT_SCHEMA_INVALID)
                structured = validate_output(response.content, validator)
                break
            except LLMError as error:
                if error.code != LLMErrorCode.OUTPUT_SCHEMA_INVALID or repair_limit <= 0 or budget.structured_retries >= 1:
                    raise
                budget.structured_retries += 1
                # 잘못된 응답 원문은 복제하지 않고 최소 입력만 재사용합니다.
                request = request.model_copy(update={"repair": True,
                    "prompt": policy.payload_json + "\n위 최소 입력만 사용해 제공된 JSON Schema를 만족하는 JSON 객체만 다시 작성하세요. 다른 설명이나 새로운 근거를 추가하지 마세요.",
                    "timeout_seconds": min(timeout_seconds, self.remaining(intent))})
        return LLMResult(request_id=intent.request_id, provider=self.provider.capability.provider,
            model=model, config_version=intent.config_version, structured_json=structured, usage=budget.usage,
            structured_retry_count=budget.structured_retries, provider_retry_count=budget.provider_retries,
            fallback_used=fallback, estimated_cost_usd=budget.charged_cost)

    def remaining(self, intent):
        remaining = (intent.deadline - self.clock()).total_seconds()
        if remaining <= 0:
            raise LLMError(LLMErrorCode.DEADLINE_EXHAUSTED)
        return remaining

    async def invoke(self, request, intent, budget, policy, input_rate, output_rate, retry_limit, fallback, domain_validator):
        retry = False
        while True:
            request = request.model_copy(update={"timeout_seconds": min(request.timeout_seconds, self.remaining(intent))})
            reservation = budget.reserve(request, input_rate, output_rate)
            started, created_at = monotonic(), self.clock()
            response, failure = None, None
            try:
                response = await asyncio.wait_for(self.provider.generate(request), timeout=request.timeout_seconds)
            except LLMError as error:
                failure = error
            except TimeoutError:
                failure = LLMError(LLMErrorCode.TIMEOUT)
            except Exception:  # noqa: BLE001 — SDK 예외 원문 없이 실패 코드로 관측합니다.
                failure = LLMError(LLMErrorCode.PROVIDER_UNAVAILABLE)
            cost = budget.consume(response.usage if response else None, reservation, input_rate, output_rate)
            output_failure = None
            if response:
                try:
                    if response.finish_reason == "BLOCKED":
                        raise LLMError(LLMErrorCode.POLICY_DENIED)
                    if response.finish_reason == "LIMIT":
                        raise LLMError(LLMErrorCode.OUTPUT_SCHEMA_INVALID)
                    validate_output(response.content, schema_validator(request.output_schema_json), domain_validator)
                except LLMError as error:
                    output_failure = error
            record = LLMCallRecord(str(uuid4()), intent.tenant_id, intent.request_id, intent.correlation_id,
                intent.incident_id, intent.config_version, self.provider.capability.provider, request.model,
                intent.task_type.value, intent.prompt_template, intent.prompt_version, intent.schema_version,
                intent.classification.value, policy.redacted, hashlib.sha256(policy.payload_json.encode()).hexdigest(),
                response.usage.input_tokens if response else 0, response.usage.output_tokens if response else 0,
                cost, int((monotonic()-started)*1000), request.repair, retry, fallback,
                (failure or output_failure).code.value if (failure or output_failure) else None, created_at)
            if self.recorder:
                try:
                    self.recorder(record)
                except Exception:  # noqa: BLE001 — 기록 실패는 성공 처리하거나 외부 호출을 재실행하지 않습니다.
                    raise LLMError(LLMErrorCode.TRACE_UNAVAILABLE) from None
            if failure is None:
                if output_failure and output_failure.code == LLMErrorCode.OUTPUT_DOMAIN_INVALID:
                    raise output_failure
                if budget.charged_tokens > budget.token_limit or budget.charged_cost > budget.cost_limit:
                    raise LLMError(LLMErrorCode.BUDGET_EXHAUSTED)
                return response
            if not failure.retryable or retry_limit <= 0 or budget.provider_retries >= 1:
                raise failure
            budget.provider_retries += 1
            retry = True
            await self.sleep(min(0.1, self.remaining(intent)))
