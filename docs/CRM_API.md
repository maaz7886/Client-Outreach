# CRM & API (Phase 7)

FastAPI app: `app/api/main.py`. Run locally:

```powershell
cd backend
$env:DATABASE_URL = "sqlite:///outreach.db"   # or Postgres URL
python -m app.cli create-user you@aivalytics.com --role admin
.\.venv\Scripts\uvicorn.exe app.api.main:app --port 8000
# interactive docs at http://localhost:8000/docs
```

## Endpoints

| Route | Auth | Purpose |
|---|---|---|
| `POST /auth/login` | — | email+password → JWT |
| `GET /health` | — | liveness |
| `GET /u/{token}` | — | **unsubscribe landing** (HMAC-verified, one click, immediate suppression) |
| `GET /t/o/{msg}.gif` | — | open-tracking pixel |
| `GET /t/c/{msg}?url=` | — | click tracking + redirect (http/https only) |
| `GET /api/colleges` `?state=&q=` | any role | list + filters |
| `GET /api/colleges/{id}` | any role | detail: research summary, contacts with per-field sources |
| `GET /api/contacts` `?status=` | any role | CRM list |
| `PATCH /api/contacts/{id}` | operator | notes + manual statuses only (pipeline-owned statuses like CONTACTED are rejected — 422) |
| `GET /api/drafts` `?status=` | any role | approval queue |
| `PATCH /api/drafts/{id}` | operator | edit subject/body → **re-linted immediately** |
| `POST /api/drafts/{id}/approve` | operator | refuses failing lint (409); audit-logged |
| `POST /api/drafts/{id}/reject` | operator | reject |
| `POST /api/replies` | operator | paste an inbound reply → LLM classification → status update |
| `GET /api/stats` | any role | dashboard numbers: totals, open/click/reply rates, funnel, by-state |

Roles: `viewer` reads, `operator`/`admin` mutate (enforced, tested).

## Reply classification (`app/crm/replies.py`)

POSITIVE / NEUTRAL / NEGATIVE / AUTO_REPLY / UNSUBSCRIBE.
Safety properties:
- an "unsubscribe/remove me/stop emailing" regex fires **before** the LLM —
  an opt-out can never be misclassified by a flaky model
- LLM failure defaults to NEUTRAL (no automated action, human reviews)
- any human reply cancels the pending follow-up sequence
- AUTO_REPLY (out-of-office) records the event but keeps the sequence

## Follow-up runner (`app/followups/runner.py`)

Run daily (`python -m app.cli followups`; Celery beat wires it in Phase 10):
- due schedule + contact still CONTACTED → generates the touch-N draft, which
  enters the same human approval queue as first touches
- contact replied/bounced/unsubscribed meanwhile → schedule CANCELLED
- 4-touch DB constraint makes overshooting impossible regardless of bugs here
