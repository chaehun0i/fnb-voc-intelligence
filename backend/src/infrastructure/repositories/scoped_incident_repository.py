"""HTTP 업무 경로에서 조직 범위를 생략할 수 없는 저장소입니다."""

from src.application.security.principal import AccessError


class ScopedIncidentRepository:
    def __init__(self, repository, tenant_id: str):
        self.repository = repository
        self.tenant_id = tenant_id

    def list(self, status=None, severity=None, store=None):
        return self.repository.list(status, severity, store, tenant_id=self.tenant_id)

    def get(self, incident_id):
        return self.repository.get(incident_id, tenant_id=self.tenant_id)

    def save(self, incident):
        if incident.tenant_id != self.tenant_id:
            raise AccessError()
        return self.repository.save(incident)
