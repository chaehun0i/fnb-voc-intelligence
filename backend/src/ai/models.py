"""ai/models: 통합된 기능 책임, 기존 실행 계약 유지."""
from pydantic import BaseModel, ConfigDict, field_validator


class SafeModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    @field_validator("evidence_refs", check_fields=False)
    @classmethod
    def safe_refs(cls, values):
        import re
        if any(not re.fullmatch(r"(review|transaction|inventory):[A-Za-z0-9_.:-]{1,128}", value) for value in values):
            raise ValueError("원문 대신 안전한 Review 출처 참조를 사용해 주세요.")
        return values
