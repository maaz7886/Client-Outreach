"""End-to-end pipeline test: one college travels the entire system —
CSV import → research → contact discovery → draft → approval → send →
open tracking → reply → follow-up cancellation → stats — with the website
and LLM mocked, everything else real (SQLite, real API app, real services)."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.sender.links as links_mod
import app.sender.service as service_mod
from app.api.main import create_app
from app.contacts.engine import discover_contacts
from app.core.config import Settings
from app.core.db import get_db
from app.core.security import hash_password
from app.discovery.importer import import_colleges_csv
from app.followups.runner import run_due_followups
from app.models import (
    Base, College, Contact, ContactStatus, DraftStatus, EmailDraft,
    FollowupSchedule, FollowupStatus, ResearchStatus, User, UserRole,
)
from app.personalize.engine import generate_draft
from app.personalize.lint import UNSUBSCRIBE_TOKEN
from app.research.engine import RESEARCH_FIELDS, research_college
from app.research.fetcher import PoliteFetcher
from app.sender.providers import SendResult
from app.sender.service import send_approved_batch

TEST_SETTINGS = Settings(jwt_secret="e2e-secret", sender_name="Maaz",
                         sender_email="maaz@outreach.example",
                         daily_send_cap=100, hourly_send_cap=100, _env_file=None)

CSV = ("Institute Name,District,State Name,Website\n"
       "ABC College of Engineering,Pune,Maharashtra,https://abc-college.example/\n")

SITE = {
    "https://abc-college.example/robots.txt": httpx.Response(404),
    "https://abc-college.example/": httpx.Response(
        200,
        text='<a href="/placement">Placement Cell</a>'
             "<p>ABC College of Engineering, Pune. NAAC A+ institute.</p>",
        headers={"content-type": "text/html"},
    ),
    "https://abc-college.example/placement": httpx.Response(
        200,
        text="<p>Training and Placement Cell runs AI workshops with industry "
             "partners. Officer: Dr. Anil Kumar, Training and Placement Officer. "
             "Email: tpo@abc-college.ac.in Phone: +91 98765 43210</p>",
        headers={"content-type": "text/html"},
    ),
}

GOOD_BODY = (
    "Dear Dr. Anil Kumar,\n\nI came across ABC College of Engineering's AI "
    "workshops with industry partners and wanted to reach out. AI literacy is "
    "becoming a baseline expectation in campus placements, and hands-on exposure "
    "gives students a real edge in interviews and internships alike.\n\nWe run "
    "practical, industry-focused, interactive guest sessions on Artificial "
    "Intelligence, tailored to your students, at no cost to the institution.\n\n"
    "Would you be open to a short call to see if this fits your training "
    f"calendar?\n\nWarm regards,\nMaaz\nAIValytics\n\nUnsubscribe: {UNSUBSCRIBE_TOKEN}"
)


class RoutedLLM:
    """One fake LLM, routed by prompt type — mirrors how the real provider is
    shared across engines."""

    name = "routed-fake"

    def complete(self, system, user, *, max_tokens=2048):
        if "research analyst" in system:
            payload = {f: {"value": "NOT_FOUND", "source_url": None} for f in RESEARCH_FIELDS}
            payload["placement_activities"] = {
                "value": "Runs AI workshops with industry partners.",
                "source_url": "https://abc-college.example/placement",
            }
            return json.dumps(payload)
        if "extract people" in system:
            return json.dumps([{
                "full_name": "Dr. Anil Kumar",
                "designation": "Training and Placement Officer",
                "department": "Placement Cell",
                "email": "tpo@abc-college.ac.in",
                "phone": "+91 98765 43210",
            }])
        if "outreach emails" in system:
            return json.dumps({
                "subject_options": [
                    "AI guest lecture for ABC College students",
                    "Practical AI session for ABC College, Pune",
                    "Industry AI workshop proposal - ABC College",
                    "Helping ABC College students prepare for AI hiring",
                    "AI workshop for your training calendar",
                ],
                "body_text": GOOD_BODY,
            })
        if "Classify a reply" in system:
            return "POSITIVE"
        raise AssertionError(f"Unrouted prompt: {system[:80]}")


class CapturingProvider:
    name = "capture"

    def __init__(self):
        self.sent = []

    def send(self, email):
        self.sent.append(email)
        return SendResult(ok=True, provider_message_id=f"m{len(self.sent)}")


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setattr(service_mod, "get_settings", lambda: TEST_SETTINGS)
    monkeypatch.setattr(links_mod, "get_settings", lambda: TEST_SETTINGS)
    monkeypatch.setattr("app.core.security.get_settings", lambda: TEST_SETTINGS)
    monkeypatch.setattr("app.personalize.engine.get_settings", lambda: TEST_SETTINGS)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    api = create_app()

    def _get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    api.dependency_overrides[get_db] = _get_db
    return factory, TestClient(api)


def make_fetcher():
    def handler(request):
        return SITE.get(str(request.url), httpx.Response(404))

    return PoliteFetcher(delay_seconds=0, transport=httpx.MockTransport(handler),
                         sleep=lambda s: None)


def test_full_pipeline(env):
    factory, api = env
    llm = RoutedLLM()

    with factory() as db:
        # 1. import
        result = import_colleges_csv(db, CSV, source_label="e2e.csv")
        assert result["inserted"] == 1
        college = db.query(College).one()

        # 2. research
        record = research_college(db, college, make_fetcher(), llm)
        assert record.status is ResearchStatus.DONE
        assert record.summary["placement_activities"]["value"].startswith("Runs AI")

        # 3. contact discovery
        contacts = discover_contacts(db, college, make_fetcher(), llm,
                                     mx_lookup=lambda d: True)
        assert len(contacts) == 1
        contact = contacts[0]
        assert contact.status is ContactStatus.VERIFIED
        assert contact.confidence >= 95

        # 4. draft generation (grounded in the research record)
        draft = generate_draft(db, contact, llm)
        assert draft.lint_report["ok"]

        # 5. human approval via the real API
        db.add(User(email="op@x.com", full_name="Op",
                    hashed_password=hash_password("pw123456"), role=UserRole.OPERATOR))
        db.commit()
        contact_id, draft_id = contact.id, draft.id

    token = api.post("/auth/login", json={"email": "op@x.com", "password": "pw123456"}) \
        .json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert api.post(f"/api/drafts/{draft_id}/approve", headers=headers).status_code == 200

    # 6. send
    provider = CapturingProvider()
    with factory() as db:
        stats = send_approved_batch(db, provider)
        assert stats["sent"] == 1
        outgoing = provider.sent[0]
        assert outgoing.to == "tpo@abc-college.ac.in"
        assert UNSUBSCRIBE_TOKEN not in outgoing.body_text
        assert db.query(FollowupSchedule).count() == 3  # day 3/7/14 scheduled

    # 7. open tracking via the real public endpoint
    with factory() as db:
        from app.models import EmailMessage
        message_id = db.query(EmailMessage).one().id
    assert api.get(f"/t/o/{message_id}.gif").status_code == 200

    # 8. positive reply via the real API -> follow-ups cancelled
    resp = api.post("/api/replies", headers=headers,
                    json={"contact_id": contact_id,
                          "text": "Sounds interesting, please share dates."})
    assert resp.json() == {"sentiment": "POSITIVE",
                           "contact_status": "REPLIED_POSITIVE"}

    # 9. the reply itself already cancelled the sequence; the runner then
    # finds nothing pending and drafts nothing
    with factory() as db:
        assert all(f.status is FollowupStatus.CANCELLED
                   for f in db.query(FollowupSchedule).all())
        db.query(FollowupSchedule).update(
            {"scheduled_for": datetime.now(timezone.utc) - timedelta(hours=1)})
        db.commit()
        run_stats = run_due_followups(db, llm)
        assert run_stats == {"drafted": 0, "completed": 0, "cancelled": 0}
        assert db.query(EmailDraft).filter(EmailDraft.touch_number > 1).count() == 0

    # 10. stats reflect the journey
    stats = api.get("/api/stats", headers=headers).json()
    assert stats["colleges"] == 1
    assert stats["emails_sent"] == 1
    assert stats["open_rate"] == 1.0
    assert stats["reply_rate"] == 1.0
    assert stats["positive"] == 1


def test_pipeline_no_reply_generates_followup(env):
    """Variant: contact never replies -> due follow-up produces a touch-2 draft
    in the approval queue, and the 3-touch cap holds."""
    factory, _ = env
    llm = RoutedLLM()

    with factory() as db:
        import_colleges_csv(db, CSV, source_label="e2e.csv")
        college = db.query(College).one()
        research_college(db, college, make_fetcher(), llm)
        contact = discover_contacts(db, college, make_fetcher(), llm,
                                    mx_lookup=lambda d: True)[0]
        draft = generate_draft(db, contact, llm)
        from app.personalize.engine import approve_draft
        approve_draft(db, draft, user_id=None)
        send_approved_batch(db, CapturingProvider())

        db.query(FollowupSchedule).filter_by(touch_number=2).update(
            {"scheduled_for": datetime.now(timezone.utc) - timedelta(hours=1)})
        db.commit()

        run_stats = run_due_followups(db, llm)
        assert run_stats["drafted"] == 1
        followup = db.query(EmailDraft).filter_by(touch_number=2).one()
        assert followup.status is DraftStatus.DRAFT  # awaits human approval

        # the DB constraint is the final backstop on touch count
        from sqlalchemy.exc import IntegrityError
        db.add(EmailDraft(contact_id=contact.id, touch_number=5))
        with pytest.raises(IntegrityError):
            db.commit()
