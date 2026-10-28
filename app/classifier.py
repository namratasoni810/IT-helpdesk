"""Ticket classification.

This module is the ONLY place that knows about the LLM. The rest of the app
calls ``classify_ticket(issue_text)`` and gets back a ``Classification`` --
that contract is what lets you swap these internals for an Agent Bricks agent
later without touching anything else.

Select ``agent``, ``anthropic``, or ``mock`` with ``CLASSIFIER_MODE``. If the
mode is unset and no ``ANTHROPIC_API_KEY`` is configured, deterministic
keyword-based mock results keep the pipeline testable without network calls.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict

from app.config import get_settings

logger = logging.getLogger(__name__)

VALID_CATEGORIES = ("hardware", "software", "network", "access")
VALID_PRIORITIES = ("low", "medium", "high")


@dataclass(frozen=True)
class Classification:
    """The contract the rest of the app depends on.

    Keep these three fields stable when you re-implement this module with
    Agent Bricks -- callers only ever consume this structure.
    """

    category: str
    priority: str
    suggested_fix: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Mock classifier (offline fallback)
# ---------------------------------------------------------------------------

_MOCK_RULES = (
    (
        ("password", "reset", "login", "sign in", "account", "credential", "mfa", "2fa"),
        "access",
        "high",
        "Verify the user's identity, then trigger a password reset via the "
        "self-service portal and have them re-enrol MFA if needed.",
    ),
    (
        ("laptop", "monitor", "keyboard", "mouse", "printer", "screen", "battery"),
        "hardware",
        "medium",
        "Check physical connections and run the hardware diagnostic script; "
        "swap in a spare device if the fault is confirmed.",
    ),
    (
        ("wifi", "internet", "network", "vpn", "connect", "drop", "latency"),
        "network",
        "high",
        "Confirm the network/VPN profile, re-seat the adapter, and re-test "
        "against the known-good SSID before escalating to network ops.",
    ),
    (
        ("install", "crash", "error", "bug", "freeze", "update", "application"),
        "software",
        "medium",
        "Reproduce the fault, clear the app cache/preferences, reinstall the "
        "latest managed version, and capture logs if it recurs.",
    ),
)


def _mock_classify(issue_text: str) -> Classification:
    text = issue_text.lower()
    for keywords, category, priority, fix in _MOCK_RULES:
        if any(kw in text for kw in keywords):
            return Classification(category, priority, fix)
    return Classification(
        category="software",
        priority="low",
        suggested_fix="Triage with the user to reproduce the issue, then route "
        "to the appropriate second-line team.",
    )


# ---------------------------------------------------------------------------
# Anthropic classifier
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an IT helpdesk triage assistant.
Read the employee's issue and classify it.

Return ONLY a JSON object with exactly these keys and no other text:
{
  "category": one of ["hardware", "software", "network", "access"],
  "priority": one of ["low", "medium", "high"],
  "suggested_fix": a single short sentence (max ~25 words) describing the \
first troubleshooting step an IT technician should try.
}

Rules:
- If the issue is ambiguous, pick the closest category rather than refusing.
- "access" covers accounts, passwords, MFA, logins and permissions.
- "high" priority means work is fully blocked or a security issue is involved.
- Never wrap the JSON in markdown fences or add commentary."""


def _normalise(raw: Dict[str, Any]) -> Classification:
    """Coerce LLM output into the guaranteed contract."""
    category = str(raw.get("category", "")).strip().lower()
    priority = str(raw.get("priority", "")).strip().lower()
    fix = str(raw.get("suggested_fix", "")).strip()

    if category not in VALID_CATEGORIES:
        logger.warning("LLM returned unexpected category %r; defaulting", category)
        category = "software"
    if priority not in VALID_PRIORITIES:
        logger.warning("LLM returned unexpected priority %r; defaulting", priority)
        priority = "medium"
    if not fix:
        fix = "Triage with the user and route to the appropriate team."

    return Classification(category, priority, fix)


def _extract_json(text: str) -> Dict[str, Any]:
    """Pull a JSON object out of a model response that may include prose."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back to the first {...} block in the response.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse JSON from classifier response: {text!r}")


def _call_anthropic(issue_text: str) -> Dict[str, Any]:
    """Make the raw API call. Isolated so it is trivial to mock in tests."""
    import anthropic  # imported lazily so mock mode needs no SDK installed

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=300,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": issue_text}],
    )
    # Concatenate text blocks (vision/other block types are not expected here).
    return _extract_json(
        "".join(
            block.text
            for block in message.content
            if getattr(block, "type", None) == "text"
        )
    )


def _call_agent(issue_text: str) -> Dict[str, Any]:
    """Call the deployed Agent Bricks app and parse its classification."""
    import uuid

    import requests
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    app_url = w.apps.get(os.environ["AGENT_APP_NAME"]).url
    resp = requests.post(
        f"{app_url.rstrip('/')}/api/invocations",
        headers={**w.config.authenticate(), "Content-Type": "application/json"},
        timeout=60,
        json={
            "id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "input": [{"role": "user", "content": issue_text}],
        },
    )
    resp.raise_for_status()
    data = resp.json()
    logger.debug("Agent Bricks raw response: %s", data)

    messages = data["output"]["output"]
    for message in reversed(messages):
        if message.get("type") != "ai":
            continue

        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            )
        if isinstance(content, str) and content.strip():
            return _extract_json(content)

    raise ValueError("Agent Bricks response did not contain an assistant message")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_ticket(issue_text: str) -> Classification:
    """Classify a single ticket.

    Select the configured classifier while keeping the result contract stable.
    """
    if not issue_text or not issue_text.strip():
        # Degenerate input still yields a valid, safe classification.
        return Classification("software", "low", "Ask the user for more detail.")

    settings = get_settings()
    mode = os.getenv("CLASSIFIER_MODE", "").strip().lower()
    if mode == "mock" or (mode != "agent" and settings.mock_mode):
        logger.debug("Classifier in mock mode")
        return _mock_classify(issue_text)

    try:
        raw = _call_agent(issue_text) if mode == "agent" else _call_anthropic(issue_text)
        return _normalise(raw)
    except Exception as exc:  # noqa: BLE001 - fail soft, keep the worker alive
        # Never let a classifier hiccup kill the background worker. The ticket
        # stays 'new' and will be retried on the next poll.
        logger.exception("Classification failed; leaving ticket for retry: %s", exc)
        raise


def classify_ticket_safe(issue_text: str) -> Classification:
    """Non-raising variant for the background worker."""
    try:
        return classify_ticket(issue_text)
    except Exception:  # noqa: BLE001
        logger.exception("Safe classification failed; triaging manually")
        return Classification(
            "software",
            "medium",
            "Classification failed; triage manually with the user.",
        )
