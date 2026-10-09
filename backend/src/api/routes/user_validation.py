"""Explicit consent, bounded task events; never arbitrary Agent execution."""
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Request
from pydantic import Field

from src.ai.ax.models import SafeModel
from src.ai.ax.validation import Scenario
from src.api.dependencies.auth import request_context
from src.application.ports.repositories import AgentRunsUnavailable
from src.application.user_validation import UserValidation, ValidationSignal

router = APIRouter(prefix="/api/v1/validation", tags=["user-validation"])


def service(request):
    return UserValidation(request.app.state.access_persistence, request_context(request), request.app.state.service.clock)


class StartInput(SafeModel):
    store: str = Field(min_length=1, max_length=100)
    scenario_id: Scenario
    consent: bool = Field(strict=True)


@router.get("/summary")
def summary(request: Request, store: str, kind: Literal["USER_OBSERVATION", "SYNTHETIC"] = "USER_OBSERVATION"):
    try:
        return service(request).summary(store, kind)
    except psycopg.Error as error:
        raise AgentRunsUnavailable() from error


@router.post("/sessions", status_code=201)
def start(body: StartInput, request: Request):
    try:
        return service(request).start(body.store, body.scenario_id, consent=body.consent)
    except psycopg.Error as error:
        raise AgentRunsUnavailable() from error


@router.get("/sessions/{session_id}")
def get(session_id: UUID, request: Request):
    try:
        return service(request).get(session_id)
    except psycopg.Error as error:
        raise AgentRunsUnavailable() from error


@router.post("/sessions/{session_id}/events", status_code=201)
def signal(session_id: UUID, body: ValidationSignal, request: Request):
    try:
        return service(request).signal(session_id, body)
    except psycopg.Error as error:
        raise AgentRunsUnavailable() from error


@router.post("/sessions/{session_id}/complete")
def finish(session_id: UUID, request: Request):
    try:
        return service(request).finish(session_id)
    except psycopg.Error as error:
        raise AgentRunsUnavailable() from error
