"""Load brand-specific credentials from CREDENTIALS_DIR."""

import json
from pathlib import Path

from src.config import Brand, settings


def credentials_path(brand: Brand, filename: str) -> Path:
    return settings.credentials_dir / brand / filename


def load_service_account(brand: Brand, filename: str = "gsc.json") -> dict:
    """Load a Google Service Account JSON for the given brand."""
    path = credentials_path(brand, filename)
    if not path.exists():
        raise FileNotFoundError(f"Service account not found: {path}")
    with path.open() as f:
        return json.load(f)
