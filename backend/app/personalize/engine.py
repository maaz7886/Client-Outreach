"""Email Personalization Engine.

Grounding contract, same as everywhere else in this system: the LLM writes
from a fact sheet containing ONLY verified data — contact fields with
provenance and research-summary claims that carry a source URL. NOT_FOUND
fields are omitted from the prompt entirely, so the model cannot reference
what we don't know. The lint gate then blocks structural failures."""

import json
import re

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.base import LLMError, LLMProvider
from app.models import (
    Contact,
    ContactStatus,
    DraftStatus,
    EmailDraft,
    ResearchSummary,
)
from app.personalize.lint import UNSUBSCRIBE_TOKEN, lint_draft

SYSTEM_PROMPT = """You write short, respectful B2B outreach emails from an AI \
training company to Indian college administrators, proposing a free guest \
lecture / workshop on Artificial Intelligence for students.

You will receive a FACT SHEET. Use ONLY facts from it — never invent \
achievements, numbers, names, or initiatives. If the fact sheet is thin, write \
a shorter, simpler email rather than padding it.

The email must:
- open with a specific, genuine reference to THIS college from the fact sheet
- explain in one or two sentences why AI literacy matters for their students now
- say what students gain: a practical, industry-focused, interactive session
- close with a soft call-to-action asking if they'd be open to a short call \
or to host a session (no pressure, no deadlines)
- tone: professional, warm, concise. No hype words, no exclamation marks, \
no flattery. 120-180 words.
- sign off with the sender block exactly as given in the fact sheet
- end the body with this literal line: Unsubscribe: %UNSUBSCRIBE_URL%

Return JSON only:
{"subject_options": [5 distinct subject lines, each under 70 chars,
 at least 3 mentioning the college or city by name],
 "body_text": "the plain-text email"}"""


def build_fact_sheet(contact: Contact, research: ResearchSummary | None) -> str:
    settings = get_settings()
    college = contact.college
    lines = [
        f"RECIPIENT: {contact.full_name}",
        f"DESIGNATION: {contact.designation_raw or contact.role.value}",
        f"DEPARTMENT: {contact.department}" if contact.department else None,
        f"COLLEGE: {college.name}",
        f"CITY/STATE: {college.city}, {college.state}",
        f"NAAC GRADE: {college.naac_grade}" if college.naac_grade else None,
        f"NIRF RANK: {college.nirf_rank}" if college.nirf_rank else None,
        f"STUDENT STRENGTH: {college.student_strength}" if college.student_strength else None,
    ]
    if research and research.summary:
        for field, entry in research.summary.items():
            if entry.get("value") and entry["value"] != "NOT_FOUND":
                label = field.replace("_", " ").upper()
                lines.append(f"{label}: {entry['value']}")
    lines += [
        "",
        "SENDER BLOCK:",
        settings.sender_name or "AIValytics Team",
        "AIValytics",
        settings.sender_email or "",
        settings.sender_postal_address or "",
    ]
    return "\n".join(line for line in lines if line is not None)


def _parse(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned, strict=False)  # LLMs emit literal newlines in strings
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def generate_draft(
    db: Session, contact: Contact, llm: LLMProvider, *, touch_number: int = 1,
    max_attempts: int = 2,
) -> EmailDraft:
    """Create (or refresh) the draft for a contact/touch. Lint failures are
    retried once with the errors fed back, then stored as DRAFT with a failing
    lint_report for human attention — never silently approved."""
    if contact.status not in (ContactStatus.VERIFIED, ContactStatus.CONTACTED):
        raise ValueError(f"contact {contact.id} is {contact.status.value}, not draftable")

    research = (
        db.query(ResearchSummary).filter_by(college_id=contact.college_id).one_or_none()
    )
    fact_sheet = build_fact_sheet(contact, research)

    draft = (
        db.query(EmailDraft)
        .filter_by(contact_id=contact.id, touch_number=touch_number)
        .one_or_none()
    )
    if draft and draft.status not in (DraftStatus.DRAFT, DraftStatus.REJECTED):
        return draft  # approved/queued/sent drafts are immutable
    if draft is None:
        draft = EmailDraft(contact_id=contact.id, touch_number=touch_number)
        db.add(draft)

    system_prompt = SYSTEM_PROMPT
    if touch_number > 1:
        system_prompt += (
            f"\n\nThis is polite follow-up #{touch_number - 1} to an earlier email that "
            "received no reply. Reference the earlier note briefly, add one new specific "
            "point of value from the fact sheet if available, keep it to 90-130 words, "
            "and make it easy to say no."
        )
    user_prompt = f"FACT SHEET:\n{fact_sheet}"
    report = {"ok": False, "errors": ["not generated"], "warnings": []}
    for _ in range(max_attempts):
        raw = llm.complete(system_prompt, user_prompt, max_tokens=1500)
        try:
            data = _parse(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            report = {"ok": False, "errors": [f"invalid JSON from LLM: {exc}"], "warnings": []}
            continue
        subjects = [str(s) for s in data.get("subject_options", [])][:5]
        body = str(data.get("body_text", ""))
        if UNSUBSCRIBE_TOKEN not in body:
            body = body.rstrip() + f"\n\nUnsubscribe: {UNSUBSCRIBE_TOKEN}"
        report = lint_draft(subjects, body, contact.college.name)
        draft.subject_options = subjects
        draft.chosen_subject = subjects[0] if subjects else None
        draft.body_text = body
        if report["ok"]:
            break
        user_prompt = (
            f"FACT SHEET:\n{fact_sheet}\n\nYour previous draft failed these checks, "
            f"fix them: {report['errors']}"
        )

    draft.lint_report = report
    draft.status = DraftStatus.DRAFT
    db.commit()
    return draft


def approve_draft(db: Session, draft: EmailDraft, user_id: int | None) -> EmailDraft:
    from app.models import AuditLog

    if draft.status is not DraftStatus.DRAFT:
        raise ValueError(f"draft {draft.id} is {draft.status.value}, not approvable")
    if not draft.lint_report or not draft.lint_report.get("ok"):
        raise ValueError(f"draft {draft.id} fails lint: {draft.lint_report}")
    draft.status = DraftStatus.APPROVED
    from app.models.base import utcnow

    draft.approved_by_id = user_id
    draft.approved_at = utcnow()
    db.add(AuditLog(user_id=user_id, action="draft.approve",
                    entity_type="email_draft", entity_id=draft.id,
                    detail={"contact_id": draft.contact_id, "touch": draft.touch_number}))
    db.commit()
    return draft
