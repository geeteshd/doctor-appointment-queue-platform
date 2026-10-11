"""Application configuration, read from environment variables.

Using pydantic-settings keeps config typed and in one place. Every value has a
sensible default so the app runs locally without a .env, but can be overridden
in Docker / production.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Default points at the docker-compose postgres service. For a purely local
    # run without Docker, override with e.g. sqlite:///./clinic.db
    database_url: str = "postgresql+psycopg2://clinic:clinic@db:5432/clinic"

    # Prescription upload rules (configurable, as the assignment requires)
    upload_dir: str = "uploads"
    allowed_image_extensions: str = "jpg,jpeg,png,pdf"
    max_upload_size_mb: int = 5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
