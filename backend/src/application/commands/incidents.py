"""보호된 HTTP 명령을 기존 서비스와 같은 트랜잭션 안에서 실행합니다."""

from src.application.approvals.service import ApprovalService
from src.application.incidents.service import IncidentService

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
            with self.persistence.transaction(self.context.principal.tenant_id) as uow:
                service = self._service(uow.incidents)
                approval = ApprovalService(service, uow.approvals, self.context)
                if operation == "request_approval":
                    return approval.request(*args, **kwargs)
                if operation in {"approve", "reject"}:
                    return approval.decide_incident(args[0], operation, *args[1:], **kwargs)
                if operation == "execute":
                    approval.require_effective(service._load(args[0], None))
                return getattr(service, operation)(*args, **kwargs)
        return invoke
