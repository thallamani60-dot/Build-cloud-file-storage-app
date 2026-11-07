from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a local .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Cloud File Storage API"
    app_version: str = "2.0.0"
    environment: str = "development"
    database_url: str = "sqlite:///./cloud_file_storage.db"
    # A random per-process fallback keeps local health/docs usable. Production must
    # provide a stable value through a managed secret store.
    secret_key: SecretStr | None = None
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    jwt_algorithm: Literal["HS256"] = "HS256"

    aws_region: str = "ap-south-1"
    s3_bucket_name: str | None = None
    s3_endpoint_url: str | None = None
    s3_kms_key_id: str | None = None
    presigned_url_expire_seconds: int = Field(default=900, ge=60, le=3600)

    max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    rate_limit_storage_uri: str = "memory://"
    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_secret_key(self) -> "Settings":
        value = self.secret_key.get_secret_value().strip() if self.secret_key else ""
        is_placeholder = value.lower().startswith("replace-with") or "generate-a-random-value" in value.lower()
        if not value:
            if self.environment.lower() in {"prod", "production"}:
                raise ValueError("SECRET_KEY is required in production")
            self.secret_key = SecretStr(secrets.token_urlsafe(48))
        elif is_placeholder:
            if self.environment.lower() in {"prod", "production"}:
                raise ValueError("Replace the sample SECRET_KEY before production deployment")
            self.secret_key = SecretStr(secrets.token_urlsafe(48))
        return self

    @property
    def jwt_secret(self) -> str:
        assert self.secret_key is not None
        return self.secret_key.get_secret_value()

    @property
    def allowed_extensions(self) -> set[str]:
        return {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".csv", ".docx"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
