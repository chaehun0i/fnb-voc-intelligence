from dataclasses import dataclass, field
from .enums import IncidentStatus, Severity

@dataclass(frozen=True)
class Evidence: id:str; source:str; type:str; summary:str; confidence:float
@dataclass(frozen=True)
class RootCauseCandidate: id:str; summary:str; confidence:float; supporting_evidence_ids:list[str]=field(default_factory=list); counter_evidence_ids:list[str]=field(default_factory=list)
@dataclass(frozen=True)
class CorrectiveAction: id:str; summary:str; risk_level:Severity; expected_effect:str; verification_criteria:str
@dataclass(frozen=True)
class Verification: result:str; summary:str
@dataclass(frozen=True)
class StateTransition: status:IncidentStatus; occurred_at:str
@dataclass
class Incident:
    id:str; display_id:str; title:str; severity:Severity; status:IncidentStatus; store:str; owner:str; created_at:str; sla_due_at:str
    evidence:list[Evidence]=field(default_factory=list); root_cause_candidates:list[RootCauseCandidate]=field(default_factory=list); corrective_actions:list[CorrectiveAction]=field(default_factory=list); verification:Verification|None=None; timeline:list[StateTransition]=field(default_factory=list); approved:bool=False
