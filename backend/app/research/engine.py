"""Research Engine: fetch a college's public pages, summarize them with the
configured LLM, and store a structured, source-cited ResearchSummary.

Grounding contract: the LLM sees ONLY text fetched from the college's own
site, each chunk labeled with its URL. Every claim in the output must cite
one of those URLs; anything else is dropped at parse time. Unknown fields
are the literal string "NOT_FOUND"."""

import json
import re

from sqlalchemy.orm import Session

from app.llm.base import LLMError, LLMProvider
from app.models import College, ResearchStatus, ResearchSummary
from app.research.extractor import candidate_links, html_to_text
from app.research.fetcher import FetchBlocked, FetchFailed, PoliteFetcher

RESEARCH_FIELDS = [
    "known_for",
    "major_departments",
    "recent_achievements",
    "ai_initiatives",
    "hackathons",
    "innovation_activities",
    "industry_collaborations",
    "student_strength",
    "ai_clubs",
    "entrepreneurship_cell",
    "placement_activities",
]

SYSTEM_PROMPT = """You are a meticulous research analyst. You will receive text \
extracted from a college's official website, split into chunks labeled with their \
source URL. Produce a JSON object with exactly these keys: {fields}.

Rules:
- Each key maps to {{"value": <string>, "source_url": <one of the provided URLs>}}.
- Only state facts present in the provided text. Never use outside knowledge.
- If the text does not support a field, use {{"value": "NOT_FOUND", "source_url": null}}.
- "value" must be concise (max 2 sentences per field).
- Respond with the JSON object only, no prose, no markdown fences."""

USER_PROMPT = """College: {name}, {city}, {state}

Website text by source URL:

{corpus}"""


def _build_corpus(pages: dict[str, str]) -> str:
    parts = []
    budget = 24_000  # keep the prompt within free-tier context comfortably
    for url, text in pages.items():
        chunk = f"=== SOURCE: {url} ===\n{text[: budget // len(pages)]}"
        parts.append(chunk)
    return "\n\n".join(parts)


def _parse_llm_json(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned, strict=False)  # LLMs emit literal newlines in strings


def _validate(summary: dict, allowed_urls: set[str]) -> dict:
    """Drop any claim citing a URL we never fetched — hallucination guard."""
    validated = {}
    for field in RESEARCH_FIELDS:
        entry = summary.get(field)
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("value"), str)
            and (entry.get("source_url") in allowed_urls or entry.get("value") == "NOT_FOUND")
        ):
            validated[field] = {"value": entry["value"], "source_url": entry.get("source_url")}
        else:
            validated[field] = {"value": "NOT_FOUND", "source_url": None}
    return validated


def fetch_college_pages(college: College, fetcher: PoliteFetcher, max_pages: int = 6) -> dict[str, str]:
    """Homepage + highest-value internal pages, as {url: clean_text}."""
    if not college.website:
        return {}
    pages: dict[str, str] = {}
    homepage = fetcher.get(college.website)
    pages[str(homepage.url)] = html_to_text(homepage.text)
    for url in candidate_links(homepage.text, str(homepage.url), limit=max_pages - 1):
        try:
            resp = fetcher.get(url)
        except (FetchBlocked, FetchFailed):
            continue  # skip politely; never retry a robots block
        if "text/html" in resp.headers.get("content-type", "text/html"):
            pages[str(resp.url)] = html_to_text(resp.text)
    return pages


def research_college(
    db: Session, college: College, fetcher: PoliteFetcher, llm: LLMProvider
) -> ResearchSummary:
    record = (
        db.query(ResearchSummary).filter_by(college_id=college.id).one_or_none()
        or ResearchSummary(college_id=college.id)
    )
    db.add(record)
    record.status = ResearchStatus.IN_PROGRESS
    record.llm_provider = llm.name
    db.commit()

    try:
        pages = fetch_college_pages(college, fetcher)
    except (FetchBlocked, FetchFailed) as exc:
        record.status = ResearchStatus.WEBSITE_UNAVAILABLE
        record.last_error = str(exc)
        record.retry_count += 1
        db.commit()
        return record

    if not pages:
        record.status = ResearchStatus.WEBSITE_UNAVAILABLE
        record.last_error = "No website on record or no pages fetched"
        db.commit()
        return record

    system = SYSTEM_PROMPT.format(fields=json.dumps(RESEARCH_FIELDS))
    user = USER_PROMPT.format(
        name=college.name, city=college.city, state=college.state, corpus=_build_corpus(pages)
    )
    try:
        raw = llm.complete(system, user)
        summary = _validate(_parse_llm_json(raw), allowed_urls=set(pages))
    except (LLMError, json.JSONDecodeError) as exc:
        record.status = ResearchStatus.FAILED
        record.last_error = str(exc)
        record.retry_count += 1
        db.commit()
        return record

    record.summary = summary
    record.source_urls = sorted(pages)
    record.summary_text = "\n".join(
        f"{field}: {entry['value']}" for field, entry in summary.items()
        if entry["value"] != "NOT_FOUND"
    )
    record.status = ResearchStatus.DONE
    record.last_error = None
    db.commit()
    return record
