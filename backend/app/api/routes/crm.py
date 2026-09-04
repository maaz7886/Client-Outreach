"""Authenticated CRM endpoints: colleges, contacts, drafts, replies, stats."""

import csv
import io
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_operator
from app.core.config import get_settings
from app.core.db import get_db
from app.llm.providers import get_provider
from app.models import (
    Attachment,
    Campaign,
    College,
    Contact,
    ContactList,
    ContactStatus,
    DraftStatus,
    EmailDraft,
    EmailEvent,
    EmailEventType,
    EmailMessage,
    EmailTemplate,
    MessageStatus,
    SenderProfile,
    User,
)
from app.models.base import CanonicalRole, CollegeType, SourceType, utcnow
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
    list_id: int | None = None
    new_list_name: str | None = None
    new_list_description: str | None = None


def _resolve_import_list(db: Session, body: ContactImportRequest) -> ContactList | None:
    """Return the target list for import, or None when no list assignment requested."""
    if body.new_list_name is not None:
        if body.list_id is not None:
            raise HTTPException(422, "Provide list_id or new_list_name, not both")
        name = body.new_list_name.strip()
        if not name:
            raise HTTPException(422, "new_list_name cannot be empty")
        lst = ContactList(name=name, description=body.new_list_description)
        db.add(lst)
        db.flush()
        return lst
    if body.list_id is not None:
        lst = db.get(ContactList, body.list_id)
        if not lst:
            raise HTTPException(404, "List not found")
        return lst
    return None


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
    contacts_associated = 0
    target_list = _resolve_import_list(db, body)

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
            contact, created = _upsert_contact(db, college, name, email, role)
            if created:
                added_contacts += 1
            else:
                skipped_contacts += 1
            if target_list is not None and contact not in target_list.contacts:
                target_list.contacts.append(contact)
                contacts_associated += 1

    db.commit()
    result = {
        "ok": True,
        "colleges_processed": len(body.rows),
        "contacts_added": added_contacts,
        "contacts_skipped": skipped_contacts,
        "message": f"Added {added_contacts} contacts across {len(body.rows)} colleges.",
    }
    if target_list is not None:
        result["list_id"] = target_list.id
        result["list_name"] = target_list.name
        result["contacts_associated"] = contacts_associated
        result["message"] = (
            f"Added {added_contacts} contacts across {len(body.rows)} colleges. "
            f"{contacts_associated} contact(s) assigned to list \"{target_list.name}\"."
        )
    return result


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
    return import_contacts(
        ContactImportRequest(
            rows=rows,
            list_id=body.get("list_id"),
            new_list_name=body.get("new_list_name"),
            new_list_description=body.get("new_list_description"),
        ),
        user=user,
        db=db,
    )


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
    attachment_map: dict[int, list[dict]] = {}
    if rows:
        draft_ids = [d.id for d in rows]
        for att in db.query(Attachment).filter(Attachment.draft_id.in_(draft_ids)).all():
            attachment_map.setdefault(att.draft_id, []).append(_attachment_dict(att))
    out = []
    for d in rows:
        contact = db.get(Contact, d.contact_id)
        out.append({
            "id": d.id, "contact": contact.full_name, "college": contact.college.name,
            "email": contact.email, "touch": d.touch_number,
            "chosen_subject": d.chosen_subject, "subject_options": d.subject_options,
            "body_text": d.body_text, "lint": d.lint_report,
            "attachments": attachment_map.get(d.id, []),
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


def _attachment_dict(att: Attachment) -> dict:
    return {
        "id": att.id,
        "filename": att.original_filename,
        "original_filename": att.original_filename,
        "mime_type": att.mime_type,
        "size": att.size,
        "uploaded_at": att.uploaded_at,
    }


def _editable_draft(db: Session, draft_id: int) -> EmailDraft:
    draft = db.get(EmailDraft, draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found")
    if draft.status is not DraftStatus.DRAFT:
        raise HTTPException(
            409, f"Draft is {draft.status.value}; attachments can only be edited on DRAFT",
        )
    return draft


@router.get("/drafts/{draft_id}/attachments")
def list_draft_attachments(draft_id: int, db: Session = Depends(get_db)):
    draft = db.get(EmailDraft, draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found")
    rows = db.query(Attachment).filter_by(draft_id=draft_id).order_by(Attachment.id).all()
    return {"items": [_attachment_dict(a) for a in rows]}


@router.post("/drafts/{draft_id}/attachments", status_code=201)
async def upload_draft_attachments(
    draft_id: int,
    files: list[UploadFile] = File(...),
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    from app.sender.storage import delete_file, read_upload, save_bytes

    draft = _editable_draft(db, draft_id)
    if not files:
        raise HTTPException(422, "No files uploaded")
    max_per = get_settings().max_attachments_per_draft
    existing = db.query(Attachment).filter_by(draft_id=draft_id).count()
    if existing + len(files) > max_per:
        raise HTTPException(422, f"Maximum {max_per} attachments per draft")

    created: list[dict] = []
    saved_paths: list[str] = []
    try:
        for upload in files:
            content, original, stored_name, mime_type = await read_upload(upload)
            storage_path = save_bytes(content, stored_name)
            saved_paths.append(storage_path)
            row = Attachment(
                draft_id=draft.id,
                filename=stored_name,
                original_filename=original,
                mime_type=mime_type,
                size=len(content),
                storage_path=storage_path,
            )
            db.add(row)
            db.flush()
            created.append(_attachment_dict(row))
        db.commit()
    except Exception:
        db.rollback()
        for path in saved_paths:
            delete_file(path)
        raise
    return {"items": created}


@router.delete("/drafts/{draft_id}/attachments/{attachment_id}")
def delete_draft_attachment(
    draft_id: int,
    attachment_id: int,
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    from app.sender.storage import delete_file

    _editable_draft(db, draft_id)
    att = db.get(Attachment, attachment_id)
    if not att or att.draft_id != draft_id:
        raise HTTPException(404, "Attachment not found")
    delete_file(att.storage_path)
    db.delete(att)
    db.commit()
    return {"ok": True}


@router.put("/drafts/{draft_id}/attachments/{attachment_id}")
async def replace_draft_attachment(
    draft_id: int,
    attachment_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    from app.sender.storage import delete_file, read_upload, save_bytes

    _editable_draft(db, draft_id)
    att = db.get(Attachment, attachment_id)
    if not att or att.draft_id != draft_id:
        raise HTTPException(404, "Attachment not found")

    content, original, stored_name, mime_type = await read_upload(file)
    old_path = att.storage_path
    att.filename = stored_name
    att.original_filename = original
    att.mime_type = mime_type
    att.size = len(content)
    att.storage_path = save_bytes(content, stored_name)
    db.commit()
    delete_file(old_path)
    return _attachment_dict(att)


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


class ApproveAllIn(BaseModel):
    list_id: int | None = None


@router.post("/drafts/approve-all")
def approve_all_drafts(body: ApproveAllIn | None = None,
                       user: User = Depends(require_operator),
                       db: Session = Depends(get_db)):
    query = db.query(EmailDraft).filter(EmailDraft.status == DraftStatus.DRAFT)
    if body and body.list_id is not None:
        lst = db.get(ContactList, body.list_id)
        if lst:
            member_ids = [c.id for c in lst.contacts]
            query = query.filter(EmailDraft.contact_id.in_(member_ids))
    drafts = query.all()
    approved = 0
    for d in drafts:
        if d.lint_report and d.lint_report.get("ok"):
            d.status = DraftStatus.APPROVED
            d.approved_by_id = user.id
            d.approved_at = utcnow()
            approved += 1
    db.commit()
    return {"ok": True, "approved": approved}


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

def _verified_contacts_without_drafts(
    db: Session, limit: int, list_id: int | None = None,
) -> list[Contact]:
    """Contacts with valid email addresses eligible for draft generation, optionally scoped to one list."""
    from app.models import ContactStatus as CS

    query = db.query(Contact).filter(
        Contact.email.isnot(None),
        Contact.email != "",
        Contact.status.in_([CS.VERIFIED, CS.CONTACTED, CS.DISCOVERED, CS.NEEDS_MANUAL_REVIEW]),
    )
    if list_id is not None:
        lst = db.get(ContactList, list_id)
        if not lst:
            raise HTTPException(404, "List not found")
        member_ids = [c.id for c in lst.contacts]
        if not member_ids:
            return []
        query = query.filter(Contact.id.in_(member_ids))
    contacts = query.limit(min(limit, 200)).all()
    for c in contacts:
        if c.status in (CS.DISCOVERED, CS.NEEDS_MANUAL_REVIEW):
            c.status = CS.VERIFIED
    db.commit()
    return contacts


def _generate_drafts_for_contacts(
    db: Session,
    contacts: list[Contact],
    template_context: str | None = None,
) -> dict:
    drafted = 0
    lint_passed = 0
    lint_failed = 0
    errors: list[str] = []
    llm = _llm()
    for contact in contacts:
        try:
            draft = generate_draft(db, contact, llm, template_context=template_context, force_regenerate=True)
            drafted += 1
            if draft.lint_report and draft.lint_report.get("ok"):
                lint_passed += 1
            else:
                lint_failed += 1
        except Exception as exc:
            db.rollback()
            lint_failed += 1
            errors.append(f"contact {contact.id} ({contact.full_name}): {exc}")
    result: dict = {"drafted": drafted, "lint_passed": lint_passed, "lint_failed": lint_failed}
    if errors:
        result["errors"] = errors
    return result


def _resolve_template_context(db: Session, template_id: int | None) -> str | None:
    if template_id is None:
        return None
    from app.personalize.templates import build_template_prompt_block

    template = db.get(EmailTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    block = build_template_prompt_block(template)
    return block or None


@router.post("/pipeline/draft-emails")
def pipeline_draft_emails(limit: int = 50, template_id: int | None = None,
                           user: User = Depends(require_operator),
                           db: Session = Depends(get_db)):
    """Generate email drafts for all VERIFIED contacts that don't have one yet."""
    template_context = _resolve_template_context(db, template_id)
    contacts = _verified_contacts_without_drafts(db, limit)
    result = _generate_drafts_for_contacts(db, contacts, template_context=template_context)
    if template_id is not None:
        template = db.get(EmailTemplate, template_id)
        result["template_id"] = template_id
        result["template_name"] = template.name if template else None
    return result


@router.post("/lists/{list_id}/draft-emails")
def draft_emails_for_list(list_id: int, limit: int = 50, template_id: int | None = None,
                          user: User = Depends(require_operator),
                          db: Session = Depends(get_db)):
    """Generate email drafts for VERIFIED contacts in a list that don't have one yet."""
    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    template_context = _resolve_template_context(db, template_id)
    contacts = _verified_contacts_without_drafts(db, limit, list_id=list_id)
    result = _generate_drafts_for_contacts(db, contacts, template_context=template_context)
    response = {
        **result,
        "list_id": lst.id,
        "list_name": lst.name,
        "eligible_contacts": len(contacts),
    }
    if template_id is not None:
        template = db.get(EmailTemplate, template_id)
        response["template_id"] = template_id
        response["template_name"] = template.name if template else None
    return response


def _smtp_sender():
    """Validate SMTP config and return a sender provider."""
    from app.sender.providers import SMTPSender

    s = get_settings()
    if not s.smtp_host:
        raise HTTPException(422, "SMTP_HOST is not configured. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and SENDER_EMAIL in your .env file.")
    if not s.smtp_username or not s.smtp_password:
        raise HTTPException(422, "SMTP_USERNAME and SMTP_PASSWORD must be configured in your .env file.")
    try:
        return SMTPSender()
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def _default_sender_from_env() -> dict:
    s = get_settings()
    configured = bool(
        s.sender_email and "example" not in s.sender_email and s.sender_name,
    )
    return {
        "display_name": s.sender_name or "AIValytics",
        "email_address": s.sender_email or "",
        "configured": configured,
        "label": "Default (.env)",
    }


def _resolve_sender_identity(
    db: Session, sender_profile_id: int | None = None,
) -> tuple[str, str, int | None, str]:
    if sender_profile_id is None:
        default = _default_sender_from_env()
        if not default["email_address"] or "example" in default["email_address"]:
            raise HTTPException(
                422,
                "No sender profile selected and SENDER_EMAIL is not configured in .env.",
            )
        return default["display_name"], default["email_address"], None, default["label"]

    profile = db.get(SenderProfile, sender_profile_id)
    if not profile:
        raise HTTPException(404, "Sender profile not found")
    if not profile.enabled:
        raise HTTPException(422, "Sender profile is disabled")
    email = profile.email_address.strip().lower()
    if not email:
        raise HTTPException(422, "Sender profile has no email address")
    return profile.display_name.strip(), email, profile.id, profile.name


def _sender_profile_dict(p: SenderProfile) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "display_name": p.display_name,
        "email_address": p.email_address,
        "enabled": p.enabled,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _count_send_recipients(
    db: Session, limit: int, contact_ids: list[int] | None = None,
) -> int:
    """Approved drafts eligible for this send (before quota/limit cap)."""
    from app.sender.service import remaining_quota

    quota = remaining_quota(db)
    batch_size = min(quota, limit)
    if batch_size <= 0:
        return 0
    query = db.query(EmailDraft).filter(EmailDraft.status == DraftStatus.APPROVED)
    if contact_ids is not None:
        if not contact_ids:
            return 0
        query = query.filter(EmailDraft.contact_id.in_(contact_ids))
    return min(query.count(), batch_size)


def _campaign_dict(c: Campaign) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "list_id": c.list_id,
        "list_name": c.list_name,
        "recipient_count": c.recipient_count,
        "started_at": c.started_at,
        "completed_at": c.completed_at,
        "sent": c.sent,
        "failed": c.failed,
        "suppressed": c.suppressed,
    }


class SendRequest(BaseModel):
    contact_ids: list[int] | None = None


def _run_send_with_campaign(
    db: Session,
    provider,
    *,
    name: str,
    limit: int,
    list_id: int | None = None,
    list_name: str | None = None,
    contact_ids: list[int] | None = None,
    sender_profile_id: int | None = None,
) -> dict:
    """Execute send_approved_batch and persist a Campaign record (send logic unchanged)."""
    from app.sender.service import remaining_quota, send_approved_batch

    from_name, from_email, profile_id, profile_label = _resolve_sender_identity(
        db, sender_profile_id,
    )
    recipient_count = _count_send_recipients(db, limit, contact_ids)
    campaign = Campaign(
        name=name,
        list_id=list_id,
        list_name=list_name,
        recipient_count=recipient_count,
        started_at=utcnow(),
    )
    db.add(campaign)
    db.flush()

    # Clone list-level campaign attachments to campaign-level attachments
    import shutil
    import uuid
    from app.sender.storage import _storage_root

    list_attachments = []
    if list_id is not None:
        list_attachments = db.query(Attachment).filter_by(list_id=list_id, campaign_id=None, draft_id=None).all()

    for att in list_attachments:
        ext = att.filename.split(".")[-1]
        new_stored_name = f"{uuid.uuid4().hex}.{ext}"
        src_path = _storage_root() / att.storage_path
        dst_path = _storage_root() / new_stored_name
        try:
            shutil.copy2(src_path, dst_path)
            clone = Attachment(
                campaign_id=campaign.id,
                list_id=None,
                draft_id=None,
                filename=new_stored_name,
                original_filename=att.original_filename,
                mime_type=att.mime_type,
                size=att.size,
                storage_path=new_stored_name,
            )
            db.add(clone)
        except Exception:
            pass
    db.flush()

    quota = remaining_quota(db)
    result = send_approved_batch(
        db, provider,
        limit=limit,
        contact_ids=contact_ids,
        from_name=from_name,
        from_email=from_email,
        campaign_id=campaign.id,
    )

    campaign.sent = result.get("sent", 0)
    campaign.failed = result.get("failed", 0)
    campaign.suppressed = result.get("suppressed", 0)
    campaign.completed_at = utcnow()
    db.commit()

    response = {
        "sent": campaign.sent,
        "suppressed": campaign.suppressed,
        "failed": campaign.failed,
        "quota_remaining": result.get("quota_left", quota),
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "sender_profile_id": profile_id,
        "sender_label": profile_label,
        "from_name": from_name,
        "from_email": from_email,
    }
    if list_id is not None:
        response["list_id"] = list_id
        response["list_name"] = list_name
    return response


@router.post("/pipeline/send")
def pipeline_send(limit: int = 25, sender_profile_id: int | None = None,
                  user: User = Depends(require_operator),
                  db: Session = Depends(get_db)):
    """Send all APPROVED drafts (respects daily/hourly caps and suppression list)."""
    provider = _smtp_sender()
    stamp = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return _run_send_with_campaign(
        db, provider,
        name=f"All Contacts — {stamp}",
        limit=limit,
        sender_profile_id=sender_profile_id,
    )


@router.post("/lists/{list_id}/send")
def send_for_list(list_id: int, body: SendRequest | None = None, limit: int = 25, dry_run: bool = False,
                  sender_profile_id: int | None = None,
                  user: User = Depends(require_operator),
                  db: Session = Depends(get_db)):
    """Send APPROVED drafts for contacts in a list (respects caps and suppression)."""
    from app.sender.service import remaining_quota

    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    
    # Get contacts, optionally filtered by user selection
    if body and body.contact_ids is not None:
        contact_ids = [c.id for c in lst.contacts if c.id in body.contact_ids]
    else:
        contact_ids = [c.id for c in lst.contacts]

    if dry_run:
        ready = 0
        if contact_ids:
            ready = (
                db.query(EmailDraft)
                .filter(
                    EmailDraft.status == DraftStatus.APPROVED,
                    EmailDraft.contact_id.in_(contact_ids),
                )
                .count()
            )
        return {
            "dry_run": True,
            "ready_to_send": ready,
            "list_id": lst.id,
            "list_name": lst.name,
            "quota_remaining": remaining_quota(db),
        }

    provider = _smtp_sender()
    stamp = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return _run_send_with_campaign(
        db, provider,
        name=f"{lst.name} — {stamp}",
        limit=limit,
        list_id=lst.id,
        list_name=lst.name,
        contact_ids=contact_ids,
        sender_profile_id=sender_profile_id,
    )


# ---------- email templates ----------

class EmailTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    additional_context: str | None = None
    formatting_notes: str | None = None


class EmailTemplatePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    additional_context: str | None = None
    formatting_notes: str | None = None


class TemplatePreviewIn(BaseModel):
    contact_id: int | None = None


def _email_template_dict(t: EmailTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "additional_context": t.additional_context,
        "formatting_notes": t.formatting_notes,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


@router.get("/templates")
def list_email_templates(db: Session = Depends(get_db)):
    rows = db.query(EmailTemplate).order_by(EmailTemplate.name).all()
    return {"total": len(rows), "items": [_email_template_dict(t) for t in rows]}


@router.get("/templates/{template_id}")
def get_email_template(template_id: int, db: Session = Depends(get_db)):
    template = db.get(EmailTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return _email_template_dict(template)


@router.post("/templates", status_code=201)
def create_email_template(body: EmailTemplateCreate,
                          user: User = Depends(require_operator),
                          db: Session = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(422, "Template name is required")
    if not (body.additional_context or body.formatting_notes):
        raise HTTPException(422, "Provide additional_context and/or formatting_notes")
    template = EmailTemplate(
        name=body.name.strip(),
        description=body.description,
        additional_context=body.additional_context,
        formatting_notes=body.formatting_notes,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _email_template_dict(template)


@router.patch("/templates/{template_id}")
def patch_email_template(template_id: int, body: EmailTemplatePatch,
                         user: User = Depends(require_operator),
                         db: Session = Depends(get_db)):
    template = db.get(EmailTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(422, "Template name cannot be empty")
        template.name = body.name.strip()
    if body.description is not None:
        template.description = body.description or None
    if body.additional_context is not None:
        template.additional_context = body.additional_context or None
    if body.formatting_notes is not None:
        template.formatting_notes = body.formatting_notes or None
    if not (template.additional_context or template.formatting_notes):
        raise HTTPException(422, "Template must have additional_context and/or formatting_notes")
    db.commit()
    return _email_template_dict(template)


@router.delete("/templates/{template_id}")
def delete_email_template(template_id: int,
                          user: User = Depends(require_operator),
                          db: Session = Depends(get_db)):
    template = db.get(EmailTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    db.delete(template)
    db.commit()
    return {"ok": True}


@router.post("/templates/{template_id}/preview")
def preview_email_template(template_id: int, body: TemplatePreviewIn | None = None,
                           db: Session = Depends(get_db)):
    from app.personalize.engine import build_fact_sheet
    from app.personalize.templates import preview_template_prompt
    from app.models import ResearchSummary

    template = db.get(EmailTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    fact_sheet = None
    contact_id = body.contact_id if body else None
    if contact_id is not None:
        contact = db.get(Contact, contact_id)
        if not contact:
            raise HTTPException(404, "Contact not found")
        research = db.query(ResearchSummary).filter_by(college_id=contact.college_id).one_or_none()
        fact_sheet = build_fact_sheet(contact, research)

    return {
        "template": _email_template_dict(template),
        "preview": preview_template_prompt(template, fact_sheet),
        "contact_id": contact_id,
    }


# ---------- sender profiles ----------

class SenderProfileCreate(BaseModel):
    name: str
    display_name: str
    email_address: str
    enabled: bool = True


class SenderProfilePatch(BaseModel):
    name: str | None = None
    display_name: str | None = None
    email_address: str | None = None
    enabled: bool | None = None


@router.get("/sender-profiles")
def list_sender_profiles(db: Session = Depends(get_db)):
    rows = db.query(SenderProfile).order_by(SenderProfile.name).all()
    return {
        "default": _default_sender_from_env(),
        "total": len(rows),
        "items": [_sender_profile_dict(p) for p in rows],
    }


@router.post("/sender-profiles", status_code=201)
def create_sender_profile(body: SenderProfileCreate,
                          user: User = Depends(require_operator),
                          db: Session = Depends(get_db)):
    profile = SenderProfile(
        name=body.name.strip(),
        display_name=body.display_name.strip(),
        email_address=body.email_address.strip().lower(),
        enabled=body.enabled,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _sender_profile_dict(profile)


@router.patch("/sender-profiles/{profile_id}")
def patch_sender_profile(profile_id: int, body: SenderProfilePatch,
                         user: User = Depends(require_operator),
                         db: Session = Depends(get_db)):
    profile = db.get(SenderProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Sender profile not found")
    if body.name is not None:
        profile.name = body.name.strip()
    if body.display_name is not None:
        profile.display_name = body.display_name.strip()
    if body.email_address is not None:
        profile.email_address = body.email_address.strip().lower()
    if body.enabled is not None:
        profile.enabled = body.enabled
    db.commit()
    return _sender_profile_dict(profile)


@router.delete("/sender-profiles/{profile_id}")
def delete_sender_profile(profile_id: int,
                          user: User = Depends(require_operator),
                          db: Session = Depends(get_db)):
    profile = db.get(SenderProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Sender profile not found")
    db.delete(profile)
    db.commit()
    return {"ok": True}


# ---------- campaigns ----------

@router.get("/campaigns")
def list_campaigns(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    query = db.query(Campaign)
    total = query.count()
    rows = (
        query.order_by(Campaign.started_at.desc())
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )
    return {"total": total, "items": [_campaign_dict(c) for c in rows]}


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    return _campaign_dict(campaign)


@router.get("/pipeline/smtp-status")
def smtp_status(user: User = Depends(require_operator)):
    """Check whether SMTP is configured (does not test the connection)."""
    s = get_settings()
    default = _default_sender_from_env()
    configured = bool(
        s.smtp_host
        and s.smtp_username
        and s.smtp_password
    )
    return {
        "configured": configured,
        "smtp_host": s.smtp_host or "(not set)",
        "smtp_port": s.smtp_port,
        "smtp_username": s.smtp_username or "(not set)",
        "sender_email": s.sender_email or "(not set)",
        "sender_name": s.sender_name or "(not set)",
        "default_sender": default,
        "daily_send_cap": s.daily_send_cap,
        "hourly_send_cap": s.hourly_send_cap,
        "missing": [
            field for field, val in [
                ("SMTP_HOST", s.smtp_host),
                ("SMTP_USERNAME", s.smtp_username),
                ("SMTP_PASSWORD", s.smtp_password),
            ] if not val
        ] + (
            ["SENDER_EMAIL"] if not s.sender_email else []
        ) + (
            ["SENDER_EMAIL (placeholder domain)"] if s.sender_email and "example" in s.sender_email else []
        ),
    }


# ---------- contact lists ----------

class ListCreate(BaseModel):
    name: str
    description: str | None = None


class ListPatch(BaseModel):
    name: str | None = None
    description: str | None = None


@router.post("/lists", status_code=201)
def create_list(body: ListCreate,
                user: User = Depends(require_operator),
                db: Session = Depends(get_db)):
    lst = ContactList(name=body.name.strip(), description=body.description)
    db.add(lst)
    db.commit()
    db.refresh(lst)
    return {
        "id": lst.id, "name": lst.name, "description": lst.description,
        "contact_count": 0,
        "created_at": lst.created_at, "updated_at": lst.updated_at,
    }


@router.get("/lists")
def list_lists(db: Session = Depends(get_db)):
    rows = db.query(ContactList).order_by(ContactList.name).all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": lst.id, "name": lst.name, "description": lst.description,
                "contact_count": len(lst.contacts),
                "created_at": lst.created_at, "updated_at": lst.updated_at,
            }
            for lst in rows
        ],
    }


@router.get("/lists/{list_id}")
def get_list(list_id: int, db: Session = Depends(get_db)):
    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")

    # Fetch the latest draft status per contact in one query
    contact_ids = [c.id for c in lst.contacts]
    draft_status_map: dict[int, str] = {}
    if contact_ids:
        from app.models import EmailDraft
        from sqlalchemy import desc
        for cid in contact_ids:
            latest = (
                db.query(EmailDraft)
                .filter(EmailDraft.contact_id == cid)
                .order_by(desc(EmailDraft.id))
                .first()
            )
            if latest:
                draft_status_map[cid] = latest.status.value

    # Research status per college
    from app.models import ResearchSummary
    college_ids = list({c.college_id for c in lst.contacts})
    research_map: dict[int, str] = {}
    if college_ids:
        for rs in db.query(ResearchSummary).filter(
            ResearchSummary.college_id.in_(college_ids)
        ).all():
            research_map[rs.college_id] = rs.status.value

    return {
        "id": lst.id, "name": lst.name, "description": lst.description,
        "contact_count": len(lst.contacts),
        "created_at": lst.created_at, "updated_at": lst.updated_at,
        "contacts": [
            {
                "id": c.id,
                "full_name": c.full_name,
                "role": c.role.value,
                "college": c.college.name,
                "college_id": c.college_id,
                "email": c.email,
                "designation": c.designation_raw,
                "confidence": c.confidence,
                "status": c.status.value,
                "research_status": research_map.get(c.college_id, "PENDING"),
                "draft_status": draft_status_map.get(c.id),
                "last_contact_at": c.last_contact_at,
                "created_at": c.created_at,
            }
            for c in lst.contacts
        ],
    }


@router.patch("/lists/{list_id}")
def patch_list(list_id: int, body: ListPatch,
               user: User = Depends(require_operator),
               db: Session = Depends(get_db)):
    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    if body.name is not None:
        lst.name = body.name.strip()
    if body.description is not None:
        lst.description = body.description or None
    db.commit()
    return {
        "id": lst.id, "name": lst.name, "description": lst.description,
        "contact_count": len(lst.contacts),
        "created_at": lst.created_at, "updated_at": lst.updated_at,
    }


@router.delete("/lists/{list_id}")
def delete_list(list_id: int,
                user: User = Depends(require_operator),
                db: Session = Depends(get_db)):
    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    db.delete(lst)
    db.commit()
    return {"ok": True}


@router.post("/lists/{list_id}/contacts/{contact_id}", status_code=201)
def add_contact_to_list(list_id: int, contact_id: int,
                        user: User = Depends(require_operator),
                        db: Session = Depends(get_db)):
    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(404, "Contact not found")
    if contact not in lst.contacts:
        lst.contacts.append(contact)
        db.commit()
    return {"ok": True, "contact_count": len(lst.contacts)}


# ---------- list bulk operations ----------

class BulkContactIds(BaseModel):
    contact_ids: list[int]
    target_list_id: int | None = None  # for move/copy


@router.post("/lists/{list_id}/contacts/add-existing", status_code=201)
def add_existing_contacts_to_list(list_id: int, body: BulkContactIds,
                                  user: User = Depends(require_operator),
                                  db: Session = Depends(get_db)):
    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    added = 0
    for cid in body.contact_ids:
        contact = db.get(Contact, cid)
        if contact and contact not in lst.contacts:
            lst.contacts.append(contact)
            added += 1
    db.commit()
    return {"ok": True, "added": added, "contact_count": len(lst.contacts)}


@router.delete("/lists/{list_id}/contacts/{contact_id}")
def remove_contact_from_list(list_id: int, contact_id: int,
                              user: User = Depends(require_operator),
                              db: Session = Depends(get_db)):
    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(404, "Contact not found")
    if contact in lst.contacts:
        lst.contacts.remove(contact)
        db.commit()
    return {"ok": True, "contact_count": len(lst.contacts)}


@router.post("/lists/{list_id}/contacts/bulk-remove")
def bulk_remove_contacts_from_list(
    list_id: int,
    body: BulkContactIds,
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """Remove multiple contacts from a list (does not delete the contacts)."""
    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    removed = 0
    for cid in body.contact_ids:
        contact = db.get(Contact, cid)
        if contact and contact in lst.contacts:
            lst.contacts.remove(contact)
            removed += 1
    db.commit()
    return {"ok": True, "removed": removed, "contact_count": len(lst.contacts)}


@router.post("/lists/{list_id}/contacts/bulk-move")
def bulk_move_contacts(
    list_id: int,
    body: BulkContactIds,
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """Move contacts from this list to another list."""
    if not body.target_list_id:
        raise HTTPException(422, "target_list_id is required")
    src = db.get(ContactList, list_id)
    dst = db.get(ContactList, body.target_list_id)
    if not src:
        raise HTTPException(404, "Source list not found")
    if not dst:
        raise HTTPException(404, "Target list not found")
    moved = 0
    for cid in body.contact_ids:
        contact = db.get(Contact, cid)
        if contact and contact in src.contacts:
            src.contacts.remove(contact)
            if contact not in dst.contacts:
                dst.contacts.append(contact)
            moved += 1
    db.commit()
    return {"ok": True, "moved": moved}


@router.post("/lists/{list_id}/contacts/bulk-copy")
def bulk_copy_contacts(
    list_id: int,
    body: BulkContactIds,
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """Copy contacts from this list to another list (keeps them in source too)."""
    if not body.target_list_id:
        raise HTTPException(422, "target_list_id is required")
    dst = db.get(ContactList, body.target_list_id)
    if not dst:
        raise HTTPException(404, "Target list not found")
    copied = 0
    for cid in body.contact_ids:
        contact = db.get(Contact, cid)
        if contact and contact not in dst.contacts:
            dst.contacts.append(contact)
            copied += 1
    db.commit()
    return {"ok": True, "copied": copied}


@router.get("/lists/{list_id}/export-csv")
def export_list_csv(list_id: int, db: Session = Depends(get_db)):
    """Export all contacts in a list as a CSV file."""
    import io, csv
    from fastapi.responses import StreamingResponse
    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "full_name", "role", "designation", "college", "email",
        "status", "confidence", "last_contact_at", "created_at",
    ])
    writer.writeheader()
    for c in lst.contacts:
        writer.writerow({
            "id": c.id,
            "full_name": c.full_name,
            "role": c.role.value,
            "designation": c.designation_raw or "",
            "college": c.college.name,
            "email": c.email or "",
            "status": c.status.value,
            "confidence": c.confidence,
            "last_contact_at": c.last_contact_at.isoformat() if c.last_contact_at else "",
            "created_at": c.created_at.isoformat() if hasattr(c, 'created_at') and c.created_at else "",
        })

    filename = lst.name.replace(" ", "_").lower() + "_contacts.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- campaign attachments ----------

def _campaign_attachment_dict(att: Attachment) -> dict:
    return {
        "id": att.id,
        "filename": att.original_filename,
        "original_filename": att.original_filename,
        "mime_type": att.mime_type,
        "size": att.size,
        "uploaded_at": att.uploaded_at,
    }


@router.get("/campaigns/{campaign_id}/attachments")
def list_campaign_attachments(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    rows = db.query(Attachment).filter_by(campaign_id=campaign_id).order_by(Attachment.id).all()
    return {"items": [_campaign_attachment_dict(a) for a in rows]}


@router.post("/campaigns/{campaign_id}/attachments", status_code=201)
async def upload_campaign_attachments(
    campaign_id: int,
    files: list[UploadFile] = File(...),
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    from app.sender.storage import delete_file, read_upload, save_bytes

    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if not files:
        raise HTTPException(422, "No files uploaded")
    max_per = get_settings().max_attachments_per_draft
    existing = db.query(Attachment).filter_by(campaign_id=campaign_id).count()
    if existing + len(files) > max_per:
        raise HTTPException(422, f"Maximum {max_per} attachments per campaign")

    created: list[dict] = []
    saved_paths: list[str] = []
    try:
        for upload in files:
            content, original, stored_name, mime_type = await read_upload(upload)
            storage_path = save_bytes(content, stored_name)
            saved_paths.append(storage_path)
            row = Attachment(
                campaign_id=campaign_id,
                draft_id=None,
                filename=stored_name,
                original_filename=original,
                mime_type=mime_type,
                size=len(content),
                storage_path=storage_path,
            )
            db.add(row)
            db.flush()
            created.append(_campaign_attachment_dict(row))
        db.commit()
    except Exception:
        db.rollback()
        for path in saved_paths:
            delete_file(path)
        raise
    return {"items": created}


@router.delete("/campaigns/{campaign_id}/attachments/{attachment_id}")
def delete_campaign_attachment(
    campaign_id: int,
    attachment_id: int,
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    from app.sender.storage import delete_file

    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    att = db.get(Attachment, attachment_id)
    if not att or att.campaign_id != campaign_id:
        raise HTTPException(404, "Attachment not found")
    delete_file(att.storage_path)
    db.delete(att)
    db.commit()
    return {"ok": True}


@router.put("/campaigns/{campaign_id}/attachments/{attachment_id}")
async def replace_campaign_attachment(
    campaign_id: int,
    attachment_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    from app.sender.storage import delete_file, read_upload, save_bytes

    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    att = db.get(Attachment, attachment_id)
    if not att or att.campaign_id != campaign_id:
        raise HTTPException(404, "Attachment not found")

    content, original, stored_name, mime_type = await read_upload(file)
    old_path = att.storage_path
    att.filename = stored_name
    att.original_filename = original
    att.mime_type = mime_type
    att.size = len(content)
    att.storage_path = save_bytes(content, stored_name)
    db.commit()
    delete_file(old_path)
    return _campaign_attachment_dict(att)


# ---------- list-level campaign attachments ----------

@router.get("/lists/{list_id}/attachments")
def list_list_attachments(list_id: int, db: Session = Depends(get_db)):
    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    rows = db.query(Attachment).filter_by(list_id=list_id, campaign_id=None, draft_id=None).order_by(Attachment.id).all()
    return {"items": [_campaign_attachment_dict(a) for a in rows]}


@router.post("/lists/{list_id}/attachments", status_code=201)
async def upload_list_attachments(
    list_id: int,
    files: list[UploadFile] = File(...),
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    from app.sender.storage import delete_file, read_upload, save_bytes

    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    if not files:
        raise HTTPException(422, "No files uploaded")
    max_per = get_settings().max_attachments_per_draft
    existing = db.query(Attachment).filter_by(list_id=list_id, campaign_id=None, draft_id=None).count()
    if existing + len(files) > max_per:
        raise HTTPException(422, f"Maximum {max_per} attachments per list")

    created: list[dict] = []
    saved_paths: list[str] = []
    try:
        for upload in files:
            content, original, stored_name, mime_type = await read_upload(upload)
            storage_path = save_bytes(content, stored_name)
            saved_paths.append(storage_path)
            row = Attachment(
                list_id=list_id,
                draft_id=None,
                campaign_id=None,
                filename=stored_name,
                original_filename=original,
                mime_type=mime_type,
                size=len(content),
                storage_path=storage_path,
            )
            db.add(row)
            db.flush()
            created.append(_campaign_attachment_dict(row))
        db.commit()
    except Exception:
        db.rollback()
        for path in saved_paths:
            delete_file(path)
        raise
    return {"items": created}


@router.delete("/lists/{list_id}/attachments/{attachment_id}")
def delete_list_attachment(
    list_id: int,
    attachment_id: int,
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    from app.sender.storage import delete_file

    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    att = db.get(Attachment, attachment_id)
    if not att or att.list_id != list_id or att.campaign_id is not None or att.draft_id is not None:
        raise HTTPException(404, "Attachment not found")
    delete_file(att.storage_path)
    db.delete(att)
    db.commit()
    return {"ok": True}


@router.put("/lists/{list_id}/attachments/{attachment_id}")
async def replace_list_attachment(
    list_id: int,
    attachment_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    from app.sender.storage import delete_file, read_upload, save_bytes

    lst = db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(404, "List not found")
    att = db.get(Attachment, attachment_id)
    if not att or att.list_id != list_id or att.campaign_id is not None or att.draft_id is not None:
        raise HTTPException(404, "Attachment not found")

    content, original, stored_name, mime_type = await read_upload(file)
    old_path = att.storage_path
    att.filename = stored_name
    att.original_filename = original
    att.mime_type = mime_type
    att.size = len(content)
    att.storage_path = save_bytes(content, stored_name)
    db.commit()
    delete_file(old_path)
    return _campaign_attachment_dict(att)


# ---------- attachment download / preview ----------

@router.get("/attachments/{attachment_id}/file")
def get_attachment_file(attachment_id: int, download: bool = False, db: Session = Depends(get_db)):
    from app.sender.storage import read_bytes
    from fastapi.responses import Response
    att = db.get(Attachment, attachment_id)
    if not att:
        raise HTTPException(404, "Attachment not found")
    content = read_bytes(att.storage_path)
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{att.original_filename}"'
    else:
        headers["Content-Disposition"] = f'inline; filename="{att.original_filename}"'
    return Response(
        content=content,
        media_type=att.mime_type,
        headers=headers,
    )
