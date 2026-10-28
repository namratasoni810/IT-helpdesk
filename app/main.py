"""FastAPI backend.

Thin HTTP layer over the database + worker. The Streamlit UI talks to this,
so the UI stays free of direct DB access.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import db, worker
from app.config import get_settings
from app.classifier import Classification, classify_ticket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("helpdesk.api")


# --- Lifespan: pool + worker start/stop -------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_pool()
    worker.start_worker()
    logger.info("Helpdesk API ready")
    try:
        yield
    finally:
        worker.stop_worker()
        db.close_pool()
        logger.info("Helpdesk API shut down")


app = FastAPI(title="IT Helpdesk Assistant", version="0.1.0", lifespan=lifespan)


# --- Schemas -----------------------------------------------------------------

class TicketCreate(BaseModel):
    employee_name: str = Field(..., min_length=1, max_length=200)
    issue_text: str = Field(..., min_length=1)


class TicketOut(BaseModel):
    id: int
    employee_name: str
    issue_text: str
    category: Optional[str] = None
    priority: Optional[str] = None
    suggested_fix: Optional[str] = None
    status: str
    created_at: str
    updated_at: str


class ResolveRequest(BaseModel):
    status: str = "resolved"


# --- Routes ------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "mock_mode": settings.classifier_mode == "mock",
        "classifier_mode": settings.classifier_mode,
    }


@app.post("/tickets", response_model=TicketOut, status_code=201)
def create_ticket(payload: TicketCreate) -> dict:
    """Submit a new IT issue (employee-facing)."""
    ticket = db.create_ticket(payload.employee_name, payload.issue_text)
    logger.info("Created ticket #%s for %s", ticket["id"], payload.employee_name)
    return _serialise(ticket)


@app.get("/tickets", response_model=list[TicketOut])
def list_tickets() -> list[dict]:
    """List every ticket (IT-staff-facing)."""
    return [_serialise(t) for t in db.list_tickets()]


@app.get("/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int) -> dict:
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _serialise(ticket)


@app.post("/tickets/{ticket_id}/resolve", response_model=TicketOut)
def resolve_ticket(ticket_id: int, payload: ResolveRequest) -> dict:
    """Mark a ticket resolved (IT-staff-facing)."""
    if not db.get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    db.update_ticket_status(ticket_id, payload.status)
    return _serialise(db.get_ticket(ticket_id))


@app.post("/tickets/{ticket_id}/classify", response_model=Classification)
def classify_ticket_endpoint(ticket_id: int) -> Classification:
    """Classify on demand (handy for debugging without waiting on the worker)."""
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return classify_ticket(ticket["issue_text"])


@app.post("/worker/run")
def run_worker_once() -> dict:
    """Trigger one classification pass immediately."""
    processed = worker.process_new_tickets()
    return {"processed": processed}


# --- Helpers -----------------------------------------------------------------

def _serialise(row: dict) -> dict:
    """Stringify timestamps so the JSON response is stable across clients."""
    return {
        **row,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }
