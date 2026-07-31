"""Contact Discovery Engine: walk a college's highest-value public pages
(placement cell, faculty, mandatory-disclosure PDFs), extract grounded
people, merge duplicates, score confidence, verify MX, and persist with
full per-field provenance."""

from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.contacts.extractor import extract_people, pdf_to_text
from app.contacts.roles import PRIORITY_ROLES, canonical_role
from app.contacts.scoring import confidence_score
from app.contacts.verify import check_email
from app.llm.base import LLMError, LLMProvider
from app.models import (
    CanonicalRole,
    College,
    Contact,
    ContactSource,
    ContactStatus,
    SourceType,
)
from app.research.extractor import candidate_links, html_to_text
from app.research.fetcher import FetchBlocked, FetchFailed, PoliteFetcher

VERIFY_THRESHOLD = 60


def _source_type_for(url: str, is_pdf: bool) -> SourceType:
    if is_pdf:
        return SourceType.MANDATORY_DISCLOSURE_PDF
    return SourceType.OFFICIAL_WEBSITE


def collect_page_texts(
    college: College, fetcher: PoliteFetcher, max_pages: int = 6
) -> dict[str, tuple[str, SourceType]]:
    """{url: (text, source_type)} from homepage, ranked subpages, and PDFs."""
    results: dict[str, tuple[str, SourceType]] = {}
    if not college.website:
        return results
    try:
        homepage = fetcher.get(college.website)
    except (FetchBlocked, FetchFailed):
        return results
    results[str(homepage.url)] = (html_to_text(homepage.text), SourceType.OFFICIAL_WEBSITE)

    for url in candidate_links(homepage.text, str(homepage.url), limit=max_pages - 1):
        try:
            resp = fetcher.get(url)
        except (FetchBlocked, FetchFailed):
            continue
        content_type = resp.headers.get("content-type", "")
        is_pdf = "pdf" in content_type or urlparse(url).path.lower().endswith(".pdf")
        try:
            text = pdf_to_text(resp.content) if is_pdf else html_to_text(resp.text)
        except Exception:
            continue  # malformed PDF etc. — skip, never fail the college
        if text.strip():
            results[str(resp.url)] = (text, _source_type_for(url, is_pdf))
    return results


def _merge_key(person: dict) -> str:
    return person["email"] or person["full_name"].lower()


def discover_contacts(
    db: Session, college: College, fetcher: PoliteFetcher, llm: LLMProvider,
    mx_lookup=None,
) -> list[Contact]:
    """Run discovery for one college; returns contacts created or updated."""
    pages = collect_page_texts(college, fetcher)
    now = datetime.now(timezone.utc)

    # extract per page, then merge on email (or name when no email)
    merged: dict[str, dict] = {}
    for url, (text, source_type) in pages.items():
        try:
            people = extract_people(text, llm)
        except LLMError:
            continue  # one bad page must not sink the college
        for person in people:
            key = _merge_key(person)
            entry = merged.setdefault(key, {**person, "citations": []})
            for field in ("email", "phone", "designation", "department"):
                if not entry.get(field) and person.get(field):
                    entry[field] = person[field]
            cited_fields = [f for f in ("email", "phone") if person.get(f)] or ["full_name"]
            for field in cited_fields:
                entry["citations"].append((field, source_type, url))

    touched: list[Contact] = []
    for entry in merged.values():
        role = canonical_role(entry.get("designation"))
        if role not in PRIORITY_ROLES:
            continue  # store only decision-makers we actually target

        contact = None
        if entry.get("email"):
            contact = (
                db.query(Contact)
                .filter_by(college_id=college.id, email=entry["email"])
                .one_or_none()
            )
        if contact is None:
            contact = (
                db.query(Contact)
                .filter(
                    Contact.college_id == college.id,
                    Contact.full_name.ilike(entry["full_name"]),
                    Contact.email.is_(None) if entry.get("email") else True,
                )
                .one_or_none()
            ) or Contact(college_id=college.id, full_name=entry["full_name"])
        db.add(contact)

        contact.designation_raw = contact.designation_raw or entry.get("designation")
        if contact.role in (None, CanonicalRole.OTHER):
            contact.role = role
        contact.department = contact.department or entry.get("department")
        contact.email = contact.email or entry.get("email")
        contact.phone_office = contact.phone_office or entry.get("phone")
        db.flush()  # need contact.id for source rows

        existing_citations = {
            (s.field_name, s.source_url) for s in contact.sources
        }
        for field, source_type, url in entry["citations"]:
            if (field, url) not in existing_citations:
                contact.sources.append(
                    ContactSource(
                        field_name=field,
                        source_type=source_type,
                        source_url=url,
                        collected_at=now,
                    )
                )

        contact.confidence = confidence_score({s.source_type for s in contact.sources})
        if contact.email:
            contact.email_mx_valid = check_email(
                contact.email, **({"mx_lookup": mx_lookup} if mx_lookup else {})
            )
        verified = (
            contact.confidence >= VERIFY_THRESHOLD
            and contact.email
            and contact.email_mx_valid is not False
        )
        if contact.status in (ContactStatus.DISCOVERED, ContactStatus.NEEDS_MANUAL_REVIEW):
            contact.status = (
                ContactStatus.VERIFIED if verified else ContactStatus.NEEDS_MANUAL_REVIEW
            )
        touched.append(contact)

    db.commit()
    return touched
