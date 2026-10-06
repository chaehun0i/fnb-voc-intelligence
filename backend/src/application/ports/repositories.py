"""application/ports/repositories: 통합된 기능 책임, 기존 실행 계약 유지."""
from typing import Protocol

from src.ai.decision.models import DecisionRecord
from src.ai.intelligence.models import LLMCallRecord
from src.ai.workflow.models import AgentRun, AgentStep
from src.domain.approvals.audit import AuditRecord
from src.domain.approvals.models import Approval
from src.domain.config.models import ConfigVersion
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Incident
from src.domain.jobs.models import Job


class IncidentConflict(ValueError):
    """다른 명령이 먼저 저장해 최신 버전을 다시 읽어야 합니다."""


class IncidentRepository(Protocol):
    def list(
        self,
        status: IncidentStatus | None = None,
        severity: Severity | None = None,
        store: str | None = None,
        *, tenant_id: str | None = None,
    ) -> list[Incident]: ...

    def get(self, incident_id: str, *, tenant_id: str | None = None) -> Incident | None: ...

    def save(self, incident: Incident) -> Incident:
        """버전을 확인하고 저장한 새 버전의 복사본을 반환합니다."""
        ...


class ApprovalRepository(Protocol):
    def get(self, approval_id: str) -> Approval | None: ...
    def list(self, incident_id: str | None = None) -> list[Approval]: ...
    def save(self, approval: Approval) -> Approval: ...


class AuditRepository(Protocol):
    def append(self, record: AuditRecord) -> None: ...
    def list(self) -> list[AuditRecord]: ...


class IdempotencyRepository(Protocol):
    def claim(self, principal_id: str, operation: str, key: str, fingerprint: str) -> Incident | None: ...
    def complete(self, principal_id: str, operation: str, key: str, result: Incident) -> None: ...


class JobConflict(Exception):
    """다른 실행이나 운영 명령이 먼저 작업을 변경했습니다."""


class JobRepository(Protocol):
    def get(self, job_id: str) -> Job | None: ...
    def list(self, *, status=None, priority=None, job_type=None, incident_id=None,
             correlation_id=None, limit=100, offset=0) -> list[Job]: ...
    def save(self, job: Job) -> Job: ...


class ConfigVersionConflict(Exception):
    pass


class ConfigNotFound(Exception):
    pass


class SettingsUnavailable(Exception):
    pass


class ConfigRepository(Protocol):
    def current(self) -> ConfigVersion | None: ...
    def get(self, version: int) -> ConfigVersion | None: ...
    def history(self, limit: int, offset: int) -> list[ConfigVersion]: ...
    def append(self, version: ConfigVersion, expected_version: int) -> ConfigVersion: ...


class DecisionRepository(Protocol):
    def get(self, decision_id: str) -> DecisionRecord | None: ...
    def by_job(self, job_id: str, ruleset: str = "1") -> DecisionRecord | None: ...
    def history(self, incident_id: str, limit: int, offset: int) -> list[DecisionRecord]: ...
    def append(self, record: DecisionRecord) -> DecisionRecord: ...


class DecisionsUnavailable(Exception):
    """저장소 오류 원문은 HTTP 응답에 전달하지 않습니다."""


class LLMCallRepository(Protocol):
    def append(self, record: LLMCallRecord) -> None: ...
    def history(self, incident_id: str, limit: int = 20) -> list[LLMCallRecord]: ...


class LLMCallsUnavailable(Exception):
    """저장소 원문을 HTTP 응답에 노출하지 않습니다."""


class AgentRunsUnavailable(Exception):
    """실행 이력 저장소를 사용할 수 없습니다."""


class AgentRunRepository(Protocol):
    def get(self, run_id: str) -> AgentRun | None: ...
    def by_job(self, job_id: str) -> AgentRun | None: ...
    def history(self, incident_id: str, limit=20, offset=0) -> list[AgentRun]: ...
    def save(self, run: AgentRun) -> AgentRun: ...
    def append_step(self, step: AgentStep) -> None: ...
    def steps(self, run_id: str) -> list[AgentStep]: ...
    def branch(self, run_id, agent_type): ...
    def append_branch(self, run_id, result): ...
    def lock(self, run_id): ...
    def events(self, run_id): ...
    def append_event(self, run_id, event): ...


class InvestigationSource(Protocol):
    def capabilities(self, tenant_id, store, now): ...
    def observations(self, context): ...
