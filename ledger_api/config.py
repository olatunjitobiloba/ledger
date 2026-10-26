from __future__ import annotations

import json
import os
from pathlib import Path

# The API and worker run independently from judge.py's CLI, so they must load
# local development configuration themselves. Existing environment variables
# still win, which is what Rumpty's production environment uses.
from ledger.judges import load_dotenv

load_dotenv()


def database_url() -> str:
    """Return a SQLAlchemy psycopg URL from Rumpty or local configuration."""
    value = os.getenv("LEDGER_DATABASE_URL", "sqlite:///./data/ledger.db")
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


DATABASE_URL = database_url()
BLOB_DIR = Path(os.getenv("LEDGER_BLOB_DIR", "./data/blobs"))
ADMIN_TOKEN = os.getenv("LEDGER_ADMIN_TOKEN", "")
POLL_SECONDS = float(os.getenv("LEDGER_WORKER_POLL_SECONDS", "0.5"))
DB_SSLMODE = os.getenv("LEDGER_DB_SSLMODE", "")
DB_SSLROOTCERT = os.getenv("LEDGER_DB_SSLROOTCERT", "")
_cors = [
    origin.strip()
    for origin in os.getenv("LEDGER_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
CORS_ORIGINS = _cors or ["*"]
# SQLite is disposable local development. Managed Postgres must be created by
# the reviewed migration, never implicitly at API startup.
AUTO_CREATE_SCHEMA = (
    os.getenv(
        "LEDGER_AUTO_CREATE_SCHEMA",
        "true" if DATABASE_URL.startswith("sqlite") else "false",
    ).lower()
    == "true"
)

# USD per token. This intentionally lives in configuration rather than code so
# providers can update prices without a deployment.
DEFAULT_PRICING = {
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "llama-3.3-70b-versatile": {"input": 0.59 / 1_000_000, "output": 0.79 / 1_000_000},
    "llama-3.1-8b-instant": {"input": 0.05 / 1_000_000, "output": 0.08 / 1_000_000},
    "openai/gpt-oss-120b": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "openai/gpt-oss-20b": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
}
try:
    _pricing = json.loads(os.getenv("LEDGER_MODEL_PRICING", "")) or DEFAULT_PRICING
except json.JSONDecodeError:
    _pricing = DEFAULT_PRICING
MODEL_PRICING = _pricing
