# Email Personalization Engine (Phase 5)

## Flow

verified contact → **fact sheet** (only provenance-backed data; NOT_FOUND
fields omitted entirely) → LLM writes body + 5 subject options → **lint gate**
→ stored as `EmailDraft(DRAFT)` → human approves → `APPROVED` (immutable).

## Grounding

The model never sees anything we haven't verified: contact fields carry
ContactSource rows, research claims carry source URLs, unknown fields simply
don't appear in the prompt. Thin research ⇒ shorter honest email, not padding.

## Lint gate (`app/personalize/lint.py`)

Blocking: <5 subject options, subject >78 chars or all-caps, body outside
400–2200 chars, leaked template placeholders (`[College Name]`, `{{x}}`),
missing `%UNSUBSCRIBE_URL%` token, body never mentioning the college.
Warnings: spam-trigger phrases, excessive exclamation marks.

On lint failure the generator retries once with the errors fed back; a still-
failing draft is stored with its failing report for human attention — it can
never be approved (`approve_draft` refuses).

## Approval

`approve_draft` requires status DRAFT + passing lint, stamps approver and
time, writes an `audit_log` row, and locks the draft (regeneration returns it
untouched). The `%UNSUBSCRIBE_URL%` token is replaced with a real per-contact
link by the sender service (Phase 6).

## CLI

```powershell
python -m app.cli draft-emails --limit 10   # generate for verified contacts
python -m app.cli show-draft 3              # review subjects + body
python -m app.cli approve-draft 3           # approve (audit-logged)
```

Verified live against Groq (llama-3.3-70b) on 2026-07-17: draft generated,
lint passed, college-specific references present, no fabricated facts.
