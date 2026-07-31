"""Phase 6 tests: suppression wins at send time, caps are DB-counted,
unsubscribe links sign/verify, bounces and unsubscribes cancel follow-ups."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.sender.links as links_mod
import app.sender.service as service_mod
from app.core.config import Settings
from app.models import (
    Base,
    CanonicalRole,
    College,
    Contact,
    ContactStatus,
    DraftStatus,
    EmailDraft,
    EmailMessage,
    FollowupSchedule,
    FollowupStatus,
    MessageStatus,
    SuppressionEntry,
    SuppressionReason,
)
from app.personalize.lint import UNSUBSCRIBE_TOKEN
from app.sender.links import unsubscribe_token, verify_unsubscribe_token
from app.sender.providers import SendResult
from app.sender.service import (
    record_bounce,
    record_unsubscribe,
    send_approved_batch,
)

TEST_SETTINGS = Settings(
    jwt_secret="test-secret",
    public_base_url="https://outreach.aivalytics.example",
    sender_name="Maaz Patel",
    sender_email="maaz@outreach.aivalytics.example",
    daily_send_cap=10,
    hourly_send_cap=10,
    _env_file=None,
)


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setattr(service_mod, "get_settings", lambda: TEST_SETTINGS)
    monkeypatch.setattr(links_mod, "get_settings", lambda: TEST_SETTINGS)
    return TEST_SETTINGS


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class FakeProvider:
    name = "fake"

    def __init__(self, fail_for: set[str] | None = None):
        self.sent = []
        self.fail_for = fail_for or set()

    def send(self, email):
        if email.to in self.fail_for:
            return SendResult(ok=False, error="boom")
        self.sent.append(email)
        return SendResult(ok=True, provider_message_id=f"msg-{len(self.sent)}")


def make_contact(db, email="tpo@abc.ac.in", name="Dr. Anil Kumar") -> Contact:
    college = db.query(College).first()
    if college is None:
        college = College(name="ABC College", normalized_name="abc college",
                          city="Pune", state="Maharashtra")
        db.add(college)
        db.flush()
    contact = Contact(college_id=college.id, full_name=name, role=CanonicalRole.TPO,
                      email=email, confidence=95, status=ContactStatus.VERIFIED)
    db.add(contact)
    db.flush()
    return contact


def make_approved_draft(db, contact, touch=1) -> EmailDraft:
    draft = EmailDraft(
        contact_id=contact.id, touch_number=touch,
        subject_options=["s1", "s2", "s3", "s4", "s5"], chosen_subject="s1",
        body_text=f"Hello ABC College.\n\nUnsubscribe: {UNSUBSCRIBE_TOKEN}",
        lint_report={"ok": True, "errors": [], "warnings": []},
        status=DraftStatus.APPROVED,
    )
    db.add(draft)
    db.commit()
    return draft


# ---------- links ----------

def test_unsubscribe_token_roundtrip_and_tamper():
    token = unsubscribe_token(42)
    assert verify_unsubscribe_token(token) == 42
    assert verify_unsubscribe_token(token[:-1] + "0") is None
    assert verify_unsubscribe_token("999." + token.split(".")[1]) is None
    assert verify_unsubscribe_token("garbage") is None


# ---------- sending ----------

def test_send_batch_happy_path(db):
    contact = make_contact(db)
    make_approved_draft(db, contact)
    provider = FakeProvider()

    stats = send_approved_batch(db, provider)

    assert stats["sent"] == 1
    outgoing = provider.sent[0]
    assert outgoing.to == contact.email
    assert UNSUBSCRIBE_TOKEN not in outgoing.body_text
    assert f"/u/{unsubscribe_token(contact.id)}" in outgoing.body_text

    assert db.query(EmailDraft).one().status is DraftStatus.SENT
    assert db.query(EmailMessage).one().status is MessageStatus.SENT
    db.refresh(contact)
    assert contact.status is ContactStatus.CONTACTED
    followups = db.query(FollowupSchedule).filter_by(contact_id=contact.id).all()
    assert sorted(f.touch_number for f in followups) == [2, 3, 4]


def test_suppressed_address_never_sent_even_if_queued(db):
    contact = make_contact(db)
    draft = make_approved_draft(db, contact)
    db.add(SuppressionEntry(email=contact.email.upper().lower(),
                            reason=SuppressionReason.UNSUBSCRIBED))
    db.commit()
    provider = FakeProvider()

    stats = send_approved_batch(db, provider)

    assert provider.sent == []
    assert stats["suppressed"] == 1
    assert draft.status is DraftStatus.REJECTED


def test_daily_cap_enforced(db, settings, monkeypatch):
    capped = settings.model_copy(update={"daily_send_cap": 2})
    monkeypatch.setattr(service_mod, "get_settings", lambda: capped)
    for i in range(3):
        make_approved_draft(db, make_contact(db, email=f"tpo{i}@abc.ac.in", name=f"Dr {i}"))
    provider = FakeProvider()

    stats = send_approved_batch(db, provider)

    assert stats["sent"] == 2
    assert stats["quota_left"] == 0
    # a second run sends nothing more today
    assert send_approved_batch(db, provider)["sent"] == 0


def test_failed_send_recorded_and_draft_stays_approved(db):
    contact = make_contact(db)
    draft = make_approved_draft(db, contact)
    provider = FakeProvider(fail_for={contact.email})

    stats = send_approved_batch(db, provider)

    assert stats["failed"] == 1
    assert draft.status is DraftStatus.APPROVED  # retryable next run
    message = db.query(EmailMessage).one()
    assert message.status is MessageStatus.FAILED
    assert message.error == "boom"


# ---------- bounce / unsubscribe ----------

def test_bounce_suppresses_and_cancels_followups(db):
    contact = make_contact(db)
    make_approved_draft(db, contact)
    send_approved_batch(db, FakeProvider())

    record_bounce(db, contact.email, detail="550 user unknown")

    db.refresh(contact)
    assert contact.status is ContactStatus.BOUNCED
    assert db.query(SuppressionEntry).filter_by(email=contact.email).one().reason \
        is SuppressionReason.HARD_BOUNCE
    assert all(
        f.status is FollowupStatus.CANCELLED
        for f in db.query(FollowupSchedule).filter_by(contact_id=contact.id)
    )
    assert db.query(EmailMessage).one().status is MessageStatus.BOUNCED


def test_unsubscribe_suppresses_and_cancels(db):
    contact = make_contact(db)
    make_approved_draft(db, contact)
    send_approved_batch(db, FakeProvider())

    assert record_unsubscribe(db, contact.id) is True
    db.refresh(contact)
    assert contact.status is ContactStatus.UNSUBSCRIBED
    assert db.query(SuppressionEntry).count() == 1
    assert all(
        f.status is FollowupStatus.CANCELLED
        for f in db.query(FollowupSchedule).filter_by(contact_id=contact.id)
    )
    # a later queued draft for the same address can never go out
    draft2 = make_approved_draft(db, contact, touch=2)
    stats = send_approved_batch(db, FakeProvider())
    assert stats["suppressed"] == 1 and stats["sent"] == 0
    assert record_unsubscribe(db, 99999) is False
