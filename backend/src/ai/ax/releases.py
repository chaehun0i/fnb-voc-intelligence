"""Offline RC evidence contract, not a production release or activation lifecycle."""
from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import Field, model_validator

from src.ai.models import SafeModel
from src.ai.workflow.models import AgentRunManifest
from src.domain.config.models import config_document

GOLDEN_VERSION = "serviq-closed-loop-ax-1"
BLOCKERS = ("CROSS_TENANT_LEAKAGE", "APPROVAL_BYPASS", "DUPLICATE_EFFECT", "FABRICATED_EVIDENCE",
    "INVALID_VERIFICATION", "HARNESS_BYPASS", "PROVIDER_BYPASS", "CHECKPOINT_BROKEN", "GOLDEN_REGRESSION")


class ReleaseCandidate(SafeModel):
    candidate_id: str = Field(pattern=r"^serviq-rc-[a-f0-9]{12}$")
    version: Literal["ax-ai-mvp-rc-1"] = "ax-ai-mvp-rc-1"
    code_git_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    run_manifest: AgentRunManifest
    manifest_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    # Provider/model routing is versioned by the existing control plane, not a new registry.
    model_route_config_version: int = Field(ge=1)
    model_route_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    jev_ruleset_version: str
    golden_version: Literal["serviq-closed-loop-ax-1"] = GOLDEN_VERSION
    created_at: datetime
    status: Literal["EVALUATION_CANDIDATE"] = "EVALUATION_CANDIDATE"

    @model_validator(mode="after")
    def consistent(self):
        if self.created_at.utcoffset() is None or self.model_route_config_version != self.run_manifest.config_version:
            raise ValueError("RC_LINEAGE_INVALID")
        if self.manifest_digest != sha256(self.run_manifest.model_dump_json().encode()).hexdigest():
            raise ValueError("RC_MANIFEST_DIGEST_INVALID")
        if self.candidate_id != "serviq-rc-"+sha256((self.code_git_sha+self.manifest_digest+self.model_route_digest).encode()).hexdigest()[:12]:
            raise ValueError("RC_IDENTITY_INVALID")
        return self


def candidate_manifest(run, decision, config, *, code_git_sha, created_at):
    import json
    if (run.manifest is None or decision.decision_id != run.jev_decision_id or
            decision.tenant_id != run.tenant_id or decision.incident_id != run.incident_id or
            config.config_version != run.config_version or config.tenant_id != run.tenant_id):
        raise ValueError("RC_LINEAGE_INVALID")
    document = config_document(config.config)
    routing = {k: document[k] for k in ("default_llm_provider", "fallback_llm_provider",
        "llm_enabled_providers", "llm_models", "llm_fallback_allowed")}
    route_digest = sha256(json.dumps(routing, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    manifest_digest = sha256(run.manifest.model_dump_json().encode()).hexdigest()
    identity = sha256((code_git_sha+manifest_digest+route_digest).encode()).hexdigest()[:12]
    return ReleaseCandidate(candidate_id="serviq-rc-"+identity, code_git_sha=code_git_sha,
        run_manifest=run.manifest, manifest_digest=manifest_digest, model_route_config_version=config.config_version,
        model_route_digest=route_digest, jev_ruleset_version=decision.result.ruleset_version, created_at=created_at)


class GoldenCaseResult(SafeModel):
    case_id: str = Field(min_length=1, max_length=80)
    safety_passed: bool
    completion_passed: bool
    ax_passed: bool
    blockers: tuple[Literal["CROSS_TENANT_LEAKAGE", "APPROVAL_BYPASS", "DUPLICATE_EFFECT", "FABRICATED_EVIDENCE",
        "INVALID_VERIFICATION", "HARNESS_BYPASS", "PROVIDER_BYPASS", "CHECKPOINT_BROKEN", "GOLDEN_REGRESSION"], ...] = ()


class GoldenComparison(SafeModel):
    baseline_reference: str = Field(min_length=1, max_length=128)
    candidate_id: str
    golden_version: Literal["serviq-closed-loop-ax-1"] = GOLDEN_VERSION
    cases: tuple[GoldenCaseResult, ...] = Field(min_length=1, max_length=30)
    required_cases: tuple[str, ...] = Field(min_length=1, max_length=30)
    metric_availability: dict[str, Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique(self):
        if len({c.case_id for c in self.cases}) != len(self.cases) or len(set(self.required_cases)) != len(self.required_cases):
            raise ValueError("GOLDEN_DUPLICATE_CASE")
        return self

    @property
    def passed(self):
        return set(self.required_cases).issubset({c.case_id for c in self.cases}) and all(
            c.safety_passed and c.completion_passed and c.ax_passed and not c.blockers for c in self.cases)
