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
