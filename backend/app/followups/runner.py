"""Follow-up runner: for each due schedule whose contact never replied,
generate the next-touch draft (which enters the normal approval queue) and
reconcile schedules whose drafts have been sent.

Run daily (Celery beat in production, `python -m app.cli followups` manually).
The 4-touch DB constraint makes overshooting impossible."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.models import (
    Contact,
    ContactStatus,
    DraftStatus,
    EmailDraft,
    FollowupSchedule,
    FollowupStatus,
)
from app.personalize.engine import generate_draft


def run_due_followups(db: Session, llm: LLMProvider) -> dict:
    now = datetime.now(timezone.utc)
    stats = {"drafted": 0, "completed": 0, "cancelled": 0}

    due = (
        db.query(FollowupSchedule)
        .filter(FollowupSchedule.status == FollowupStatus.PENDING,
                FollowupSchedule.scheduled_for <= now)
        .all()
    )
    for schedule in due:
        contact = db.get(Contact, schedule.contact_id)
        if contact is None or contact.status is not ContactStatus.CONTACTED:
            # replied, bounced, unsubscribed, meeting booked... -> no follow-up
            schedule.status = FollowupStatus.CANCELLED
            schedule.cancelled_reason = (
                f"contact status {contact.status.value}" if contact else "contact missing"
            )
            stats["cancelled"] += 1
            db.commit()
            continue

        draft = (
            db.query(EmailDraft)
            .filter_by(contact_id=contact.id, touch_number=schedule.touch_number)
            .one_or_none()
        )
        if draft is None:
            generate_draft(db, contact, llm, touch_number=schedule.touch_number)
            stats["drafted"] += 1
        elif draft.status is DraftStatus.SENT:
            schedule.status = FollowupStatus.SENT
            stats["completed"] += 1
            db.commit()
    return stats
