import pytest

from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Incident
from src.domain.incidents.transitions import DomainRuleViolation, transition


def incident(): return Incident("1","INC-1","test",Severity.HIGH,IncidentStatus.DETECTED,"store","owner","2026-01-01","2026-01-02")
def test_transition(): assert transition(incident(),IncidentStatus.TRIAGED,"2026-01-01").status==IncidentStatus.TRIAGED
def test_skip_rejected():
 with pytest.raises(DomainRuleViolation): transition(incident(),IncidentStatus.EXECUTING,"2026-01-01")
