"""Central application settings."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INTERIM_DATA_DIR = DATA_DIR / "interim"
PROCESSED_DATA_DIR = DATA_DIR / "processed"


class Settings(BaseSettings):
    """Environment-backed application settings."""

    project_root: Path = PROJECT_ROOT
    data_dir: Path = DATA_DIR
    raw_data_dir: Path = RAW_DATA_DIR
    interim_data_dir: Path = INTERIM_DATA_DIR
    processed_data_dir: Path = PROCESSED_DATA_DIR
    app_env: str = "local"
    database_url: str | None = None
    postgresql_url: str | None = None
    openai_api_key: str | None = None
    embedding_provider: str = "fake"
    embedding_model: str = "fake-v1"
    embedding_dimension: int = Field(default=384, ge=1, le=2000)
    embedding_batch_size: int = Field(default=100, ge=1)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("postgresql_url")
    @classmethod
    def validate_postgresql_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("postgresql://", "postgres://")):
            raise ValueError("must use a PostgreSQL URL")
        return value


settings = Settings()
