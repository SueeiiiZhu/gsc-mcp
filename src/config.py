from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Site URL (e.g. "sc-domain:example.com")
    site_url: str = ""

    # Google service account — JSON string or file path
    google_credentials: str = ""
    google_credentials_file: Path | None = None

    # Proxy (optional)
    proxy_url: str = ""

    # Token cache TTL
    google_access_token_ttl_seconds: int = 3300

    @field_validator("google_access_token_ttl_seconds")
    @classmethod
    def ttl_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("TTL must be > 0")
        return v


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
