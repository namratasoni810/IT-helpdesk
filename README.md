# IT Helpdesk Assistant

Employee ticket submission → automatic ticket classification → IT staff resolution queue.

Runs locally with Postgres or on **Databricks Lakebase**, with a combined
**Streamlit + FastAPI Databricks App** and **Agent Bricks** classification.

## Architecture

```
┌──────────────┐     HTTP     ┌───────────────┐   psycopg2   ┌──────────────┐
│  Streamlit   │ ───────────► │   FastAPI     │ ───────────► │   Postgres   │
│  (frontend)  │              │   (backend)   │              │  (in Docker) │
└──────────────┘              └───┬───────────┘              └──────────────┘
                                  │
                          ┌───────▼────────┐
                          │  Worker thread │ ──► classifier.py ──► configured classifier
                          │  (polls 'new') │      (Agent Bricks, Anthropic, or mock)
                          └────────────────┘
```

## Project layout

```
application/
├── docker-compose.yml          # Postgres 16 (stands in for Lakebase)
├── requirements.txt
├── .env.example                # copy to .env
├── run_api.py                  # starts FastAPI (+ background worker thread)
├── run_app.py                  # starts FastAPI and Streamlit as one app
├── run_worker.py               # optional: worker as a standalone process
└── app/
    ├── config.py               # all env-var config in one place
    ├── db.py                   # schema + SQL queries (psycopg2)
    ├── classifier.py           # LLM classification — the Agent Bricks swap point
    ├── worker.py               # polling loop that classifies 'new' tickets
    ├── main.py                 # FastAPI app
    └── frontend/
        ├── streamlit_app.py    # landing page
        └── pages/
            ├── 1_Submit_a_Ticket.py   # employee form
            └── 2_Ticket_Queue.py      # IT staff dashboard
```

## Prerequisites

- **Python 3.12** — installed in this workspace at
  `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`
- **Docker Desktop** — for Postgres
- An **Anthropic API key** — *optional*. Without one the classifier runs in
  deterministic **mock mode** so you can test the whole flow with no API spend.

## Setup

```powershell
# 1. Create the virtual environment and install dependencies
cd C:\Users\testuser\Desktop\IT-helpdesk
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configure
Copy-Item .env.example .env
#   then edit .env and paste your Anthropic key (or leave it blank for mock mode)

# 3. Start Postgres
docker compose up -d
```

## Running

```powershell
# Start the API, worker, and Streamlit UI together
.\.venv\Scripts\Activate.ps1
python run_app.py
```

Open **http://localhost:8501**. The API listens on `API_PORT` (default `8000`),
and Streamlit uses that local API address automatically. To run the UI and API
separately, start `python run_api.py` and `streamlit run
app/frontend/streamlit_app.py` in separate terminals.

Then: submit a ticket on **Submit a Ticket**, and within a few seconds
(`WORKER_POLL_INTERVAL`, default 5s) it appears as `classified` on
**Ticket Queue**, where you can mark it resolved.

## Database schema

```sql
CREATE TABLE tickets (
    id            SERIAL PRIMARY KEY,
    employee_name TEXT         NOT NULL,
    issue_text    TEXT         NOT NULL,
    category      TEXT,                       -- hardware|software|network|access
    priority      TEXT,                       -- low|medium|high
    suggested_fix TEXT,
    status        TEXT NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new','classified','resolved')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## API reference

| Method | Path                          | Purpose                                  |
|--------|-------------------------------|------------------------------------------|
| GET    | `/health`                     | Liveness + whether classifier is mock    |
| POST   | `/tickets`                    | Submit a ticket (status `new`)           |
| GET    | `/tickets`                    | List all tickets                         |
| GET    | `/tickets/{id}`               | Get one ticket                           |
| POST   | `/tickets/{id}/resolve`       | Mark resolved                            |
| POST   | `/tickets/{id}/classify`      | Classify on demand (debug helper)        |
| POST   | `/worker/run`                 | Run one classification pass immediately  |

## Migration to Databricks

The backend supports two database modes:

1. **Local development** — `.env` supplies `DATABASE_URL` for local PostgreSQL.
   Keep this file local; do not upload it or commit it.
2. **Databricks Apps** — attach a Lakebase Autoscaling database resource to the
   app using the resource key `postgres`. Databricks provides `PGHOST`,
   `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSSLMODE`, and `PGAPPNAME`. The root
   `app.yaml` maps the `postgres` resource to `LAKEBASE_ENDPOINT`. The backend
   uses the Databricks SDK app identity to get a short-lived Lakebase OAuth
   credential whenever it opens a database connection; it does not use the
   local `.env` URL in this mode.

The backend creates its tables in a `helpdesk` schema in Lakebase. Deploy this
repository as a **single Databricks App**. The `run_app.py` entrypoint starts
FastAPI on the internal `API_PORT` (8001 in `app.yaml`) and Streamlit on the
public port assigned through `DATABRICKS_APP_PORT`. The Streamlit UI calls the
internal API at `HELPDESK_API_URL` if set, otherwise at
`http://127.0.0.1:<API_PORT>`. The app URL opens the ticket UI; `/docs` is not
the public API page in this setup.

The app's `postgres` resource must be attached to a Lakebase database, and its
`AGENT_APP_NAME` must identify a deployed Agent Bricks app accessible to the
Databricks App identity. The deployed `app.yaml` selects Agent Bricks
classification. For local development, `CLASSIFIER_MODE` can be `mock` (no
external model calls) or `anthropic` (requires `ANTHROPIC_API_KEY`).

After deployment, open the app's base URL, submit a test ticket, and view it
in **Ticket Queue**. If the classifier is temporarily unavailable, the ticket
stays `new` and the worker retries it on a later poll.

## Notes & trade-offs

- **Mock mode** keeps the pipeline testable with no API key. It is keyword
  based, so expect imperfect categories — it exists to prove the plumbing, not
  to judge classification quality.
- **Worker as a daemon thread** keeps the prototype to one process. For
  production, `run_worker.py` runs it standalone, and on Databricks this
   becomes a scheduled job. The classification logic is identical either way.
- **Classification failures** are logged per ticket; the ticket stays `new`
  and is retried on a later worker poll.
- **Authorization** — Databricks Apps protects access to the app, but the
  ticket API does not provide per-user roles. Anyone allowed into the app can
  view tickets and use staff actions; add application-level authorization if
  employees and IT staff need different permissions.
