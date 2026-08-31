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
