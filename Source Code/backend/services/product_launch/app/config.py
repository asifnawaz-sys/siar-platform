"""Application configuration.

All settings are environment-driven so the same code runs unchanged in
development and production. Copy `.env.example` to `.env` and adjust values.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # --- Core ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    # --- Database ---
    # SQLite by default. To migrate to Postgres/MySQL later, set DATABASE_URL,
    # e.g. postgresql+psycopg://user:pass@host/dbname  (no code changes needed).
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'launch.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Admin credentials (protects the /admin area) ---
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    # Store a hash in production. If ADMIN_PASSWORD_HASH is set it wins;
    # otherwise ADMIN_PASSWORD (plaintext) is used for convenience in dev.
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
    ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")

    # --- Field definitions ---
    FIELD_CONFIG_PATH = os.environ.get(
        "FIELD_CONFIG_PATH", str(Path(__file__).resolve().parent / "field_config.json")
    )

    # --- CSV export ---
    # Delimiter used to join multi-value fields (sizes, fabrics, images, ...)
    MULTI_VALUE_DELIMITER = os.environ.get("MULTI_VALUE_DELIMITER", " | ")

    # --- Security / cookies ---
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Set to True when served over HTTPS (recommended in production).
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), False)

    # Length (in bytes) of the random launch tokens -> ~1.33x chars when base64url.
    TOKEN_BYTES = int(os.environ.get("TOKEN_BYTES", "9"))
