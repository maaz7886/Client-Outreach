"""Celery app + pipeline tasks + beat schedule.

Everything a task does goes through the same engine functions the CLI uses —
same grounding guards, same caps, same suppression checks. The beat schedule
automates the cadence; the human approval gate stays in the loop because
`send_batch` only ever sends APPROVED drafts.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("outreach", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # long-running crawl tasks: one at a time
)


def _llm():
    from app.llm.providers import get_provider

    return get_provider(settings.llm_provider, settings.llm_api_key, settings.llm_model)


@celery_app.task(name="pipeline.research_pending", bind=True, max_retries=2)
def research_pending(self, limit: int = 10) -> dict:
    from app.core.db import SessionLocal
    from app.models import College, ResearchStatus, ResearchSummary
    from app.research.engine import research_college
    from app.research.fetcher import PoliteFetcher

    fetcher, llm = PoliteFetcher(), _llm()
    done = 0
    with SessionLocal() as db:
        pending = (
            db.query(College)
            .outerjoin(ResearchSummary)
            .filter((ResearchSummary.id.is_(None))
                    | (ResearchSummary.status.in_(
                        [ResearchStatus.PENDING, ResearchStatus.FAILED])))
            .filter(College.website.isnot(None))
            .limit(limit)
            .all()
        )
        for college in pending:
            research_college(db, college, fetcher, llm)
            done += 1
    return {"researched": done}


@celery_app.task(name="pipeline.discover_pending", bind=True, max_retries=2)
def discover_pending(self, limit: int = 10) -> dict:
    from app.contacts.engine import discover_contacts
    from app.core.db import SessionLocal
    from app.models import College, Contact, ResearchStatus, ResearchSummary
    from app.research.fetcher import PoliteFetcher

    fetcher, llm = PoliteFetcher(), _llm()
    found = 0
    with SessionLocal() as db:
        colleges = (
            db.query(College)
            .join(ResearchSummary)
            .outerjoin(Contact)
            .filter(ResearchSummary.status == ResearchStatus.DONE, Contact.id.is_(None))
            .limit(limit)
            .all()
        )
        for college in colleges:
            found += len(discover_contacts(db, college, fetcher, llm))
    return {"contacts_found": found}


@celery_app.task(name="pipeline.draft_pending")
def draft_pending(limit: int = 20) -> dict:
    from app.core.db import SessionLocal
    from app.models import Contact, ContactStatus, EmailDraft
    from app.personalize.engine import generate_draft

    llm = _llm()
    drafted = 0
    with SessionLocal() as db:
        drafted_ids = db.query(EmailDraft.contact_id).filter(EmailDraft.touch_number == 1)
        contacts = (
            db.query(Contact)
            .filter(Contact.status == ContactStatus.VERIFIED, ~Contact.id.in_(drafted_ids))
            .limit(limit)
            .all()
        )
        for contact in contacts:
            generate_draft(db, contact, llm)
            drafted += 1
    return {"drafted": drafted}


@celery_app.task(name="pipeline.send_batch")
def send_batch() -> dict:
    """Sends only APPROVED drafts, within caps, past the suppression list."""
    from app.core.db import SessionLocal
    from app.sender.providers import SMTPSender
    from app.sender.service import send_approved_batch

    with SessionLocal() as db:
        return send_approved_batch(db, SMTPSender())


@celery_app.task(name="pipeline.run_followups")
def run_followups() -> dict:
    from app.core.db import SessionLocal
    from app.followups.runner import run_due_followups

    with SessionLocal() as db:
        return run_due_followups(db, _llm())


celery_app.conf.beat_schedule = {
    # overnight research/discovery keeps crawling off business hours
    "research-nightly": {"task": "pipeline.research_pending",
                         "schedule": crontab(hour=1, minute=0), "kwargs": {"limit": 25}},
    "discover-nightly": {"task": "pipeline.discover_pending",
                         "schedule": crontab(hour=3, minute=0), "kwargs": {"limit": 25}},
    "draft-morning": {"task": "pipeline.draft_pending",
                      "schedule": crontab(hour=8, minute=0), "kwargs": {"limit": 30}},
    # business-hours sending only (10:00-17:00 IST), caps enforced inside
    "send-hourly": {"task": "pipeline.send_batch",
                    "schedule": crontab(hour="10-17", minute=15)},
    "followups-daily": {"task": "pipeline.run_followups",
                        "schedule": crontab(hour=9, minute=0)},
}
