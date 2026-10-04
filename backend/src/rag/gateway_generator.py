"""기존 동기 RAG 계약을 공통 Gateway로 연결하며 SDK를 직접 사용하지 않습니다."""
import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.domain.config.resolution import ConfigResolver
from src.llm.contracts import LLMIntent
from src.llm.errors import LLMError, LLMErrorCode


class GatewayTextGenerator:
    def __init__(self, config, executor, *, reviewed=False):
        self.resolved = ConfigResolver().resolve(config, source="LOCAL_BOOTSTRAP")
        self.executor, self.reviewed = executor, reviewed
        binding = next((item for item in config.llm_models
            if item.provider == config.default_llm_provider and item.model_class == "STANDARD"), None)
        if binding is None:
            raise LLMError(LLMErrorCode.PROVIDER_NOT_CONFIGURED)
        self.model = binding.model

    def generate(self, prompt):
        # 원문 VOC는 canonical 필드 제거만으로 PII 안전성을 보장할 수 없습니다.
        if not self.reviewed:
            raise LLMError(LLMErrorCode.POLICY_DENIED)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError("동기 RAG 생성기는 비동기 요청 안에서 직접 실행할 수 없습니다.")
        identity = uuid4().hex
        intent = LLMIntent(request_id=identity, correlation_id=identity, tenant_id="local-rag",
            task_type="SUMMARY", payload_json=json.dumps({"instruction": "근거와 인용 표기를 유지하고 answer에 답변하세요.",
                "reviewed_context": prompt}, ensure_ascii=False),
            output_schema_json='{"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":false}',
            schema_version="1", prompt_template="reviewed-rag", prompt_version="1", config_version=0,
            deadline=datetime.now(UTC)+timedelta(seconds=self.resolved.effective.timeout_seconds),
            classification="CONFIDENTIAL", free_text_reviewed=True,
            token_budget=self.resolved.effective.token_budget, cost_budget_usd=self.resolved.effective.cost_budget_usd)
        result = asyncio.run(self.executor.execute(intent, self.resolved))
        return json.loads(result.structured_json)["answer"]
