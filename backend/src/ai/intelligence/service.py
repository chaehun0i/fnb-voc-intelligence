"""ai/intelligence/service: 통합된 기능 책임, 기존 실행 계약 유지."""
import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from time import monotonic
from uuid import uuid4

import psycopg
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from src.ai.intelligence.models import (
    DataClassification,
    ExecutionBudget,
    LLMCallRecord,
    LLMError,
    LLMErrorCode,
    LLMResult,
    ProviderRequest,
)
from src.ai.intelligence.providers.gemini import GeminiProvider
from src.ai.intelligence.providers.ollama import OllamaProvider
from src.application.incidents.service import IncidentNotFound
from src.application.ports.llm_call_repository import LLMCallsUnavailable
from src.application.security.authorization import require
from src.application.security.principal import AccessError
from src.domain.config.models import LLMModelBinding, RuntimeConfig
from src.domain.config.resolution import ConfigResolver, ConfigValidationFailed

PII_FIELDS = frozenset({"customer_name", "phone", "email", "address", "external_customer_id"})
FORBIDDEN_FIELDS = frozenset({"api_key", "secret", "password", "credential", "raw_voc", "raw_document"})


class PolicyResult(StrEnum):
    ALLOW = "ALLOW"
    ALLOW_REDACTED = "ALLOW_REDACTED"
    DENY = "DENY"
    HUMAN_ONLY = "HUMAN_ONLY"


@dataclass(frozen=True)
class PolicyDecision:
    result: PolicyResult
    payload_json: str = field(repr=False)
    redacted: bool


def minimize(value):
    redacted = False
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            normalized = key.lower()
            if normalized in PII_FIELDS | FORBIDDEN_FIELDS:
                redacted = True
                continue
            cleaned, changed = minimize(item)
            output[key] = cleaned
            redacted |= changed
        return output, redacted
    if isinstance(value, list):
        pairs = [minimize(item) for item in value]
        return [item for item, _ in pairs], any(changed for _, changed in pairs)
    return value, False


def evaluate_policy(intent, capability, *, hosted_ai_allowed=False):
    if intent.classification == DataClassification.RESTRICTED:
        raise LLMError(LLMErrorCode.POLICY_DENIED)
    if capability.hosted and not hosted_ai_allowed:
        raise LLMError(LLMErrorCode.POLICY_DENIED)
    # 자유 텍스트의 PII 여부는 이 redactor가 보장하지 않습니다. Application 검토가 필요합니다.
    if intent.classification in {DataClassification.PII, DataClassification.CONFIDENTIAL} and not intent.free_text_reviewed:
        raise LLMError(LLMErrorCode.POLICY_DENIED)
    payload, redacted = minimize(json.loads(intent.payload_json))
    if not payload:
        raise LLMError(LLMErrorCode.POLICY_DENIED)
    return PolicyDecision(PolicyResult.ALLOW_REDACTED if redacted else PolicyResult.ALLOW,
        json.dumps(payload, sort_keys=True, ensure_ascii=False), redacted)


def schema_validator(schema_json):
    try:
        schema = json.loads(schema_json)
        Draft202012Validator.check_schema(schema)
        # 외부 URL ref는 검증 중 네트워크/임의 자료 접근을 유발할 수 있습니다.
        def local_refs(value):
            if isinstance(value, dict):
                for key in ("$ref", "$dynamicRef", "$recursiveRef"):
                    if key in value and not value[key].startswith("#"):
                        raise LLMError(LLMErrorCode.INVALID_REQUEST)
                for nested in value.values():
                    local_refs(nested)
            elif isinstance(value, list):
                for nested in value:
                    local_refs(nested)
        local_refs(schema)
        return Draft202012Validator(schema)
    except (ValueError, SchemaError):
        raise LLMError(LLMErrorCode.INVALID_REQUEST) from None


def validate_output(content, validator, domain_validator=None):
    def reject_non_json_number(_):
        raise ValueError("JSON에서 NaN/Infinity는 지원하지 않습니다.")
    try:
        value = json.loads(content, parse_constant=reject_non_json_number)
        validator.validate(value)
    except (ValueError, ValidationError):
        raise LLMError(LLMErrorCode.OUTPUT_SCHEMA_INVALID) from None
    if domain_validator is not None:
        try:
            domain_validator(value)
        except (ValueError, KeyError):
            raise LLMError(LLMErrorCode.OUTPUT_DOMAIN_INVALID) from None
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


@dataclass(frozen=True)
class ProviderSelection:
    provider: object
    binding: object
    timeout_seconds: float


class ProviderRouter:
    def __init__(self, providers):
        self.providers = dict(providers)

    def select(self, intent, resolved, *, fallback=False):
        config = resolved.effective
        if fallback and not (intent.fallback_allowed and config.llm_fallback_allowed):
            raise LLMError(LLMErrorCode.POLICY_DENIED)
        name = config.fallback_llm_provider if fallback else config.default_llm_provider
        if name not in config.llm_enabled_providers or name not in self.providers:
            raise LLMError(LLMErrorCode.PROVIDER_NOT_CONFIGURED)
        provider = self.providers[name]
        capability = provider.capability
        if capability.provider != name or not capability.structured_output or intent.model_class not in capability.model_classes:
            raise LLMError(LLMErrorCode.CAPABILITY_UNSUPPORTED)
        binding = next((item for item in config.llm_models if item.provider == name and item.model_class == intent.model_class), None)
        if binding is None:
            raise LLMError(LLMErrorCode.PROVIDER_NOT_CONFIGURED)
        evaluate_policy(intent, capability, hosted_ai_allowed=config.hosted_ai_allowed)
        # 안전한 상한 추정: UTF-8 바이트 수는 입력 토큰보다 보수적인 예약량입니다.
        input_bound = len(intent.payload_json.encode("utf-8")) + len(intent.output_schema_json.encode("utf-8")) + 256
        output_bound = intent.max_output_tokens
        cost = (input_bound * binding.input_usd_per_million + output_bound * binding.output_usd_per_million) / 1_000_000
        if (input_bound + output_bound > min(intent.token_budget, config.token_budget, capability.context_limit)
                or cost > min(intent.cost_budget_usd, config.cost_budget_usd)):
            raise LLMError(LLMErrorCode.BUDGET_EXHAUSTED)
        timeout = config.provider_timeout_seconds
        if name == "gemini":
            timeout = min(timeout, config.gemini_timeout_seconds)
        return ProviderSelection(provider, binding, timeout)


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


class RoutedLLMExecutor:
    def __init__(self, router, *, clock=lambda: datetime.now(UTC), recorder=None):
        self.router, self.clock = router, clock
        self.recorder = recorder

    async def execute(self, intent, resolved, *, domain_validator=None):
        config = resolved.effective
        selection = self.router.select(intent, resolved)
        budget = ExecutionBudget(min(config.token_budget, intent.token_budget), min(config.cost_budget_usd, intent.cost_budget_usd))
        try:
            return await self.run(selection, intent, config, domain_validator, budget)
        except LLMError as error:
            if not error.retryable or not (intent.fallback_allowed and config.llm_fallback_allowed):
                raise
            if (intent.deadline - self.clock()).total_seconds() <= 0:
                raise LLMError(LLMErrorCode.DEADLINE_EXHAUSTED) from None
            alternative = self.router.select(intent, resolved, fallback=True)
            if alternative.provider.capability.provider == selection.provider.capability.provider:
                raise
            result = await self.run(alternative, intent, config, domain_validator, budget, fallback=True)
            return result.model_copy(update={"fallback_used": True})

    async def run(self, selection, intent, config, domain_validator, budget, fallback=False):
        return await LLMGateway(selection.provider, clock=self.clock, recorder=self.recorder).execute(intent,
            model=selection.binding.model, timeout_seconds=selection.timeout_seconds,
            repair_limit=min(1, config.structured_output_retry), domain_validator=domain_validator,
            hosted_ai_allowed=config.hosted_ai_allowed, budget=budget,
            input_rate=selection.binding.input_usd_per_million, output_rate=selection.binding.output_usd_per_million,
            retry_limit=1, fallback=fallback)


class LLMApplication:
    def __init__(self, persistence, executor_factory, resolver=None, *, default_config=None):
        self.persistence, self.executor_factory = persistence, executor_factory
        self.resolver = resolver or ConfigResolver()
        self.default_config = default_config or RuntimeConfig()

    async def execute(self, principal, intent, *, domain_validator=None):
        require(principal, "admin")
        if intent.tenant_id != principal.tenant_id:
            raise AccessError()
        with self.persistence.transaction(principal.tenant_id) as uow:
            if intent.incident_id:
                incident = uow.incidents.get(intent.incident_id)
                if incident is None:
                    raise IncidentNotFound(intent.incident_id)
                require(principal, "operate", incident.store)
            version = uow.configs.get(intent.config_version) if intent.config_version else None
            if intent.config_version and version is None:
                raise LLMError(LLMErrorCode.INVALID_REQUEST)
            if not intent.config_version and uow.configs.current() is not None:
                # 로컬 bootstrap으로 저장된 Tenant 정책을 우회하지 않습니다.
                raise LLMError(LLMErrorCode.INVALID_REQUEST)
            resolved = self.resolver.resolve(version.config if version else self.default_config)
        # 외부 네트워크 동안 DB transaction/lock을 유지하지 않습니다.
        def record(call):
            with self.persistence.transaction(principal.tenant_id) as uow:
                uow.llm_calls.append(call)
        return await self.executor_factory(record).execute(intent, resolved, domain_validator=domain_validator)


def local_llm_config(environ=None):
    """명시적으로 켠 로컬 환경만 Gemini를 허용합니다. 키는 설정에 넣지 않습니다."""
    values = os.environ if environ is None else environ
    if values.get("SERVIQ_LLM_ENABLED", "false").lower() != "true":
        return RuntimeConfig()
    if values.get("APP_ENV", "local") not in {"local", "development"}:
        raise LLMError(LLMErrorCode.POLICY_DENIED)
    model = values.get("MODEL", "").strip()
    if not model:
        raise LLMError(LLMErrorCode.PROVIDER_NOT_CONFIGURED)
    try:
        # 공식 청구 단가가 아니라 로컬 테스트의 보수적인 예산 예약 단가입니다.
        input_rate = float(values.get("LLM_INPUT_USD_PER_MILLION", "10"))
        output_rate = float(values.get("LLM_OUTPUT_USD_PER_MILLION", "100"))
        config = RuntimeConfig(hosted_ai_allowed=True, llm_enabled_providers=("gemini",),
            llm_models=tuple(LLMModelBinding("gemini", model_class, model, input_rate, output_rate)
                for model_class in ("FAST", "STANDARD", "REASONING")), llm_fallback_allowed=False)
        return ConfigResolver().resolve(config).effective
    except (ValueError, TypeError, ConfigValidationFailed):
        raise LLMError(LLMErrorCode.INVALID_REQUEST) from None


def configured_llm_executor(recorder=None):
    router = ProviderRouter({"gemini": GeminiProvider(), "ollama": OllamaProvider()})
    return RoutedLLMExecutor(router, recorder=recorder)


def configured_llm_application(persistence):
    return LLMApplication(persistence, configured_llm_executor, default_config=local_llm_config())


class LLMCallQueries:
    def __init__(self, persistence, principal):
        self.persistence, self.principal = persistence, principal

    def history(self, incident_id, limit=20):
        require(self.principal, "read")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("조회 개수는 1~100이어야 합니다.")
        try:
            with self.persistence.transaction(self.principal.tenant_id) as uow:
                incident = uow.incidents.get(incident_id)
                if incident is None:
                    raise IncidentNotFound(incident_id)
                require(self.principal, "read", incident.store)
                return uow.llm_calls.history(incident_id, limit)
        except (psycopg.Error, KeyError, ValueError, TypeError) as error:
            raise LLMCallsUnavailable() from error
