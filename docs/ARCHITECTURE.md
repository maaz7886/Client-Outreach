# College Outreach Automation System — Architecture Design (Phase 1)

**Owner:** AIValytics
**Purpose:** Research Indian colleges, identify decision-makers from publicly available sources, generate personalized guest-lecture/workshop outreach, send compliant email campaigns, and track the full funnel in a CRM.

---

## 1. Design principles

1. **Provenance everywhere.** Every collected fact (name, email, phone, achievement) carries a `source_url`, `collected_at`, and `confidence` score. No field exists without a source. Unverifiable → `NOT_FOUND`, never a guess.
2. **Human-in-the-loop by default.** The pipeline *stages* emails; a human approves batches before sending (configurable to full-auto later, but v1 ships approval-gated).
3. **Compliance is schema, not policy text.** Unsubscribes, suppression lists, sending caps, and the 3-touch limit are enforced in the database and sender service — impossible to bypass from the UI.
4. **Modular pipeline.** Each stage (discover → research → contacts → personalize → send → track → follow-up) is an independent Celery task chain. Any stage can be re-run, skipped, or manually overridden per college.
5. **ToS-respecting acquisition.** Official websites and public documents are fetched politely (robots.txt, rate limits, identifying User-Agent). LinkedIn and similar platforms are **never scraped** — professional-network data comes only via licensed enrichment APIs (Apollo.io adapter ships first; provider interface is pluggable).

---

## 2. System overview

```
                         ┌──────────────────────────────────────────┐
                         │                Next.js UI                │
                         │  Dashboard · CRM · Approval Queue · Auth │
                         └───────────────────┬──────────────────────┘
                                             │ REST (JWT)
                         ┌───────────────────▼──────────────────────┐
                         │              FastAPI Backend             │
                         │   /colleges /contacts /campaigns /stats  │
                         └───────┬───────────────────────┬──────────┘
                                 │                       │
                        ┌────────▼────────┐     ┌────────▼────────┐
                        │   PostgreSQL    │     │      Redis      │
                        │ (SQLAlchemy 2)  │     │ queue + cache + │
                        │                 │     │  rate limiters  │
                        └────────▲────────┘     └────────▲────────┘
                                 │                       │
                  ┌──────────────┴───────────────────────┴─────────────┐
                  │                  Celery Workers                    │
                  ├────────────┬───────────┬────────────┬──────────────┤
                  │ Discovery  │ Research  │  Contact   │ Personalize  │
                  │  Engine    │  Engine   │ Discovery  │   Engine     │
                  ├────────────┴───────────┴────────────┴──────────────┤
                  │        Email Sender  ·  Tracker  ·  Follow-up      │
                  └──────┬──────────┬──────────┬──────────┬────────────┘
                         │          │          │          │
                   ┌─────▼───┐ ┌────▼────┐ ┌───▼────┐ ┌───▼─────────┐
                   │ College │ │ Search/ │ │ Apollo │ │ Gmail API / │
                   │ websites│ │ LLM API │ │  etc.  │ │ SMTP / MSFT │
                   │ (polite)│ │(Claude) │ │(enrich)│ │  (sending)  │
                   └─────────┘ └─────────┘ └────────┘ └─────────────┘
```

## 3. Module breakdown

### 3.1 `app/core` — shared infrastructure
- `config.py` — pydantic-settings; everything from env vars (API keys, sending caps, follow-up schedule days, spend limits).
- `logging.py` — structlog, JSON output, request-id correlation.
- `db.py` — async SQLAlchemy engine/session factory.
- `security.py` — JWT issue/verify, password hashing, role checks (admin / operator / viewer).

### 3.2 `app/discovery` — College Discovery Engine
Sources (all public): AICTE/UGC open datasets, NIRF ranking lists, state technical-university affiliation lists, targeted web search.
Output: `College` rows with dedup (normalized name + city fuzzy match).

### 3.3 `app/research` — Research Engine
Pipeline per college: fetch official site pages (about, departments, placement cell, news) → extract text → LLM (Claude API) produces a structured `ResearchSummary` (known-for, departments, achievements, AI initiatives, hackathons, E-cell, student strength…). Every claim in the summary stores the URL it came from. Robots.txt honored; per-domain rate limit (1 req/2s); retries with backoff; `WEBSITE_UNAVAILABLE` state → automatic retry queue.

### 3.4 `app/contacts` — Contact Discovery Engine
Priority cascade exactly as specced: official site → dept/faculty/placement pages → enrichment API (Apollo adapter behind a `ContactProvider` interface) → public govt databases/PDFs → news/conference pages.
- Role matcher: maps free-text designations to canonical roles (TPO, Principal, HOD-CS, Dean, E-Cell Head, …) via rules + LLM fallback.
- **Confidence scoring** (matches your rubric): official-site = 95–100; multi-source = 80–95; enrichment+1 source = 60–80; single weak source = <60 → flagged `NEEDS_MANUAL_REVIEW`.
- Email verification: syntax + MX check locally; optional pluggable verification API for deliverability score. Unverified ≠ invented — stored with its real confidence.
- Dedup/merge: same person across sources merged, all sources retained.

### 3.5 `app/personalize` — Email Personalization Engine
- Input: contact + role + research summary. LLM generates body + 5 subject options against a **guarded template contract**: required variables (name, college, department, achievement, city…) must be grounded in the research record — the generator receives *only* verified facts, so it cannot cite things we don't know.
- Output stored as `EmailDraft` (status `DRAFT` → `APPROVED` → `QUEUED`). Quality lint: length bounds, no placeholder leakage (`[College]`), spam-trigger word check, mandatory unsubscribe footer.

### 3.6 `app/sender` — Email Sending Service
- Provider interface with three adapters: Gmail API (OAuth), Microsoft Graph, raw SMTP.
- Redis token-bucket rate limiter (per-day and per-hour caps from config; conservative defaults for domain warm-up).
- Retry with exponential backoff; bounce detection (webhook/IMAP poll per provider); hard bounce → contact marked `BOUNCED` + suppressed.
- **Suppression list checked at send time, in the sender, always** — unsubscribed or bounced addresses cannot be emailed even if queued.
- Open/click tracking: pixel + wrapped links via a tracking endpoint (`/t/o/{id}`, `/t/c/{id}`).

### 3.7 `app/crm` — CRM
Entities and status machine below (§4). Reply detection via provider inbox polling → LLM classifies reply sentiment (positive / neutral / negative / auto-reply / unsubscribe request) → updates status, cancels pending follow-ups on any reply.

### 3.8 `app/followups` — Follow-up Automation
Celery beat scans daily: no reply after day 3 → follow-up 1; day 7 → follow-up 2; day 14 → final. Hard cap of 3 follow-up messages enforced by a DB constraint on touch count. Any reply or unsubscribe halts the sequence.

### 3.9 `frontend/` — Next.js dashboard
Pages: Dashboard (funnel, rates, map by state), Colleges, Contacts, Approval Queue (review/edit/approve drafts in bulk), Campaign settings, Manual-review queue. Auth via JWT against the API.

## 4. Data model (summary — full DDL in Phase 2)

Core tables: `colleges`, `contacts`, `contact_sources` (1-N provenance), `research_summaries`, `email_drafts`, `email_messages` (sent instances + provider ids), `email_events` (open/click/bounce/reply), `followup_schedules`, `suppression_list`, `users`, `audit_log`.

Contact status machine:
`DISCOVERED → VERIFIED | NEEDS_MANUAL_REVIEW → QUEUED → CONTACTED → (OPENED) → REPLIED_POSITIVE | REPLIED_NEGATIVE | NO_REPLY_EXHAUSTED | BOUNCED | UNSUBSCRIBED → MEETING_SCHEDULED → WON/LOST`

## 5. Compliance design (India-first)

- **DPDP Act 2023:** we process publicly available professional data for legitimate B2B purposes; we honor erasure requests (unsubscribe = suppression + optional data deletion), and store nothing sensitive.
- Every email: real sender identity, physical address, one-click unsubscribe link, honest subject lines.
- Configurable global daily send cap; 3-touch max; per-domain politeness on scraping; identifying User-Agent with contact email.
- `audit_log` records who approved which batch and when.

## 6. Tech stack (as specced)

| Layer | Choice |
|---|---|
| API | Python 3.12, FastAPI, Pydantic v2 |
| DB | PostgreSQL 16, SQLAlchemy 2 (async), Alembic |
| Jobs | Celery + Redis (broker & result backend) |
| LLM | Pluggable `LLMProvider` — free-tier adapter first (Groq / Gemini free tier), Claude adapter optional |
| Enrichment | Primary: official sites + AICTE Mandatory Disclosure PDFs + NIRF/AICTE open data (free). Optional fallback: Apollo.io free tier behind `ContactProvider` interface |
| Frontend | Next.js 15 (App Router), Tailwind, shadcn/ui, Recharts |
| Auth | JWT (access+refresh), bcrypt |
| Deploy | Docker Compose (api, worker, beat, db, redis, web) |
| Tests | pytest + pytest-asyncio, httpx test client, factory-boy |

## 7. Phase plan

| Phase | Deliverable | Gate |
|---|---|---|
| 1 | This document | ✅ awaiting approval |
| 2 | Alembic migrations + SQLAlchemy models + ERD | approval |
| 3 | Research Engine + polite fetcher + LLM summarizer | approval |
| 4 | Contact Discovery + confidence scoring + provider interface | approval |
| 5 | Personalization Engine + draft lint + approval queue API | approval |
| 6 | Sender service (Gmail/SMTP/Graph) + tracking + suppression | approval |
| 7 | CRM endpoints + reply classification + follow-up beat | approval |
| 8 | Next.js dashboard | approval |
| 9 | Test hardening + load test on pipeline | approval |
| 10 | Dockerization + deploy docs + runbook | done |

## 8. Cost posture (decided): zero-paid-API v1

1. **Contact discovery:** official websites + AICTE Mandatory Disclosure PDFs (list Principal/Director by mandate) + placement-cell pages + NIRF/AICTE open datasets. Apollo free tier as optional fallback only. No paid enrichment.
2. **Email verification:** syntax + MX check only; bounce-detection loop suppresses bad addresses after first send. No paid verification API.
3. **LLM:** free-tier provider (Groq or Gemini) via the `LLMProvider` interface; Claude adapter available if quality upgrade wanted later.
4. **Sending:** user's custom domain via free-tier SMTP relay (Brevo 300/day free, or Zoho Mail free custom-domain SMTP). Requirements: SPF + DKIM + DMARC DNS records before first send; warm-up ramp (start 20–30/day, ramp over 2–3 weeks) enforced by the sender's rate limiter; recommended: send from a dedicated subdomain (e.g. `outreach.<domain>`) to insulate the root domain's reputation.
5. **Sending remains approval-gated in v1.**
