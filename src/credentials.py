"""Load service account credentials from env var or file.

Resolution order:
  1. GOOGLE_CREDENTIALS env var (JSON string)
  2. GOOGLE_CREDENTIALS_FILE env var (path to JSON file)
"""

import json

from src.config import settings


def load_service_account() -> dict:
    """Load the Google Service Account JSON."""
    # 1. JSON string from env var
    if settings.google_credentials:
        return json.loads(settings.google_credentials)

    # 2. File path
    if settings.google_credentials_file:
        path = settings.google_credentials_file
        if not path.exists():
            raise FileNotFoundError(
                f"Service account file not found: {path}"
            )
        with path.open() as f:
            return json.load(f)

    raise RuntimeError(
        "No credentials configured. "
        "Set GOOGLE_CREDENTIALS (JSON string) or GOOGLE_CREDENTIALS_FILE (path)."
    )
