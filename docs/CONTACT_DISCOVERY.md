# Contact Discovery Engine (Phase 4)

Finds decision-makers (TPO, Principal, HODs, Deans, cell heads…) from a
college's own public pages — placement cell, faculty pages, and
AICTE Mandatory Disclosure PDFs — with full per-field provenance.

## Modules

| Module | Responsibility |
|---|---|
| `app/contacts/roles.py` | Free-text designation → canonical role (regex rules, deterministic). `PRIORITY_ROLES` defines who we actually store. |
| `app/contacts/extractor.py` | LLM proposes people from page/PDF text; grounding layer then enforces: name must appear in the text (invented people dropped), email/phone must appear verbatim (fabricated details nulled). PDFs parsed via pypdf. |
| `app/contacts/scoring.py` | Spec rubric as a pure function: official site ⇒ 95–100, multi-trusted ⇒ 80–95, enrichment+1 ⇒ 60–80, single weak ⇒ <60. |
| `app/contacts/verify.py` | Syntax + MX check (no SMTP probing — unreliable and reputation-hazardous). `None` = indeterminate, kept but flagged. |
| `app/contacts/engine.py` | Orchestrates: collect pages/PDFs → extract → merge duplicates (by email, else name) → score → verify → persist Contact + ContactSource rows. Idempotent: re-running updates, never duplicates. |

## Status assignment

- confidence ≥ 60 **and** email present **and** MX not definitively bad → `VERIFIED`
- otherwise → `NEEDS_MANUAL_REVIEW` (dashboard queue in Phase 8)
- missing email stays `NULL` — the pipeline has no mechanism to invent one

## CLI

```powershell
python -m app.cli discover-contacts --limit 5
```

Prints each college's decision-makers with role, email, confidence, status.

## Enrichment fallback (future, optional)

`ContactProvider` interface slot reserved: if a college's site yields no
TPO, an Apollo free-tier adapter can be queried — results enter at
`ENRICHMENT_API` source type, scoring 60–80 per the rubric, never higher
than site-verified data. Not built in v1 since official sites cover most
Indian colleges.
