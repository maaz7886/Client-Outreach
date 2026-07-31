# Testing (Phase 9)

**70 tests, 83% line coverage.** Run: `cd backend; pytest` (add
`--cov=app --cov-report=term` for coverage). Everything runs offline — no
network, no API keys — via `httpx.MockTransport`, routed fake LLMs, and a
stubbed `smtplib`.

## Suites

| File | Covers |
|---|---|
| `test_models.py` | Schema + compliance constraints (touch cap, suppression uniqueness, confidence bounds, dedup keys) |
| `test_research.py` | Polite fetcher (robots, rate limit, retries), extractor, CSV importer, research engine incl. hallucinated-citation guard |
| `test_contacts.py` | Role mapping, confidence rubric, grounded extraction (fabricated emails/people dropped), discovery engine idempotence |
| `test_personalize.py` | Lint gate, NOT_FOUND omission, retry-on-lint-failure, approval rules + immutability |
| `test_sender.py` | Suppression at send time, DB-counted caps, signed unsubscribe links, bounce/unsubscribe cascades |
| `test_api.py` | Auth + roles, CRM endpoints, draft edit→re-lint→approve flow, public unsubscribe/pixel/click, reply classification, follow-up runner |
| `test_providers.py` | Groq/Gemini HTTP adapters (success/429/500/malformed), SMTP sender (success/refused/conn-error, TLS-before-login) |
| `test_pipeline_e2e.py` | **Whole system, two journeys**: (a) import → research → discover → draft → API approval → send → open pixel → positive reply → sequence cancelled → stats correct; (b) no reply → due follow-up drafted into approval queue → 5th-touch insert rejected by the DB |

## Known coverage gaps (accepted)

- `app/cli.py` (operator shell — every function it calls is tested; the CLI
  itself was smoke-tested by hand in Phases 3–6)
- `app/contacts/verify.py` DNS paths (real resolver calls; logic paths tested
  via injected `mx_lookup`)
- `app/core/db.py` engine wiring (exercised implicitly by every dev run)
