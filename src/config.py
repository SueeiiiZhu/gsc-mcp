from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Brand = Literal["boostvision", "pigeoncast", "firstorder", "cubesolver"]
BRANDS: tuple[Brand, ...] = ("boostvision", "pigeoncast", "firstorder", "cubesolver")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    google_access_token_ttl_seconds: int = 3300

    # Per-brand VPS proxy endpoints (only required brands need to be set)
    proxy_boostvision: str = ""
    proxy_pigeoncast: str = ""
    proxy_firstorder: str = ""
    proxy_cubesolver: str = ""

    # Default brand (optional)
    gsc_default_brand: str = ""

    # Per-brand site URLs (optional convenience defaults)
    site_url_boostvision: str = ""
    site_url_pigeoncast: str = ""
    site_url_firstorder: str = ""
    site_url_cubesolver: str = ""

    # Credentials directory (file-based fallback)
    credentials_dir: Path = Path("credentials")

    # Per-brand service account JSON via env var (takes precedence over file)
    google_credentials_boostvision: str = ""
    google_credentials_pigeoncast: str = ""
    google_credentials_firstorder: str = ""
    google_credentials_cubesolver: str = ""

    @field_validator("google_access_token_ttl_seconds")
    @classmethod
    def ttl_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("TTL must be > 0")
        return v

    def proxy_for(self, brand: Brand) -> str:
        """Return the VPS proxy URL for the brand, or empty string if not configured."""
        return {
            "boostvision": self.proxy_boostvision,
            "pigeoncast": self.proxy_pigeoncast,
            "firstorder": self.proxy_firstorder,
            "cubesolver": self.proxy_cubesolver,
        }[brand]

    def google_credentials_for(self, brand: Brand) -> str:
        """Return raw JSON string for the brand, or empty string if not set."""
        return {
            "boostvision": self.google_credentials_boostvision,
            "pigeoncast": self.google_credentials_pigeoncast,
            "firstorder": self.google_credentials_firstorder,
            "cubesolver": self.google_credentials_cubesolver,
        }[brand]

    def site_url_for(self, brand: Brand) -> str:
        return {
            "boostvision": self.site_url_boostvision,
            "pigeoncast": self.site_url_pigeoncast,
            "firstorder": self.site_url_firstorder,
            "cubesolver": self.site_url_cubesolver,
        }[brand]


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
