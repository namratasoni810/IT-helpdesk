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
    # Local development uses DATABASE_URL. Databricks Apps injects the
    # Lakebase connection fields and endpoint resource at runtime.
    database_url: str
    lakebase_endpoint: str | None

    # --- Classification (Anthropic) -----------------------------------------
    anthropic_api_key: str
    anthropic_model: str
    classifier_mode: str
    agent_app_name: str

    # --- Worker --------------------------------------------------------------
    worker_poll_interval: float

    # --- Servers --------------------------------------------------------------
    api_port: int
    streamlit_port: int
    api_base_url: str


@lru_cache
def get_settings() -> Settings:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    requested_mode = os.getenv("CLASSIFIER_MODE", "").strip().lower()
    if requested_mode not in {"", "agent", "anthropic", "mock"}:
        raise ValueError(
            "CLASSIFIER_MODE must be 'agent', 'anthropic', or 'mock'."
        )
    agent_app_name = os.getenv("AGENT_APP_NAME", "").strip()
    if requested_mode == "agent" and not agent_app_name:
        raise ValueError(
            "AGENT_APP_NAME is required when CLASSIFIER_MODE is 'agent'. "
            "Add the Agent Bricks app as a Databricks Apps resource."
        )
    if requested_mode == "anthropic" and not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is required when CLASSIFIER_MODE is 'anthropic'."
        )
    if requested_mode == "agent":
        classifier_mode = "agent"
    elif requested_mode == "anthropic":
        classifier_mode = "anthropic"
    elif requested_mode == "mock":
        classifier_mode = "mock"
    elif api_key:
        classifier_mode = "anthropic"
    else:
        classifier_mode = "mock"
    api_port = int(os.getenv("API_PORT", "8000"))
    api_base_url = (
        os.getenv("HELPDESK_API_URL") or f"http://127.0.0.1:{api_port}"
    ).rstrip("/")
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://helpdesk:helpdesk@localhost:5432/helpdesk",
        ),
        lakebase_endpoint=os.getenv("LAKEBASE_ENDPOINT"),
        anthropic_api_key=api_key,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
        classifier_mode=classifier_mode,
        agent_app_name=agent_app_name,
        worker_poll_interval=float(os.getenv("WORKER_POLL_INTERVAL", "5")),
        api_port=api_port,
        streamlit_port=int(os.getenv("STREAMLIT_PORT", "8501")),
        api_base_url=api_base_url,
    )
