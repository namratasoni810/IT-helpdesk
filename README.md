# IT Helpdesk Assistant — Local Prototype

Employee ticket submission → automatic LLM classification → IT staff resolution queue.

Built to migrate cleanly to Databricks: **Lakebase** (DB), **Databricks Apps** (hosting),
**Agent Bricks** (classification). Nothing in the codebase is Databricks-specific yet —
the migration points are called out below.

## Architecture

```
┌──────────────┐     HTTP     ┌───────────────┐   psycopg2   ┌──────────────┐
│  Streamlit   │ ───────────► │   FastAPI     │ ───────────► │   Postgres   │
│  (frontend)  │              │   (backend)   │              │  (in Docker) │
└──────────────┘              └───┬───────────┘              └──────────────┘
                                  │
                          ┌───────▼────────┐
                          │  Worker thread │ ──► classifier.py ──► Anthropic API
                          │  (polls 'new') │         (swap point for Agent Bricks)
                          └────────────────┘
```

## Project layout

```
application/
├── docker-compose.yml          # Postgres 16 (stands in for Lakebase)
├── requirements.txt
├── .env.example                # copy to .env
├── run_api.py                  # starts FastAPI (+ background worker thread)
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
cd C:\Users\testuser\Desktop\application
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
# Terminal 1 — backend (also starts the classification worker thread)
.\.venv\Scripts\Activate.ps1
python run_api.py
#   API at  http://localhost:8000   docs at  http://localhost:8000/docs

# Terminal 2 — UI
.\.venv\Scripts\Activate.ps1
streamlit run app/frontend/streamlit_app.py
#   UI at  http://localhost:8501
```

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

The prototype is structured so migration touches a small surface:

1. **Lakebase (database)** — change `DATABASE_URL` in `.env` to the Lakebase
   endpoint. `app/db.py` uses only standard Postgres SQL via `psycopg2`, so no
   query changes are needed. If Lakebase prefers a pooled/managed connection,
   only `init_pool()` changes.
2. **Databricks Apps (hosting)** — `app/main.py` is a standard FastAPI app;
   add an `app.yaml` and deploy as a Databricks App. The Streamlit frontend can
   deploy as a second app or be replaced by the App's built-in UI.
3. **Agent Bricks (classification)** — replace the body of
   `classify_ticket()` in `app/classifier.py` with the Agent Bricks agent call.
   Keep the `Classification` dataclass and function signature intact and
   nothing else needs to change: `worker.py` and `main.py` only consume that
   contract.

## Notes & trade-offs

- **Mock mode** keeps the pipeline testable with no API key. It is keyword
  based, so expect imperfect categories — it exists to prove the plumbing, not
  to judge classification quality.
- **Worker as a daemon thread** keeps the prototype to one process. For
  production, `run_worker.py` runs it standalone, and on Databricks this
   becomes a scheduled job. The classification logic is identical either way.
- **Classification failures are swallowed** by `classify_ticket_safe()` so a
  transient API error never kills the worker; the ticket stays `new` and is
  retried on the next poll.
- **No auth** — this is a local prototype. Add authentication before deploying.
