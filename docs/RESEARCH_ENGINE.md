# Research Engine (Phase 3)

## Components

| Module | Responsibility |
|---|---|
| `app/llm/` | `LLMProvider` protocol + Groq and Gemini free-tier adapters. Provider chosen by `LLM_PROVIDER` env var; adding Claude later = one new adapter class. |
| `app/research/fetcher.py` | `PoliteFetcher` — the ONLY door to college websites: robots.txt honored (a disallow raises `FetchBlocked`, never worked around), per-domain delay (`CRAWL_DELAY_SECONDS`, default 2s), identifying User-Agent, retries with exponential backoff on 429/5xx, 2 MB response cap. |
| `app/research/extractor.py` | HTML → clean text; homepage → ranked same-site candidate links (placement/disclosure pages first). |
| `app/research/engine.py` | Orchestrates fetch → summarize → store. |
| `app/discovery/importer.py` | CSV importer for AICTE/NIRF open datasets — flexible header matching, normalization, dedup. |
| `app/cli.py` | `init-db`, `import-csv <file>`, `research --limit N`. |

## Grounding guarantees (anti-hallucination)

1. The LLM receives **only** text fetched from the college's own site, chunked and labeled by source URL.
2. Output schema forces every claim to cite one of those URLs.
3. `_validate()` drops any claim whose `source_url` is not in the fetched set — a fabricated citation becomes `NOT_FOUND` before it ever reaches the database. This is unit-tested (`test_research_college_stores_grounded_summary`).
4. Unknown = literal `NOT_FOUND`, stored as such.

## Failure handling

| Situation | Result |
|---|---|
| Homepage unreachable / robots-blocked | `WEBSITE_UNAVAILABLE`, `retry_count` incremented — retryable later |
| Sub-page fails | Skipped silently; research continues with remaining pages |
| LLM error or bad JSON | `FAILED` + `last_error`, retryable |
| No website on record | `WEBSITE_UNAVAILABLE` with explanatory error |

## Getting data in

AICTE approved-institution lists: https://facilities.aicte-india.org/dashboard/pages/dashboardaicte.php (downloadable), NIRF rankings: https://www.nirfindia.org (Excel per category). Download the CSV/Excel for your target states, save as CSV, then:

```powershell
python -m app.cli import-csv .\aicte_maharashtra.csv
```

Then set `LLM_PROVIDER=groq` and `LLM_API_KEY=...` in `backend/.env` and run:

```powershell
python -m app.cli research --limit 5
```
