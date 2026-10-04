"""JSON/schema와 업무 의미 검증을 서로 다른 실패로 구분합니다."""
import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from src.llm.errors import LLMError, LLMErrorCode


def schema_validator(schema_json):
    try:
        schema = json.loads(schema_json)
        Draft202012Validator.check_schema(schema)
        # 외부 URL ref는 검증 중 네트워크/임의 자료 접근을 유발할 수 있습니다.
        def local_refs(value):
            if isinstance(value, dict):
                for key in ("$ref", "$dynamicRef", "$recursiveRef"):
                    if key in value and not value[key].startswith("#"):
                        raise LLMError(LLMErrorCode.INVALID_REQUEST)
                for nested in value.values():
                    local_refs(nested)
            elif isinstance(value, list):
                for nested in value:
                    local_refs(nested)
        local_refs(schema)
        return Draft202012Validator(schema)
    except (ValueError, SchemaError):
        raise LLMError(LLMErrorCode.INVALID_REQUEST) from None


def validate_output(content, validator, domain_validator=None):
    def reject_non_json_number(_):
        raise ValueError("JSON에서 NaN/Infinity는 지원하지 않습니다.")
    try:
        value = json.loads(content, parse_constant=reject_non_json_number)
        validator.validate(value)
    except (ValueError, ValidationError):
        raise LLMError(LLMErrorCode.OUTPUT_SCHEMA_INVALID) from None
    if domain_validator is not None:
        try:
            domain_validator(value)
        except (ValueError, KeyError):
            raise LLMError(LLMErrorCode.OUTPUT_DOMAIN_INVALID) from None
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
