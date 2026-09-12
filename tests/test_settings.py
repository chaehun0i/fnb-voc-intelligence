import pytest
from pydantic import ValidationError

from src.config import Settings, settings


def test_data_paths_are_rooted_in_project() -> None:
    assert settings.data_dir == settings.project_root / "data"
    assert settings.raw_data_dir == settings.data_dir / "raw"
    assert settings.interim_data_dir == settings.data_dir / "interim"
    assert settings.processed_data_dir == settings.data_dir / "processed"


def test_optional_secrets_default_to_none() -> None:
    configured = Settings()
    assert configured.database_url is None
    assert configured.openai_api_key is None


def test_postgresql_url_validation() -> None:
    assert Settings(postgresql_url="postgresql://localhost/test").postgresql_url
    with pytest.raises(ValidationError):
        Settings(postgresql_url="sqlite:///test.db")


def test_embedding_settings_have_safe_defaults() -> None:
    configured = Settings()
    assert configured.embedding_provider == "fake"
    assert configured.embedding_model == "fake-v1"
    assert configured.embedding_dimension == 384
    assert configured.embedding_batch_size == 100


@pytest.mark.parametrize("dimension", [0, -1, 2001])
def test_embedding_dimension_must_be_supported(dimension: int) -> None:
    with pytest.raises(ValidationError):
        Settings(embedding_dimension=dimension)


def test_embedding_batch_size_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(embedding_batch_size=0)


def test_rag_settings_have_safe_defaults() -> None:
    configured = Settings()
    assert configured.rag_retrieval_mode == "hybrid"
    assert configured.rag_top_k == 5
    assert configured.rag_context_max_items == 5
    assert configured.rag_context_max_chars == 6000
    assert configured.generator_model == "fake-v1"
    assert configured.rag_minimum_evidence == 1


@pytest.mark.parametrize(
    "values",
    [
        {"rag_retrieval_mode": "unknown"},
        {"rag_top_k": 0},
        {"rag_context_max_items": 0},
        {"rag_context_max_chars": 0},
        {"rag_minimum_evidence": 0},
    ],
)
def test_rag_settings_reject_invalid_values(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(**values)


def test_evaluation_settings_defaults_and_validation() -> None:
    configured = Settings()
    assert configured.evaluation_dataset_path.name == "rag_evaluation.jsonl"
    assert configured.evaluation_retrieval_k == 5
    assert configured.evaluation_evaluator_mode == "deterministic"
    for values in (
        {"evaluation_retrieval_k": 0},
        {"evaluation_recall_threshold": 1.1},
        {"evaluation_precision_threshold": -0.1},
        {"evaluation_evaluator_mode": "llm"},
    ):
        with pytest.raises(ValidationError):
            Settings(**values)
