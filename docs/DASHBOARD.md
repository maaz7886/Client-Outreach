# Dashboard (Phase 8)

Next.js 15 (App Router, TypeScript, Tailwind) in `frontend/`.

## Screens

| Route | Purpose |
|---|---|
| `/login` | JWT sign-in (token in localStorage; 401 anywhere → auto-redirect to login) |
| `/` | Dashboard: colleges/contacts/sent/open-rate/reply-rate/meetings cards, outreach funnel bars, colleges-by-state bars |
| `/colleges` | Searchable college table (name links to website) |
| `/contacts` | CRM table with status filter, confidence, "not found" for missing emails, and contextual actions (Meeting booked → Won/Lost) |
| `/drafts` | **Approval queue**: full draft preview, lint status badge with error list, subject picker, in-place body editing (saving re-lints via API), Approve (disabled while lint fails) / Reject |

## Running locally

```powershell
# API (from backend/, venv active)
uvicorn app.api.main:app --port 8000
# Web
cd frontend; npm run dev     # http://localhost:3000
# Demo data + login (maaz@aivalytics.com / demo1234):
python backend/seed_dev.py
```

`NEXT_PUBLIC_API_URL` overrides the API base (default `http://localhost:8000`).
CORS origins configurable via `CORS_ORIGINS` on the API (default localhost:3000).

## Verified in browser (2026-07-17)

Login → dashboard stats render from live API → approval queue shows 3 drafts
→ Approve click moved queue to 2 and audit-logged → contacts filter/actions
render → no console errors.
