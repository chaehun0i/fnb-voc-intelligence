"""생성 문장 대신 원본 참조와 실제 검색 출처를 정규화합니다."""
from src.agents.models import EvidenceCandidate, NormalizedEvidence
from src.application.security.principal import AccessError


def normalize_evidence(candidates, *, tenant_id, store, agent_run_id):
    grouped = {}
    for value in candidates:
        item = EvidenceCandidate.model_validate(value.model_dump(mode="json"))
        if item.tenant_id != tenant_id or item.store != store:
            raise AccessError()
        previous = grouped.get(item.source_ref)
        if previous:
            if previous.stance != item.stance or previous.observation_code != item.observation_code:
                raise ValueError("같은 출처의 상충 관측은 정규화 전에 해결해야 합니다.")
            item = item.model_copy(update={"rank": min(item.rank, previous.rank),
                "provenance": tuple(sorted(set(item.provenance+previous.provenance))),
                "retrieved_at": min(item.retrieved_at, previous.retrieved_at)})
        grouped[item.source_ref] = item
    return tuple(NormalizedEvidence(**item.model_dump(), source_id=item.source_ref.removeprefix("review:"),
        agent_run_id=agent_run_id) for item in sorted(grouped.values(), key=lambda e: (e.rank, e.source_ref)))
