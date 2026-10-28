"""Background classification worker.

A simple polling loop: find tickets with status='new', classify them, and
update the row. Runs in a daemon thread so it needs no extra process or
infrastructure -- easy to swap for a scheduled job or Databricks job trigger
later.
"""

from __future__ import annotations

import logging
import threading

from app import classifier, db
from app.config import get_settings

logger = logging.getLogger(__name__)


def process_new_tickets(batch_size: int = 50) -> int:
    """Classify all pending tickets. Returns the number classified."""
    ticket_ids = db.get_new_ticket_ids(batch_size=batch_size)
    if not ticket_ids:
        return 0

    classified = 0
    for ticket_id in ticket_ids:
        ticket = db.get_ticket(ticket_id)
        if not ticket:
            continue

        try:
            result = classifier.classify_ticket(ticket["issue_text"])
        except Exception:
            logger.exception(
                "Could not classify ticket #%s; it will be retried",
                ticket_id,
            )
            continue
        db.update_ticket_classification(
            ticket_id=ticket_id,
            category=result.category,
            priority=result.priority,
            suggested_fix=result.suggested_fix,
        )
        classified += 1
        logger.info(
            "Classified ticket #%s -> %s/%s",
            ticket_id,
            result.category,
            result.priority,
        )
    return classified


def _worker_loop(stop_event: threading.Event) -> None:
    interval = get_settings().worker_poll_interval
    logger.info("Classification worker started (polling every %ss)", interval)
    while not stop_event.is_set():
        try:
            processed = process_new_tickets()
            if processed:
                logger.info("Processed %s new ticket(s)", processed)
        except Exception:  # noqa: BLE001 - a poll must never kill the worker
            logger.exception("Worker poll failed; will retry next cycle")

        # sleep() is interruptible, so shutdown stays responsive.
        stop_event.wait(interval)


_stop_event: threading.Event | None = None
_thread: threading.Thread | None = None


def start_worker() -> None:
    """Start the background classification loop (idempotent)."""
    global _stop_event, _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event = threading.Event()
    _thread = threading.Thread(
        target=_worker_loop,
        args=(_stop_event,),
        name="classification-worker",
        daemon=True,
    )
    _thread.start()


def stop_worker() -> None:
    global _stop_event, _thread
    if _stop_event is not None:
        _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=10)
    _stop_event = None
    _thread = None
