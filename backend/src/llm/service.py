"""명시적 호출의 Principal·Tenant·Config snapshot과 영속 trace를 연결합니다."""
from src.application.incidents.service import IncidentNotFound
from src.application.security.authorization import require
from src.application.security.principal import AccessError
from src.domain.config.models import RuntimeConfig
from src.domain.config.resolution import ConfigResolver
from src.llm.errors import LLMError, LLMErrorCode


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
