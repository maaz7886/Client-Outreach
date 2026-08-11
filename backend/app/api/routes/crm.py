"""Authenticated CRM endpoints: colleges, contacts, drafts, replies, stats."""

import csv
import io
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_operator
from app.core.config import get_settings
from app.core.db import get_db
from app.llm.providers import get_provider
from app.models import (
    College,
    Contact,
    ContactStatus,
    DraftStatus,
    EmailDraft,
    EmailEvent,
    EmailEventType,
    EmailMessage,
    MessageStatus,
    User,
)
from app.models.base import CanonicalRole, CollegeType, SourceType
from app.models.contact import ContactSource
from app.personalize.engine import approve_draft, generate_draft
from app.personalize.lint import lint_draft

router = APIRouter(tags=["crm"], dependencies=[Depends(get_current_user)])


def _llm():
    s = get_settings()
    return get_provider(s.llm_provider, s.llm_api_key, s.llm_model)


# ---------- colleges ----------

@router.get("/colleges")
def list_colleges(state: str | None = None, q: str | None = None,
                  limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    query = db.query(College)
    if state:
        query = query.filter(College.state.ilike(state))
    if q:
        query = query.filter(College.name.ilike(f"%{q}%"))
    total = query.count()
    rows = query.order_by(College.name).offset(offset).limit(min(limit, 200)).all()
    return {
        "total": total,
        "items": [
            {"id": c.id, "name": c.name, "city": c.city, "state": c.state,
             "website": c.website, "naac_grade": c.naac_grade, "nirf_rank": c.nirf_rank,
             "type": c.college_type.value, "contacts": len(c.contacts)}
            for c in rows
        ],
    }


@router.get("/colleges/{college_id}")
def get_college(college_id: int, db: Session = Depends(get_db)):
    college = db.get(College, college_id)
    if not college:
        raise HTTPException(404, "College not found")
    return {
        "id": college.id, "name": college.name, "city": college.city,
        "state": college.state, "website": college.website,
        "affiliation": college.affiliation, "naac_grade": college.naac_grade,
        "nirf_rank": college.nirf_rank, "type": college.college_type.value,
        "research": college.research.summary if college.research else None,
        "research_status": college.research.status.value if college.research else "PENDING",
        "contacts": [
            {"id": c.id, "full_name": c.full_name, "role": c.role.value,
             "email": c.email, "confidence": c.confidence, "status": c.status.value,
             "sources": [{"field": s.field_name, "url": s.source_url,
                          "type": s.source_type.value} for s in c.sources]}
            for c in college.contacts
        ],
    }


# ---------- contacts ----------

@router.get("/contacts")
def list_contacts(status: str | None = None, limit: int = 50, offset: int = 0,
                  db: Session = Depends(get_db)):
    query = db.query(Contact)
    if status:
        try:
            query = query.filter(Contact.status == ContactStatus(status.upper()))
        except ValueError:
            raise HTTPException(422, f"Unknown status {status!r}")
    total = query.count()
    rows = query.order_by(Contact.id.desc()).offset(offset).limit(min(limit, 200)).all()
    return {
        "total": total,
        "items": [
            {"id": c.id, "full_name": c.full_name, "role": c.role.value,
             "college": c.college.name, "email": c.email,
             "confidence": c.confidence, "status": c.status.value,
             "last_contact_at": c.last_contact_at, "next_followup_at": c.next_followup_at,
             "notes": c.notes}
            for c in rows
        ],
    }


# ---------- direct contact import
# IMPORTANT: these POST routes must be registered BEFORE /contacts/{contact_id}
# so FastAPI doesn't treat "import" as a path parameter and return 405. ----------

class ContactImportRow(BaseModel):
    college_name: str
    city: str = "Unknown"
    state: str = "Unknown"
    website: str | None = None
    # TPO
    tpo_name: str | None = None
    tpo_email: str | None = None
    # Director / Principal
    director_name: str | None = None
    director_email: str | None = None


class ContactImportRequest(BaseModel):
    rows: list[ContactImportRow]


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _upsert_college(db: Session, row: ContactImportRow) -> College:
    norm = _normalize(row.college_name)
    college = db.query(College).filter_by(normalized_name=norm, city=row.city).first()
    if not college:
        college = College(
            name=row.college_name.strip(),
            normalized_name=norm,
            city=row.city.strip(),
            state=row.state.strip(),
            website=row.website or None,
            college_type=CollegeType.UNKNOWN,
            discovery_source="manual_import",
        )
        db.add(college)
        db.flush()
    return college


def _upsert_contact(db: Session, college: College, name: str, email: str | None,
                    role: CanonicalRole) -> tuple[Contact, bool]:
    """Return (contact, created). Dedup on college_id + email if email given, else name."""
    existing = None
    if email:
        existing = db.query(Contact).filter_by(
            college_id=college.id, email=email.lower().strip()
        ).first()
    if not existing:
        existing = db.query(Contact).filter_by(
            college_id=college.id, full_name=name.strip()
        ).first()
    if existing:
        return existing, False
    contact = Contact(
        college_id=college.id,
        full_name=name.strip(),
        email=email.lower().strip() if email else None,
        role=role,
        confidence=95,
        status=ContactStatus.VERIFIED,
    )
    db.add(contact)
    db.flush()
    db.add(ContactSource(
        contact_id=contact.id,
        field_name="email",
        source_type=SourceType.MANUAL,
        source_url="manual_import",
        excerpt="Directly imported by operator",
        collected_at=datetime.now(timezone.utc),
    ))
    return contact, True


@router.post("/contacts/import")
def import_contacts(body: ContactImportRequest,
                    user: User = Depends(require_operator),
                    db: Session = Depends(get_db)):
    """Bulk-import colleges + contacts (TPO + Director) in one call."""
    added_colleges = 0
    added_contacts = 0
    skipped_contacts = 0

    for row in body.rows:
        if not row.college_name.strip():
            continue
        college = _upsert_college(db, row)
        if college.id is None:
            added_colleges += 1

        for name, email, role in [
            (row.tpo_name, row.tpo_email, CanonicalRole.TPO),
            (row.director_name, row.director_email, CanonicalRole.DIRECTOR),
        ]:
            if not name:
                continue
            _, created = _upsert_contact(db, college, name, email, role)
            if created:
                added_contacts += 1
            else:
                skipped_contacts += 1

    db.commit()
    return {
        "ok": True,
        "colleges_processed": len(body.rows),
        "contacts_added": added_contacts,
        "contacts_skipped": skipped_contacts,
        "message": f"Added {added_contacts} contacts across {len(body.rows)} colleges.",
    }


@router.post("/contacts/import-csv")
def import_contacts_csv(body: dict,
                        user: User = Depends(require_operator),
                        db: Session = Depends(get_db)):
    """Accept raw CSV text and import contacts."""
    csv_text: str = body.get("csv_text", "")
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    rows = []
    for r in reader:
        rows.append(ContactImportRow(
            college_name=r.get("college_name", r.get("College Name", "")).strip(),
            city=r.get("city", r.get("City", "Unknown")).strip(),
            state=r.get("state", r.get("State", "Unknown")).strip(),
            website=r.get("website", r.get("Website", None)) or None,
            tpo_name=r.get("tpo_name", r.get("TPO Name", None)) or None,
            tpo_email=r.get("tpo_email", r.get("TPO Email", None)) or None,
            director_name=r.get("director_name", r.get("Director Name", None)) or None,
            director_email=r.get("director_email", r.get("Director Email", None)) or None,
        ))
    return import_contacts(ContactImportRequest(rows=rows), user=user, db=db)


# ---------- college patch / delete ----------

class CollegePatch(BaseModel):
    name: str | None = None
    city: str | None = None
    state: str | None = None
    website: str | None = None
    naac_grade: str | None = None
    nirf_rank: int | None = None
    college_type: str | None = None
    affiliation: str | None = None


@router.patch("/colleges/{college_id}")
def patch_college(college_id: int, body: CollegePatch,
                  user: User = Depends(require_operator), db: Session = Depends(get_db)):
    college = db.get(College, college_id)
    if not college:
        raise HTTPException(404, "College not found")
    if body.name is not None:
        college.name = body.name.strip()
        college.normalized_name = re.sub(r"\s+", " ", body.name.strip().lower())
    if body.city is not None:
        college.city = body.city.strip()
    if body.state is not None:
        college.state = body.state.strip()
    if body.website is not None:
        college.website = body.website.strip() or None
    if body.naac_grade is not None:
        college.naac_grade = body.naac_grade.strip() or None
    if body.nirf_rank is not None:
        college.nirf_rank = body.nirf_rank
    if body.college_type is not None:
        try:
            college.college_type = CollegeType(body.college_type.upper())
        except ValueError:
            raise HTTPException(422, f"Unknown college type {body.college_type!r}")
    if body.affiliation is not None:
        college.affiliation = body.affiliation.strip() or None
    from app.models import AuditLog
    db.add(AuditLog(user_id=user.id, action="college.update", entity_type="college",
                    entity_id=college.id, detail=body.model_dump(exclude_none=True)))
    db.commit()
    return {"ok": True}


@router.delete("/colleges/{college_id}")
def delete_college(college_id: int,
                   user: User = Depends(require_operator), db: Session = Depends(get_db)):
    college = db.get(College, college_id)
    if not college:
        raise HTTPException(404, "College not found")
    from app.models import (
        AuditLog, EmailDraft, EmailEvent, EmailMessage, FollowupSchedule,
    )
    # Delete child records in dependency order to avoid FK violations.
    # contacts.id is referenced by: email_drafts, email_messages, followup_schedules.
    # email_messages.id is referenced by: email_events.
    # email_drafts.id is referenced by: email_messages.
    contact_ids = [c.id for c in college.contacts]
    if contact_ids:
        # events → messages → drafts → followups (then contacts cascade via SQLAlchemy)
        msg_ids = [m.id for m in db.query(EmailMessage).filter(
            EmailMessage.contact_id.in_(contact_ids)).all()]
        if msg_ids:
            db.query(EmailEvent).filter(EmailEvent.message_id.in_(msg_ids)).delete(
                synchronize_session=False)
        db.query(EmailMessage).filter(
            EmailMessage.contact_id.in_(contact_ids)).delete(synchronize_session=False)
        db.query(EmailDraft).filter(
            EmailDraft.contact_id.in_(contact_ids)).delete(synchronize_session=False)
        db.query(FollowupSchedule).filter(
            FollowupSchedule.contact_id.in_(contact_ids)).delete(synchronize_session=False)
    db.add(AuditLog(user_id=user.id, action="college.delete", entity_type="college",
                    entity_id=college.id, detail={"name": college.name}))
    db.delete(college)
    db.commit()
    return {"ok": True}


# ---------- contact patch / delete (parameterized — must be AFTER /import routes) ----------

class ContactPatch(BaseModel):
    status: str | None = None
    notes: str | None = None
    full_name: str | None = None
    email: str | None = None
    role: str | None = None


_MANUAL_STATUSES = {  # transitions an operator may set by hand
    ContactStatus.VERIFIED, ContactStatus.NEEDS_MANUAL_REVIEW,
    ContactStatus.MEETING_SCHEDULED, ContactStatus.WON, ContactStatus.LOST,
    ContactStatus.REPLIED_POSITIVE, ContactStatus.REPLIED_NEGATIVE,
}


@router.patch("/contacts/{contact_id}")
def patch_contact(contact_id: int, body: ContactPatch,
                  user: User = Depends(require_operator), db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(404, "Contact not found")
    if body.status is not None:
        try:
            new_status = ContactStatus(body.status.upper())
        except ValueError:
            raise HTTPException(422, f"Unknown status {body.status!r}")
        if new_status not in _MANUAL_STATUSES:
            raise HTTPException(422, f"{new_status.value} is set by the pipeline, not manually")
        contact.status = new_status
    if body.notes is not None:
        contact.notes = body.notes
    if body.full_name is not None:
        contact.full_name = body.full_name.strip()
    if body.email is not None:
        contact.email = body.email.strip().lower() or None
    if body.role is not None:
        try:
            from app.models.base import CanonicalRole
            contact.role = CanonicalRole(body.role.upper())
        except ValueError:
            raise HTTPException(422, f"Unknown role {body.role!r}")
    from app.models import AuditLog
    db.add(AuditLog(user_id=user.id, action="contact.update", entity_type="contact",
                    entity_id=contact.id, detail=body.model_dump(exclude_none=True)))
    db.commit()
    return {"ok": True, "status": contact.status.value}


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int,
                   user: User = Depends(require_operator), db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(404, "Contact not found")
    from app.models import (
        AuditLog, EmailDraft, EmailEvent, EmailMessage, FollowupSchedule,
    )
    # Delete child records in dependency order to avoid FK violations.
    msg_ids = [m.id for m in db.query(EmailMessage).filter_by(contact_id=contact_id).all()]
    if msg_ids:
        db.query(EmailEvent).filter(EmailEvent.message_id.in_(msg_ids)).delete(
            synchronize_session=False)
    db.query(EmailMessage).filter_by(contact_id=contact_id).delete(synchronize_session=False)
    db.query(EmailDraft).filter_by(contact_id=contact_id).delete(synchronize_session=False)
    db.query(FollowupSchedule).filter_by(contact_id=contact_id).delete(synchronize_session=False)
    db.add(AuditLog(user_id=user.id, action="contact.delete", entity_type="contact",
                    entity_id=contact.id, detail={"name": contact.full_name}))
    db.delete(contact)
    db.commit()
    return {"ok": True}


# ---------- drafts ----------

@router.get("/drafts")
def list_drafts(status: str = "DRAFT", limit: int = 50, offset: int = 0,
                db: Session = Depends(get_db)):
    try:
        wanted = DraftStatus(status.upper())
    except ValueError:
        raise HTTPException(422, f"Unknown status {status!r}")
    query = db.query(EmailDraft).filter(EmailDraft.status == wanted)
    total = query.count()
    rows = query.order_by(EmailDraft.id).offset(offset).limit(min(limit, 200)).all()
    out = []
    for d in rows:
        contact = db.get(Contact, d.contact_id)
        out.append({
            "id": d.id, "contact": contact.full_name, "college": contact.college.name,
            "email": contact.email, "touch": d.touch_number,
            "chosen_subject": d.chosen_subject, "subject_options": d.subject_options,
            "body_text": d.body_text, "lint": d.lint_report,
        })
    return {"total": total, "items": out}


class DraftPatch(BaseModel):
    chosen_subject: str | None = None
    body_text: str | None = None


@router.patch("/drafts/{draft_id}")
def patch_draft(draft_id: int, body: DraftPatch,
                user: User = Depends(require_operator), db: Session = Depends(get_db)):
    draft = db.get(EmailDraft, draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found")
    if draft.status is not DraftStatus.DRAFT:
        raise HTTPException(409, f"Draft is {draft.status.value}; only DRAFT is editable")
    if body.chosen_subject is not None:
        draft.chosen_subject = body.chosen_subject
    if body.body_text is not None:
        draft.body_text = body.body_text
    contact = db.get(Contact, draft.contact_id)
    draft.lint_report = lint_draft(
        draft.subject_options or [], draft.body_text or "", contact.college.name
    )
    db.commit()
    return {"ok": True, "lint": draft.lint_report}


@router.post("/drafts/{draft_id}/approve")
def approve(draft_id: int, user: User = Depends(require_operator),
            db: Session = Depends(get_db)):
    draft = db.get(EmailDraft, draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found")
    try:
        approve_draft(db, draft, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@router.post("/drafts/{draft_id}/reject")
def reject(draft_id: int, user: User = Depends(require_operator),
           db: Session = Depends(get_db)):
    draft = db.get(EmailDraft, draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found")
    if draft.status not in (DraftStatus.DRAFT, DraftStatus.APPROVED):
        raise HTTPException(409, f"Draft is {draft.status.value}")
    draft.status = DraftStatus.REJECTED
    db.commit()
    return {"ok": True}


# ---------- replies ----------

class ReplyIn(BaseModel):
    contact_id: int
    text: str


@router.post("/replies")
def submit_reply(body: ReplyIn, user: User = Depends(require_operator),
                 db: Session = Depends(get_db)):
    from app.crm.replies import process_reply

    contact = db.get(Contact, body.contact_id)
    if not contact:
        raise HTTPException(404, "Contact not found")
    sentiment = process_reply(db, contact, body.text, _llm())
    return {"sentiment": sentiment.value, "contact_status": contact.status.value}


# ---------- stats ----------

@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    sent_q = db.query(EmailMessage).filter(EmailMessage.status != MessageStatus.FAILED)
    sent = sent_q.count()

    def _event_msgs(event_type):
        return (
            db.query(EmailEvent.message_id)
            .filter(EmailEvent.event_type == event_type)
            .distinct()
            .count()
        )

    opened, clicked, replied = (
        _event_msgs(EmailEventType.OPEN),
        _event_msgs(EmailEventType.CLICK),
        _event_msgs(EmailEventType.REPLY),
    )
    by_status = dict(
        db.query(Contact.status, func.count(Contact.id)).group_by(Contact.status).all()
    )
    return {
        "colleges": db.query(College).count(),
        "contacts": db.query(Contact).count(),
        "emails_sent": sent,
        "open_rate": round(opened / sent, 3) if sent else 0.0,
        "click_rate": round(clicked / sent, 3) if sent else 0.0,
        "reply_rate": round(replied / sent, 3) if sent else 0.0,
        "positive": by_status.get(ContactStatus.REPLIED_POSITIVE, 0),
        "meetings": by_status.get(ContactStatus.MEETING_SCHEDULED, 0),
        "won": by_status.get(ContactStatus.WON, 0),
        "funnel": {s.value: by_status.get(s, 0) for s in ContactStatus},
        "colleges_by_state": dict(
            db.query(College.state, func.count(College.id)).group_by(College.state).all()
        ),
    }


# ---------- pipeline actions (UI-triggered) ----------

@router.post("/pipeline/draft-emails")
def pipeline_draft_emails(limit: int = 50,
                           user: User = Depends(require_operator),
                           db: Session = Depends(get_db)):
    """Generate email drafts for all VERIFIED contacts that don't have one yet."""
    from app.models import ContactStatus as CS

    drafted_ids = db.query(EmailDraft.contact_id).filter(EmailDraft.touch_number == 1)
    contacts = (
        db.query(Contact)
        .filter(Contact.status == CS.VERIFIED, ~Contact.id.in_(drafted_ids))
        .limit(limit)
        .all()
    )
    drafted = 0
    lint_passed = 0
    lint_failed = 0
    llm = _llm()
    for contact in contacts:
        try:
            draft = generate_draft(db, contact, llm)
            drafted += 1
            if draft.lint_report and draft.lint_report.get("ok"):
                lint_passed += 1
            else:
                lint_failed += 1
        except Exception:
            lint_failed += 1
    return {"drafted": drafted, "lint_passed": lint_passed, "lint_failed": lint_failed}


@router.post("/pipeline/send")
def pipeline_send(limit: int = 25,
                  user: User = Depends(require_operator),
                  db: Session = Depends(get_db)):
    """Send all APPROVED drafts (respects daily/hourly caps and suppression list)."""
    from app.sender.providers import SMTPSender
    from app.sender.service import remaining_quota, send_approved_batch

    s = get_settings()
    # Validate SMTP config before attempting to send
    if not s.smtp_host:
        raise HTTPException(422, "SMTP_HOST is not configured. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and SENDER_EMAIL in your .env file.")
    if not s.sender_email or "example" in s.sender_email:
        raise HTTPException(422, f"SENDER_EMAIL is not configured properly (current: '{s.sender_email}'). Set a real sender email in your .env file.")

    try:
        provider = SMTPSender()
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    quota = remaining_quota(db)
    result = send_approved_batch(db, provider, limit=limit)
    return {
        "sent": result.get("sent", 0),
        "suppressed": result.get("suppressed", 0),
        "failed": result.get("failed", 0),
        "quota_remaining": result.get("quota_left", quota),
    }


@router.get("/pipeline/smtp-status")
def smtp_status(user: User = Depends(require_operator)):
    """Check whether SMTP is configured (does not test the connection)."""
    s = get_settings()
    configured = bool(
        s.smtp_host
        and s.smtp_username
        and s.smtp_password
        and s.sender_email
        and "example" not in s.sender_email
    )
    return {
        "configured": configured,
        "smtp_host": s.smtp_host or "(not set)",
        "smtp_port": s.smtp_port,
        "smtp_username": s.smtp_username or "(not set)",
        "sender_email": s.sender_email or "(not set)",
        "sender_name": s.sender_name or "(not set)",
        "daily_send_cap": s.daily_send_cap,
        "hourly_send_cap": s.hourly_send_cap,
        "missing": [
            field for field, val in [
                ("SMTP_HOST", s.smtp_host),
                ("SMTP_USERNAME", s.smtp_username),
                ("SMTP_PASSWORD", s.smtp_password),
                ("SENDER_EMAIL", s.sender_email),
            ] if not val
        ] + (["SENDER_EMAIL (placeholder domain)"] if s.sender_email and "example" in s.sender_email else []),
    }
