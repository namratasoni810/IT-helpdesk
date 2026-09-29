"""Centralised configuration.

Everything the app needs is read from environment variables (loaded from a
local ``.env`` file via python-dotenv). Keeping this in one place means
repointing the prototype at Databricks Lakebase later is a config change, not
a code change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

# Load a local .env if one exists. Missing file is fine -- real env vars win.
load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- Database -----------------------------------------------------------
    # Plain Postgres connection string. Swap this for the Lakebase endpoint
    # when you migrate; nothing else in the codebase needs to change.
    database_url: str

    # --- Classification (Anthropic) -----------------------------------------
    anthropic_api_key: str
    anthropic_model: str
    # True when no API key is configured -> classifier returns deterministic
    # mock results so the whole pipeline is testable offline.
    mock_mode: bool

    # --- Worker --------------------------------------------------------------
    worker_poll_interval: float

    # --- Servers --------------------------------------------------------------
    api_port: int
    streamlit_port: int


@lru_cache
def get_settings() -> Settings:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://helpdesk:helpdesk@localhost:5432/helpdesk",
        ),
        anthropic_api_key=api_key,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
        mock_mode=not api_key,
        worker_poll_interval=float(os.getenv("WORKER_POLL_INTERVAL", "5")),
        api_port=int(os.getenv("API_PORT", "8000")),
        streamlit_port=int(os.getenv("STREAMLIT_PORT", "8501")),
    )
