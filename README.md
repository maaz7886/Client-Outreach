# AIValytics College Outreach System

> AI-powered, compliance-first outreach automation for booking AI guest lectures
> and workshops at Indian colleges.  
> **Zero paid APIs** — public data, free-tier LLMs (Groq), free SMTP relay.

---

## What does this system do?

This system automates the full lifecycle of college outreach in 6 stages:

```
Import Colleges → Research → Discover Contacts → Generate Drafts → Human Approval → Send
                                                                              ↓
                                                         Track Opens / Replies / Follow-ups
```

### What you get as output

| Stage | Output |
|---|---|
| Import | College records in DB (name, city, state, website, type) |
| Research | AI summary per college — achievements, departments, initiatives, AI programs |
| Contacts | Decision-maker list — TPO, Principal, HOD-CS, Dean, E-Cell Head — with emails, confidence scores, source URLs |
| Drafts | Personalized emails (body + 5 subject options) grounded in verified facts |
| Approval | Human-reviewed, edited, approved queue before anything is sent |
| Send | Sent emails with open/click/bounce/reply tracking |
| Follow-ups | Automated day-3, day-7, day-14 follow-ups (hard 4-touch cap) |
| Dashboard | Real-time funnel — colleges → contacts → contacted → replied → meetings → won |

---

## Setup from scratch

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) (running)
- [Node.js 18+](https://nodejs.org) (for local frontend dev)
- A free [Groq API key](https://console.groq.com) (for LLM features)
- A free [Brevo](https://brevo.com) or Zoho SMTP account (for sending emails)

### Step 1 — Clone and configure

```bash
git clone <your-repo-url>
cd college-outreach-system

# Copy the example env file
copy .env.example .env
```

Open `.env` and fill in:

```env
POSTGRES_PASSWORD=pick-a-strong-password
JWT_SECRET=pick-a-64-char-random-string

LLM_PROVIDER=groq
LLM_API_KEY=gsk_your_groq_key_here

SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USERNAME=your-brevo-username
SMTP_PASSWORD=your-brevo-password
SENDER_NAME=Your Name
SENDER_EMAIL=outreach@yourdomain.com
SENDER_POSTAL_ADDRESS=Your Full Address (legally required)

PUBLIC_BASE_URL=http://localhost:8000
PUBLIC_API_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:3000
```

### Step 2 — Start the backend

```bash
docker compose up -d db redis api worker beat
```

This starts:
- PostgreSQL database
- Redis (job queue)
- FastAPI backend (port 8000)
- Celery worker (runs pipeline tasks)
- Celery beat (scheduler for follow-ups)

Wait ~30 seconds for everything to become healthy.

### Step 3 — Create your admin account

```bash
docker compose exec api python -m app.cli create-user admin@youremail.com --role admin --password YourPassword123
```

### Step 4 — Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at **http://localhost:3000**

> **Single command shortcut** (from root folder after `npm install` at root):
> ```bash
> npm run dev
> ```
> This starts Docker backend services + Next.js frontend together.

---

## Login

Open **http://localhost:3000/login**

- **Email:** the email you used in Step 3
- **Password:** the password you used in Step 3

Default dev credentials: `admin@aivalytics.com` / `Admin1234`

---

## Running the pipeline (UI)

Go to **http://localhost:3000/pipeline** — you'll see the full 5-step pipeline with buttons, descriptions, and expected outputs.

### Step 1 — Import Colleges

Click **Run Step 1** and upload a CSV file.

CSV format:
```csv
name,city,state,website,type
IIT Bombay,Mumbai,Maharashtra,https://www.iitb.ac.in,IIT
VIT Vellore,Vellore,Tamil Nadu,https://vit.ac.in,Deemed
Pune University,Pune,Maharashtra,https://unipune.ac.in,State University
```

**Output:** Colleges added to database, duplicates skipped.

### Step 2 — Research Colleges

Click **Run Step 2**. The system will:
- Crawl each college's website (About, Departments, Placement, News pages)
- Respect robots.txt and rate limits (1 request per 2 seconds)
- Use Groq LLM to extract structured summaries
- Store every claim with its source URL

**Output:** Research summaries saved with status DONE / FAILED / UNAVAILABLE.

### Step 3 — Discover Contacts

Click **Run Step 3**. The system finds:
- TPO (Training & Placement Officer)
- Principal / Director
- HOD Computer Science
- Dean Academics
- E-Cell Head

Sources: official site pages → AICTE Mandatory Disclosure PDFs → public databases → news pages.
Each contact gets a **confidence score** (0-100):
- 95-100: found on official site
- 80-95: found in multiple sources
- 60-80: found via enrichment + 1 source
- Below 60: flagged as NEEDS_MANUAL_REVIEW

**Output:** Contacts with emails, roles, confidence scores, source URLs.

### Step 4 — Generate Email Drafts

Click **Run Step 4**. For each VERIFIED contact, the LLM generates:
- A personalized email body referencing the college's actual achievements
- 5 subject line options
- Automatic lint checks (length, spam words, no placeholder leakage, unsubscribe footer)

**Output:** Drafts appear in the **Approval Queue**.

### Step 5 — Review and Approve (Approval Queue)

Go to **http://localhost:3000/drafts**

For each draft:
- Read the personalized email
- Edit subject or body if needed
- Click **Approve** (lint must pass) or **Reject**

Only approved drafts can be sent.

### Step 6 — Send Emails

Click **Run Step 5** on the Pipeline page.

Sending respects:
- Daily cap: 25 emails (increase gradually as your domain warms up)
- Hourly cap: 10 emails
- Suppression list: unsubscribed/bounced contacts are never emailed again
- Open tracking pixel + click-wrapped links

**Output:** Emails sent, opens/clicks/replies tracked.

---

## Running the pipeline (CLI)

You can also run each step from the terminal:

```bash
# Import colleges from CSV
docker compose exec api python -m app.cli import-csv colleges.csv

# Research (fetch websites + AI summaries)
docker compose exec api python -m app.cli research --limit 10

# Discover contacts (TPO, Principal, HODs)
docker compose exec api python -m app.cli discover-contacts --limit 10

# Generate email drafts
docker compose exec api python -m app.cli draft-emails --limit 10

# Preview what would be sent (no actual sending)
docker compose exec api python -m app.cli send --dry-run

# Actually send approved drafts
docker compose exec api python -m app.cli send

# Run due follow-ups
docker compose exec api python -m app.cli followups

# View a specific draft
docker compose exec api python -m app.cli show-draft 1

# Approve a draft by ID
docker compose exec api python -m app.cli approve-draft 1
```

---

## Dashboard

Go to **http://localhost:3000** to see:

- Total colleges, contacts, emails sent
- Open rate, reply rate, meetings scheduled
- Outreach funnel (Discovered → Verified → Contacted → Replied → Won)
- Colleges by state (bar chart)
- Click rate and positive reply count

---

## API Documentation

Interactive Swagger docs at **http://localhost:8000/docs**

Key endpoints:
- `POST /auth/login` — get JWT token
- `GET /api/stats` — dashboard numbers
- `GET /api/colleges` — list colleges
- `GET /api/contacts` — list contacts
- `GET /api/drafts` — list drafts
- `POST /api/drafts/{id}/approve` — approve a draft
- `POST /api/drafts/{id}/reject` — reject a draft

---

## Email warm-up schedule

| Week | Daily cap | Notes |
|---|---|---|
| 1 | 25 | Default in `.env` |
| 2 | 50 | Set `DAILY_SEND_CAP=50` |
| 3 | 75 | Set `DAILY_SEND_CAP=75` |
| 4+ | 100+ | Increase if bounce rate < 2% |

Monitor bounce rate in your Brevo/Zoho dashboard. Keep it below 2%.

---

## Compliance built-in

- Every email includes a real sender name, physical address, and one-click unsubscribe link
- Unsubscribed contacts go into a suppression list and can never be emailed again
- Maximum 4 emails per contact (DB constraint — cannot be bypassed)
- Nothing sends without human approval
- All crawling respects robots.txt with a 1 req/2s rate limit
- User-Agent identifies the bot with contact email

---

## Stopping the system

```bash
# Stop backend
docker compose stop

# Stop frontend
# Press Ctrl+C in the terminal running npm run dev
```

---

## Production Deployment (Cloudflare Tunnel + Vercel)

This setup keeps **all backend services running locally** and exposes only the
FastAPI API via Cloudflare Tunnel. The Next.js frontend is deployed to Vercel.

```
Vercel (frontend)
    ↓ HTTPS
Cloudflare Edge  ←──────────────────── cloudflared (Windows service)
                                              ↓
                                    localhost:8000 (Docker api container)
                                              ↓
                            db / redis / worker / beat  (private Docker network)
```

### One-time setup (Administrator PowerShell)

```powershell
# 1. Run the automated setup script
cd D:\college-outreach-system
.\scripts\setup-cloudflare-tunnel.ps1 -TunnelName "college-outreach" -Hostname "api.yourdomain.com"

# 2. Generate a strong JWT secret
.\scripts\generate-jwt-secret.ps1

# 3. Update .env with your real values
#    PUBLIC_BASE_URL=https://api.yourdomain.com
#    PUBLIC_API_URL=https://api.yourdomain.com
#    CORS_ORIGINS=https://your-app.vercel.app,http://localhost:3000
#    JWT_SECRET=<output from step 2>
notepad .env

# 4. Rebuild containers to pick up .env changes
docker compose up -d --build db redis api worker beat

# 5. Set NEXT_PUBLIC_API_URL in Vercel Dashboard
#    → Your Project → Settings → Environment Variables
#    → NEXT_PUBLIC_API_URL = https://api.yourdomain.com
#    Then redeploy the frontend.

# 6. Verify everything
.\scripts\verify.ps1 -TunnelHostname "api.yourdomain.com" -VercelOrigin "https://your-app.vercel.app"
```

### After every reboot

The Task Scheduler job and cloudflared Windows service start automatically.
To start manually:

```powershell
.\scripts\start-backend.ps1
```

### Security boundaries

| Service | Publicly accessible? | How |
|---|---|---|
| FastAPI API (8000) | ✅ Via tunnel only | Bound to `127.0.0.1:8000`, tunnel routes `api.yourdomain.com` |
| PostgreSQL (5432) | ❌ Never | No `ports:` in docker-compose |
| Redis (6379) | ❌ Never | No `ports:` in docker-compose |
| Celery Worker | ❌ Never | No ports exposed |
| Celery Beat | ❌ Never | No ports exposed |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ERR_CONNECTION_REFUSED` on port 8000 | Run `docker compose up -d api` |
| 401 Unauthorized | Create user: `docker compose exec api python -m app.cli create-user email@x.com --password pass` |
| Port 3000 in use | `taskkill /PID <pid> /F` (find PID with `netstat -ano \| findstr :3000`) |
| LLM errors | Check your `LLM_API_KEY` in `.env` is valid at console.groq.com |
| No drafts generated | Run steps in order: import → research → contacts → drafts |
| Emails not sending | Fill in SMTP settings in `.env` and ensure SPF/DKIM DNS records are set |
| CORS errors from Vercel | Check `CORS_ORIGINS` in `.env` contains your exact Vercel URL |
| Tunnel offline (502) | `Restart-Service cloudflared` — check logs with `Get-EventLog -LogName Application -Source cloudflared -Newest 20` |
| Tunnel never connects | Run `.\scripts\verify.ps1` — confirm `http://localhost:8000/health` works locally first |

---

rebuild image after doing any changes in python code : docker compose up -d --build api


*Built by AIValytics — BUILD · LEARN · DEPLOY*
