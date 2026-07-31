# Deployment & Runbook (Phase 10)

## Stack

`docker-compose.yml` runs six services: **db** (Postgres 16), **redis**,
**api** (FastAPI, runs `alembic upgrade head` on boot), **worker** (Celery),
**beat** (scheduler), **web** (Next.js).

## First deployment

```bash
cp .env.example .env        # fill EVERY value; generate a long JWT_SECRET
docker compose up -d --build
docker compose exec api python -m app.cli create-user you@aivalytics.com --role admin
# dashboard at :3000, API docs at :8000/docs
```

DNS for email (before the first real send — see docs/SENDING.md):
SPF + DKIM + DMARC on the sending subdomain, `PUBLIC_BASE_URL` pointing at
the deployed API over HTTPS (put a reverse proxy / Caddy / nginx in front
for TLS; not included in compose on purpose — use your host's standard).

## Automated cadence (Celery beat, Asia/Kolkata)

| Time | Task | Notes |
|---|---|---|
| 01:00 | `pipeline.research_pending` (25) | crawling off business hours |
| 03:00 | `pipeline.discover_pending` (25) | contacts for researched colleges |
| 08:00 | `pipeline.draft_pending` (30) | fills the approval queue for your morning review |
| 09:00 | `pipeline.run_followups` | drafts due follow-ups → approval queue |
| 10:15–17:15 hourly | `pipeline.send_batch` | **APPROVED drafts only**, caps + suppression enforced inside |

The human loop: each morning, open the Approval Queue, review/edit/approve;
the hourly sender does the rest within warm-up caps.

## Operations

```bash
docker compose logs -f worker            # pipeline activity
docker compose exec api python -m app.cli send --dry-run    # quota + queue
docker compose exec db pg_dump -U outreach outreach > backup.sql   # backup (daily cron this)
docker compose exec api alembic upgrade head                # after pulling new code
```

Bounce intake: Brevo/Zoho dashboards list bounces; feed them via
`POST /api/replies` (classified) or suppress directly in a DB session with
`record_bounce`. A webhook endpoint is a straightforward later addition.

## Scaling & raising caps

- Warm-up: keep `DAILY_SEND_CAP=25` week 1; +25/week while bounce rate <2%.
- More crawl throughput: `docker compose up -d --scale worker=3` (per-domain
  politeness delay still applies inside each task).
- Postgres and Redis are single-node; that is correct at this scale.

## Security checklist

- [ ] strong `JWT_SECRET` and `POSTGRES_PASSWORD` in `.env` (never committed — `.gitignore` covers it)
- [ ] TLS in front of api + web
- [ ] `CORS_ORIGINS` set to the real dashboard origin only
- [ ] rotate the Groq key if it was ever shared in plaintext
- [ ] `SENDER_POSTAL_ADDRESS` filled (legally required footer)
