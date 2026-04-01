"""Load brand-specific credentials from env var or CREDENTIALS_DIR.

Resolution order:
  1. GOOGLE_CREDENTIALS_{BRAND} env var (JSON string)
  2. File at {CREDENTIALS_DIR}/{brand}/{filename}
"""

import json
from pathlib import Path

from src.config import Brand, settings


def credentials_path(brand: Brand, filename: str) -> Path:
    return settings.credentials_dir / brand / filename


def load_service_account(brand: Brand, filename: str = "gsc.json") -> dict:
    """Load a Google Service Account JSON for the given brand."""
    # 1. Try env var
    raw = settings.google_credentials_for(brand)
    if raw:
        return json.loads(raw)

    # 2. Fall back to file
    path = credentials_path(brand, filename)
    if not path.exists():
        raise FileNotFoundError(
            f"Service account not found for brand {brand!r}. "
            f"Set GOOGLE_CREDENTIALS_{brand.upper()} env var "
            f"or place JSON file at {path}"
        )
    with path.open() as f:
        return json.load(f)
