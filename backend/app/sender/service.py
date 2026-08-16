"""Send service: the ONLY code path that dispatches email.

Non-negotiables enforced here, at send time, regardless of what was queued:
  1. suppression list wins over everything
  2. daily/hourly caps (DB-counted, so restarts can't reset them)
  3. only APPROVED drafts with passing lint leave the building
  4. every send is recorded (email_messages + audit implicitly via status)
  5. sending schedules the follow-up sequence; any bounce/unsubscribe
     cancels it and suppresses the address
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Attachment,
    Contact,
    ContactStatus,
    DraftStatus,
    EmailDraft,
    EmailEvent,
    EmailEventType,
    EmailMessage,
    FollowupSchedule,
    FollowupStatus,
    MessageStatus,
    SuppressionEntry,
    SuppressionReason,
)
from app.personalize.lint import UNSUBSCRIBE_TOKEN
from app.sender.links import unsubscribe_url
from app.sender.providers import EmailAttachment, EmailSenderProvider, OutgoingEmail
from app.sender.storage import read_bytes


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_suppressed(db: Session, email: str) -> bool:
    return (
        db.query(SuppressionEntry).filter(func.lower(SuppressionEntry.email) == email.lower()).count() > 0
    )


def sent_in_window(db: Session, since: datetime) -> int:
    return (
        db.query(EmailMessage)
        .filter(EmailMessage.sent_at >= since, EmailMessage.status != MessageStatus.FAILED)
        .count()
    )


def remaining_quota(db: Session) -> int:
    s = get_settings()
    now = _utcnow()
    daily_left = s.daily_send_cap - sent_in_window(db, now - timedelta(days=1))
    hourly_left = s.hourly_send_cap - sent_in_window(db, now - timedelta(hours=1))
    return max(0, min(daily_left, hourly_left))


def render_body(draft: EmailDraft, contact: Contact) -> str:
    return (draft.body_text or "").replace(UNSUBSCRIBE_TOKEN, unsubscribe_url(contact.id))


def load_draft_attachments(db: Session, draft_id: int) -> list[EmailAttachment]:
    rows = db.query(Attachment).filter_by(draft_id=draft_id).order_by(Attachment.id).all()
    return [
        EmailAttachment(
            filename=a.original_filename,
            content=read_bytes(a.storage_path),
            mime_type=a.mime_type,
        )
        for a in rows
    ]


def send_approved_batch(
    db: Session,
    provider: EmailSenderProvider,
    limit: int | None = None,
    contact_ids: list[int] | None = None,
    from_name: str | None = None,
    from_email: str | None = None,
) -> dict:
    """Send approved drafts up to quota. Returns counters for the operator."""
    s = get_settings()
    sender_name = from_name or s.sender_name or "AIValytics"
    sender_email = from_email or s.sender_email
    quota = remaining_quota(db)
    if limit is not None:
        quota = min(quota, limit)

    stats = {"sent": 0, "suppressed": 0, "failed": 0, "quota_left": quota}
    if quota <= 0:
        return stats

    if contact_ids is not None and not contact_ids:
        stats["quota_left"] = remaining_quota(db)
        return stats

    query = db.query(EmailDraft).filter(EmailDraft.status == DraftStatus.APPROVED)
    if contact_ids is not None:
        query = query.filter(EmailDraft.contact_id.in_(contact_ids))
    drafts = query.order_by(EmailDraft.approved_at).limit(quota).all()
    for draft in drafts:
        contact = db.get(Contact, draft.contact_id)
        if not contact or not contact.email:
            continue
        if is_suppressed(db, contact.email):
            stats["suppressed"] += 1
            draft.status = DraftStatus.REJECTED
            db.commit()
            continue

        result = provider.send(
            OutgoingEmail(
                to=contact.email,
                subject=draft.chosen_subject or (draft.subject_options or ["(no subject)"])[0],
                body_text=render_body(draft, contact),
                from_name=sender_name,
                from_email=sender_email,
                attachments=load_draft_attachments(db, draft.id),
            )
        )
        message = EmailMessage(
            draft_id=draft.id,
            contact_id=contact.id,
            provider=provider.name,
            provider_message_id=result.provider_message_id,
            status=MessageStatus.SENT if result.ok else MessageStatus.FAILED,
            error=result.error,
        )
        db.add(message)
        if result.ok:
            draft.status = DraftStatus.SENT
            contact.status = ContactStatus.CONTACTED
            contact.last_contact_at = _utcnow()
            if draft.touch_number == 1:
                _schedule_followups(db, contact)
            stats["sent"] += 1
        else:
            stats["failed"] += 1
        db.commit()
    stats["quota_left"] = remaining_quota(db)
    return stats


def _schedule_followups(db: Session, contact: Contact) -> None:
    s = get_settings()
    now = _utcnow()
    existing = {
        f.touch_number
        for f in db.query(FollowupSchedule).filter_by(contact_id=contact.id).all()
    }
    for offset, days in enumerate(s.followup_days, start=2):
        if offset not in existing:
            db.add(FollowupSchedule(
                contact_id=contact.id, touch_number=offset,
                scheduled_for=now + timedelta(days=days),
            ))
    contact.next_followup_at = now + timedelta(days=s.followup_days[0])


def _cancel_followups(db: Session, contact_id: int, reason: str) -> None:
    for f in (
        db.query(FollowupSchedule)
        .filter_by(contact_id=contact_id, status=FollowupStatus.PENDING)
        .all()
    ):
        f.status = FollowupStatus.CANCELLED
        f.cancelled_reason = reason


def record_bounce(db: Session, email: str, detail: str = "") -> None:
    """Hard bounce: suppress the address, mark contact + latest message."""
    if not is_suppressed(db, email):
        db.add(SuppressionEntry(email=email.lower(), reason=SuppressionReason.HARD_BOUNCE,
                                detail=detail[:300] or None))
    for contact in db.query(Contact).filter(func.lower(Contact.email) == email.lower()).all():
        contact.status = ContactStatus.BOUNCED
        _cancel_followups(db, contact.id, "bounced")
        message = (
            db.query(EmailMessage)
            .filter_by(contact_id=contact.id)
            .order_by(EmailMessage.sent_at.desc())
            .first()
        )
        if message:
            message.status = MessageStatus.BOUNCED
            db.add(EmailEvent(message_id=message.id, event_type=EmailEventType.BOUNCE,
                              meta={"detail": detail[:300]}))
    db.commit()


def record_unsubscribe(db: Session, contact_id: int) -> bool:
    """Suppress + cancel follow-ups. Returns False for unknown contact."""
    contact = db.get(Contact, contact_id)
    if not contact:
        return False
    if contact.email and not is_suppressed(db, contact.email):
        db.add(SuppressionEntry(email=contact.email.lower(),
                                reason=SuppressionReason.UNSUBSCRIBED))
    contact.status = ContactStatus.UNSUBSCRIBED
    _cancel_followups(db, contact.id, "unsubscribed")
    message = (
        db.query(EmailMessage)
        .filter_by(contact_id=contact.id)
        .order_by(EmailMessage.sent_at.desc())
        .first()
    )
    if message:
        db.add(EmailEvent(message_id=message.id, event_type=EmailEventType.UNSUBSCRIBE))
    db.commit()
    return True
