"""IT-staff-facing page: the ticket queue with a resolve action."""

from __future__ import annotations

import sys
from pathlib import Path

import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import get_settings  # noqa: E402

settings = get_settings()
API_BASE = f"http://localhost:{settings.api_port}"

PRIORITY_BADGE = {"high": "🔴", "medium": "🟡", "low": "🟢"}
STATUS_BADGE = {"new": "🆕", "classified": "✅", "resolved": "✔️"}


st.set_page_config(page_title="Ticket Queue", page_icon="🗂️", layout="wide")
st.title("🗂️ IT Ticket Queue")


def fetch_tickets():
    try:
        response = requests.get(f"{API_BASE}/tickets", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(f"Failed to load tickets: {exc}")
        return []


def resolve_ticket(ticket_id: int):
    try:
        response = requests.post(
            f"{API_BASE}/tickets/{ticket_id}/resolve",
            json={"status": "resolved"},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        st.error(f"Failed to resolve ticket #{ticket_id}: {exc}")


# Refresh happens on every page load; the button below forces a reload.
if "refresh_nonce" not in st.session_state:
    st.session_state.refresh_nonce = 0

col1, col2 = st.columns([1, 6])
with col1:
    if st.button("🔄 Refresh"):
        st.session_state.refresh_nonce += 1
with col2:
    if st.button("▶️ Classify new tickets now"):
        try:
            result = requests.post(
                f"{API_BASE}/worker/run", timeout=30
            ).json()
            st.toast(f"Classified {result.get('processed', 0)} ticket(s)")
        except requests.RequestException as exc:
            st.error(f"Failed to trigger the worker: {exc}")
        st.session_state.refresh_nonce += 1

tickets = fetch_tickets()

if not tickets:
    st.info("No tickets yet. Submit one from the 'Submit a Ticket' page.")
    st.stop()

st.subheader(f"{len(tickets)} ticket(s)")

# One form per ticket so each row gets its own submit button.
for ticket in tickets:
    priority = ticket.get("priority") or "—"
    status = ticket.get("status") or "—"
    resolved = status == "resolved"

    with st.container(border=True):
        header_col, button_col = st.columns([8, 2])
        with header_col:
            st.markdown(
                f"**#{ticket['id']} — {ticket['employee_name']}** "
                f"{STATUS_BADGE.get(status, '')} "
                f"{PRIORITY_BADGE.get(priority, '')} "
                f"`{priority}` · `{status}`"
            )
        with button_col:
            with st.form(key=f"resolve_form_{ticket['id']}"):
                if st.form_submit_button(
                    "Mark resolved",
                    disabled=resolved,
                    type="primary" if not resolved else "secondary",
                ):
                    resolve_ticket(ticket["id"])
                    st.toast(f"Ticket #{ticket['id']} marked resolved")
                    st.session_state.refresh_nonce += 1
                    st.rerun()

        st.markdown(f"**Issue:** {ticket['issue_text']}")

        fix = ticket.get("suggested_fix")
        if ticket.get("category") or fix:
            st.markdown(
                f"**Category:** {ticket.get('category') or '—'} &nbsp; "
                f"**Suggested fix:** {fix or '—'}"
            )
        else:
            st.caption("Awaiting classification…")
