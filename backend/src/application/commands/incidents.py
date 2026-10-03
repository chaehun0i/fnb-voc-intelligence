"""보호된 HTTP 명령을 기존 서비스와 같은 트랜잭션 안에서 실행합니다."""

from uuid import uuid4

from src.application.approvals.service import ApprovalService
from src.application.incidents.service import IncidentService
from src.application.security.principal import AccessError
from src.domain.approvals.audit import AuditRecord

COMMANDS = frozenset({"create", "triage", "investigate", "add_evidence", "prepare_rca",
                      "propose_action", "request_approval", "approve", "reject",
                      "execute", "verify", "close", "reopen"})


class IncidentCommands:
    def __init__(self, original, persistence, context):
        self.original, self.persistence, self.context = original, persistence, context

    def _service(self, repository):
        return IncidentService(repository, self.original.clock,
                               self.original.id_generator, self.context.principal)

    def __getattr__(self, operation):
        if operation not in COMMANDS | {"list", "get", "workspace"}:
            raise AttributeError(operation)

        def invoke(*args, **kwargs):
            try:
                return self._invoke(operation, args, kwargs)
            except AccessError:
                if operation in COMMANDS:
                    with self.persistence.transaction(self.context.principal.tenant_id) as uow:
                        self._audit(uow, operation, str(args[0]) if args else "", "DENIED")
                raise
        return invoke

    def _audit(self, uow, operation, resource_id, result, version=None):
        principal = self.context.principal
        uow.audit.append(AuditRecord(
            str(uuid4()), principal.tenant_id, principal.principal_id, operation,
            "incident", resource_id, result, self.context.request_id,
            self.context.correlation_id, self._service(uow.incidents)._now(), version,
        ))

    def _invoke(self, operation, args, kwargs):
            with self.persistence.transaction(self.context.principal.tenant_id) as uow:
                service = self._service(uow.incidents)
                approval = ApprovalService(service, uow.approvals, self.context)
                if operation == "request_approval":
                    result = approval.request(*args, **kwargs)
                elif operation in {"approve", "reject"}:
                    result = approval.decide_incident(args[0], operation, *args[1:], **kwargs)
                else:
                    if operation == "execute":
                        approval.require_effective(service._load(args[0], None))
                    result = getattr(service, operation)(*args, **kwargs)
                if operation in COMMANDS:
                    self._audit(uow, operation, result.id, "SUCCESS", result.version)
                return result
