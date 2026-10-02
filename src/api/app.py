from fastapi import FastAPI

from src.api.routes.incidents import router
from src.application.incidents.service import IncidentService
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


def create_app() -> FastAPI:
    app = FastAPI(title="ServIQ API")
    app.state.service = IncidentService(InMemoryIncidentRepository())
    app.include_router(router)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
