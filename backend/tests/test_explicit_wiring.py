"""동적 public dispatch와 positional UoW wiring을 다시 도입하지 않습니다."""
import inspect

import pytest

from src.application.incidents.commands import COMMANDS, IncidentCommands
from src.infrastructure.access_unit_of_work import AccessUnitOfWork


def test_command_api_is_explicit_and_preserves_argument_forwarding():
    assert "__getattr__" not in IncidentCommands.__dict__
    commands = IncidentCommands(None, None, None)
    calls = []
    commands._command = lambda name, *args, **kwargs: calls.append((name, args, kwargs))
    for name in COMMANDS | {"list", "get", "workspace"}:
        assert name in IncidentCommands.__dict__
        getattr(commands, name)("id", expected_version=3)
        assert calls[-1] == (name, ("id",), {"expected_version": 3})
    with pytest.raises(AttributeError):
        _ = commands.arbitrary_status_patch


def test_uow_requires_named_stores():
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY
               for p in inspect.signature(AccessUnitOfWork).parameters.values())
    with pytest.raises(TypeError):
        AccessUnitOfWork(None, None, None, None)
    work = AccessUnitOfWork(incidents="incidents", approvals="approvals", audit="audit", idempotency="keys")
    assert work.incidents == "incidents" and work.idempotency == "keys"
