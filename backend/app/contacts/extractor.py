"""Grounded people-extraction from page/PDF text.

Same anti-fabrication contract as the research engine: the LLM proposes
structured people, but every email and phone must appear VERBATIM in the
source text or it is nulled, and the person's name must appear in the text
or the whole row is dropped. A hallucinated contact cannot survive this."""

import io
import json
import re

from pypdf import PdfReader

from app.llm.base import LLMError, LLMProvider

EMAIL_IN_TEXT_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Indian formats: +91-XXXXXXXXXX, 0XX-XXXXXXX, 10-digit mobiles, spaced groups
PHONE_IN_TEXT_RE = re.compile(r"(?:\+91[\s\-]?)?(?:\d[\s\-]?){9,12}\d")

SYSTEM_PROMPT = """You extract people from text taken from an Indian college's \
official website or public PDF. Return a JSON array; each element:
{"full_name": str, "designation": str|null, "department": str|null,
 "email": str|null, "phone": str|null}

Rules:
- Only include people whose NAME appears in the text.
- email/phone must be copied character-for-character from the text; use null if absent.
- Include ONLY people in administrative or academic leadership roles \
(principal, director, dean, HOD, placement/training officers, cell heads). Skip students.
- Respond with the JSON array only."""


def pdf_to_text(content: bytes, max_pages: int = 30, max_chars: int = 40_000) -> str:
    reader = PdfReader(io.BytesIO(content))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)[:max_chars]


def _normalize_phone(raw: str) -> str:
    return re.sub(r"[\s\-]", "", raw)


def _parse(raw: str) -> list:
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned, strict=False)  # LLMs emit literal newlines in strings
    return data if isinstance(data, list) else []


def extract_people(text: str, llm: LLMProvider) -> list[dict]:
    """Returns grounded person dicts; may raise LLMError for the caller to handle."""
    if not text.strip():
        return []
    raw = llm.complete(SYSTEM_PROMPT, text[:24_000], max_tokens=3000)
    try:
        proposed = _parse(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Contact extraction returned invalid JSON: {exc}") from exc

    text_lower = text.lower()
    emails_in_text = {e.lower() for e in EMAIL_IN_TEXT_RE.findall(text)}
    phones_in_text = {_normalize_phone(p) for p in PHONE_IN_TEXT_RE.findall(text)}

    grounded = []
    for person in proposed:
        if not isinstance(person, dict):
            continue
        name = (person.get("full_name") or "").strip()
        # name must literally appear -> invented people are dropped
        if len(name) < 3 or name.lower() not in text_lower:
            continue
        email = (person.get("email") or "").strip().rstrip(".,;") or None
        if email and email.lower() not in emails_in_text:
            email = None
        phone = (person.get("phone") or "").strip() or None
        if phone and _normalize_phone(phone) not in phones_in_text:
            phone = None
        grounded.append(
            {
                "full_name": name,
                "designation": (person.get("designation") or "").strip() or None,
                "department": (person.get("department") or "").strip() or None,
                "email": email.lower() if email else None,
                "phone": phone,
            }
        )
    return grounded
