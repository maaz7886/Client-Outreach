# Database Design (Phase 2)

PostgreSQL 16 in production, SQLite for unit tests (all types/constraints are portable).
Migrations: Alembic (`backend/alembic/`). Initial revision: `a3637d12c61b`.

## ERD

```mermaid
erDiagram
    COLLEGES ||--o{ CONTACTS : has
    COLLEGES ||--o| RESEARCH_SUMMARIES : "researched by"
    CONTACTS ||--o{ CONTACT_SOURCES : "cited by"
    CONTACTS ||--o{ EMAIL_DRAFTS : receives
    CONTACTS ||--o{ FOLLOWUP_SCHEDULES : "scheduled for"
    EMAIL_DRAFTS ||--o{ EMAIL_MESSAGES : "sent as"
    EMAIL_MESSAGES ||--o{ EMAIL_EVENTS : generates
    USERS ||--o{ EMAIL_DRAFTS : approves
    USERS ||--o{ AUDIT_LOG : acts

    COLLEGES {
        int id PK
        string name
        string normalized_name UK "dedup key with city"
        string city
        string state
        string website
        string naac_grade
        int nirf_rank
        string affiliation
        enum college_type
        int student_strength
    }
    CONTACTS {
        int id PK
        int college_id FK
        string full_name
        enum role "TPO, PRINCIPAL, HOD, DEAN..."
        string email "NULL = NOT_FOUND, never guessed"
        int confidence "0-100, CHECK enforced"
        enum status "state machine"
        datetime last_contact_at
        datetime next_followup_at
    }
    CONTACT_SOURCES {
        int id PK
        int contact_id FK
        string field_name "which field this cites"
        enum source_type
        string source_url
        text excerpt
    }
    RESEARCH_SUMMARIES {
        int id PK
        int college_id FK "unique"
        enum status
        json summary "every claim carries source_url"
        json source_urls
    }
    EMAIL_DRAFTS {
        int id PK
        int contact_id FK
        int touch_number "CHECK 1-4: hard 3-followup cap"
        json subject_options "5 generated"
        text body_text
        json lint_report
        enum status
        int approved_by_id FK
    }
    EMAIL_MESSAGES {
        int id PK
        int draft_id FK
        string provider
        string provider_message_id
        enum status
    }
    EMAIL_EVENTS {
        int id PK
        int message_id FK
        enum event_type "OPEN CLICK BOUNCE REPLY UNSUBSCRIBE"
        json meta
    }
    FOLLOWUP_SCHEDULES {
        int id PK
        int contact_id FK
        int touch_number "CHECK 2-4"
        datetime scheduled_for
        enum status
    }
    SUPPRESSION_LIST {
        int id PK
        string email UK
        enum reason "UNSUBSCRIBED HARD_BOUNCE COMPLAINT MANUAL"
    }
    USERS {
        int id PK
        string email UK
        enum role "ADMIN OPERATOR VIEWER"
    }
    AUDIT_LOG {
        int id PK
        int user_id FK
        string action
        json detail
    }
```

## Compliance encoded as constraints

| Rule | Enforcement |
|---|---|
| Max 4 emails per contact (1 initial + 3 follow-ups) | `CHECK (touch_number BETWEEN 1 AND 4)` + `UNIQUE (contact_id, touch_number)` on `email_drafts` |
| Follow-ups only touches 2–4 | `CHECK (touch_number BETWEEN 2 AND 4)` on `followup_schedules` |
| One suppression entry per address; sender checks it at send time | `UNIQUE (email)` on `suppression_list` |
| Confidence must be a real 0–100 score | `CHECK (confidence BETWEEN 0 AND 100)` |
| No duplicate colleges from fuzzy discovery | `UNIQUE (normalized_name, city)` |
| No duplicate contact per college mailbox | `UNIQUE (college_id, email)` |
| Provenance mandatory | `contact_sources.source_url` NOT NULL; research JSON stores per-claim URLs |

## Contact status machine

`DISCOVERED → VERIFIED | NEEDS_MANUAL_REVIEW → QUEUED → CONTACTED → REPLIED_POSITIVE | REPLIED_NEGATIVE | NO_REPLY_EXHAUSTED | BOUNCED | UNSUBSCRIBED`, then `REPLIED_POSITIVE → MEETING_SCHEDULED → WON | LOST`.

Transitions happen only in service-layer functions (Phase 7) that also write `audit_log`.

## Running it

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest                    # 6 schema/constraint tests
alembic upgrade head      # applies to DATABASE_URL (Postgres in prod)
```
