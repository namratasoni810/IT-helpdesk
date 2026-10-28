"""Streamlit entrypoint.

Run with:  streamlit run app/frontend/streamlit_app.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import requests
import streamlit as st

# Make `app.*` importable regardless of the directory streamlit is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import get_settings  # noqa: E402

logging.basicConfig(level=logging.INFO)
settings = get_settings()

API_BASE = settings.api_base_url
REQUEST_TIMEOUT = 10


def api(method: str, path: str, **kwargs):
    url = f"{API_BASE}{path}"
    try:
        response = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
        response.raise_for_status()
        if response.content:
            return response.json()
        return None
    except requests.RequestException as exc:
        st.error(f"Could not reach the API at {url}: {exc}")
        st.caption(
            "Make sure the FastAPI backend is running "
            f"(`uvicorn app.main:app --port {settings.api_port}`)."
        )
        return None


st.set_page_config(page_title="IT Helpdesk Assistant", page_icon="🎧", layout="wide")

st.title("🎧 IT Helpdesk Assistant")
st.caption(
    "Submit and track IT support tickets. "
    f"Classification uses **{settings.classifier_mode}** mode."
)

# The multipage layout is handled by files in app/frontend/pages/.
st.markdown(
    """
    Use the sidebar to switch between pages:

    - **Submit a Ticket** — the employee-facing form
    - **Ticket Queue** — the IT-staff dashboard
    """
)
