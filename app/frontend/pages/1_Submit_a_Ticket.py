"""Employee-facing page: submit an IT issue."""

from __future__ import annotations

import sys
from pathlib import Path

import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import get_settings  # noqa: E402

settings = get_settings()
API_BASE = f"http://localhost:{settings.api_port}"


st.set_page_config(page_title="Submit a Ticket", page_icon="📝", layout="wide")
st.title("📝 Submit an IT Ticket")
st.write("Describe the problem and we'll route it to the right team automatically.")


def submit_ticket(employee_name: str, issue_text: str) -> bool:
    try:
        response = requests.post(
            f"{API_BASE}/tickets",
            json={"employee_name": employee_name, "issue_text": issue_text},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"Failed to submit ticket: {exc}")
        return False

    ticket = response.json()
    st.success(
        f"Ticket #{ticket['id']} submitted. "
        "It will be classified automatically within a few seconds — "
        "check the Ticket Queue page."
    )
    return True


with st.container(border=True):
    with st.form("submit_ticket_form", clear_on_submit=True):
        name = st.text_input("Your name", placeholder="e.g. Ada Lovelace")
        issue = st.text_area(
            "What's the issue?",
            placeholder=(
                "e.g. My laptop won't connect to the office Wi-Fi — it keeps "
                "asking for a password and then fails."
            ),
            height=140,
        )
        submitted = st.form_submit_button("Submit ticket", type="primary")

        if submitted:
            if not name.strip() or not issue.strip():
                st.error("Please fill in both your name and the issue description.")
            elif submit_ticket(name.strip(), issue.strip()):
                pass  # success message already shown by submit_ticket()
