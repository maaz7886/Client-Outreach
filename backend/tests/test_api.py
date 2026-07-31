"""Phase 7 tests: auth, public unsubscribe/tracking, CRM endpoints, reply
classification, follow-up runner. FastAPI TestClient over SQLite."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.sender.links as links_mod
import app.sender.service as service_mod
from app.api.main import create_app
from app.core.config import Settings
from app.core.db import get_db
from app.core.security import hash_password
from app.models import (
    Base,
    CanonicalRole,
    College,
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
    User,
    UserRole,
)
from app.personalize.lint import UNSUBSCRIBE_TOKEN
from app.sender.links import unsubscribe_token

TEST_SETTINGS = Settings(jwt_secret="test-secret", _env_file=None)


@pytest.fixture()
def db_session(monkeypatch):
    monkeypatch.setattr(service_mod, "get_settings", lambda: TEST_SETTINGS)
    monkeypatch.setattr(links_mod, "get_settings", lambda: TEST_SETTINGS)
    monkeypatch.setattr("app.core.security.get_settings", lambda: TEST_SETTINGS)
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session, factory


@pytest.fixture()
def client(db_session):
    session, factory = db_session
    app = create_app()

    def _get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app), session


def seed_user(db, role=UserRole.ADMIN) -> User:
    user = User(email="maaz@aivalytics.example", full_name="Maaz",
                hashed_password=hash_password("secret123"), role=role)
    db.add(user)
    db.commit()
    return user


def login(client) -> dict:
    resp = client.post("/auth/login",
                       json={"email": "maaz@aivalytics.example", "password": "secret123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def seed_pipeline(db):
    college = College(name="ABC College", normalized_name="abc college",
                      city="Pune", state="Maharashtra")
    db.add(college)
    db.flush()
    contact = Contact(college_id=college.id, full_name="Dr. Anil Kumar",
                      role=CanonicalRole.TPO, email="tpo@abc.ac.in",
                      confidence=95, status=ContactStatus.VERIFIED)
    db.add(contact)
    db.flush()
    draft = EmailDraft(contact_id=contact.id, touch_number=1,
                       subject_options=["a", "b", "c", "d", "e"], chosen_subject="a",
                       body_text="Hello ABC College. " + "x" * 400
                                 + f"\nUnsubscribe: {UNSUBSCRIBE_TOKEN}",
                       lint_report={"ok": True, "errors": [], "warnings": []})
    db.add(draft)
    db.commit()
    return college, contact, draft


# ---------- auth ----------

def test_login_and_reject_bad_password(client):
    api, db = client
    seed_user(db)
    assert api.post("/auth/login", json={"email": "maaz@aivalytics.example",
                                         "password": "wrong"}).status_code == 401
    headers = login(api)
    assert api.get("/api/stats", headers=headers).status_code == 200


def test_endpoints_require_token(client):
    api, _ = client
    assert api.get("/api/stats").status_code == 401
    assert api.get("/api/colleges").status_code == 401


def test_viewer_cannot_mutate(client):
    api, db = client
    seed_user(db, role=UserRole.VIEWER)
    _, contact, draft = seed_pipeline(db)
    headers = login(api)
    assert api.get("/api/drafts", headers=headers).status_code == 200
    assert api.post(f"/api/drafts/{draft.id}/approve", headers=headers).status_code == 403
    assert api.patch(f"/api/contacts/{contact.id}", headers=headers,
                     json={"notes": "x"}).status_code == 403


# ---------- CRM ----------

def test_college_and_contact_listing(client):
    api, db = client
    seed_user(db)
    seed_pipeline(db)
    headers = login(api)
    colleges = api.get("/api/colleges?state=maharashtra", headers=headers).json()
    assert colleges["total"] == 1
    detail = api.get(f"/api/colleges/{colleges['items'][0]['id']}", headers=headers).json()
    assert detail["contacts"][0]["email"] == "tpo@abc.ac.in"
    contacts = api.get("/api/contacts?status=verified", headers=headers).json()
    assert contacts["total"] == 1


def test_draft_edit_relints_and_approve_flow(client):
    api, db = client
    seed_user(db)
    _, _, draft = seed_pipeline(db)
    headers = login(api)

    # edit body to something that fails lint -> approve must 409
    resp = api.patch(f"/api/drafts/{draft.id}", headers=headers,
                     json={"body_text": "too short, no token"})
    assert resp.status_code == 200 and not resp.json()["lint"]["ok"]
    assert api.post(f"/api/drafts/{draft.id}/approve", headers=headers).status_code == 409

    # restore a good body -> approve works, second approve 409s
    good = "Hello ABC College. " + "y" * 400 + f"\nUnsubscribe: {UNSUBSCRIBE_TOKEN}"
    api.patch(f"/api/drafts/{draft.id}", headers=headers, json={"body_text": good})
    assert api.post(f"/api/drafts/{draft.id}/approve", headers=headers).status_code == 200
    assert api.post(f"/api/drafts/{draft.id}/approve", headers=headers).status_code == 409


def test_manual_status_guardrail(client):
    api, db = client
    seed_user(db)
    _, contact, _ = seed_pipeline(db)
    headers = login(api)
    assert api.patch(f"/api/contacts/{contact.id}", headers=headers,
                     json={"status": "meeting_scheduled"}).status_code == 200
    # pipeline-owned status cannot be set by hand
    assert api.patch(f"/api/contacts/{contact.id}", headers=headers,
                     json={"status": "contacted"}).status_code == 422


# ---------- public endpoints ----------

def test_unsubscribe_endpoint(client):
    api, db = client
    _, contact, _ = seed_pipeline(db)
    assert api.get("/u/tampered.token").status_code == 404
    resp = api.get(f"/u/{unsubscribe_token(contact.id)}")
    assert resp.status_code == 200 and "unsubscribed" in resp.text.lower()
    db.expire_all()
    assert db.get(Contact, contact.id).status is ContactStatus.UNSUBSCRIBED


def test_open_pixel_and_click_tracking(client):
    api, db = client
    _, contact, draft = seed_pipeline(db)
    message = EmailMessage(draft_id=draft.id, contact_id=contact.id,
                           provider="fake", status=MessageStatus.SENT)
    db.add(message)
    db.commit()

    pixel = api.get(f"/t/o/{message.id}.gif")
    assert pixel.status_code == 200 and pixel.headers["content-type"] == "image/gif"
    click = api.get(f"/t/c/{message.id}", params={"url": "https://aivalytics.example"},
                    follow_redirects=False)
    assert click.status_code == 302
    assert api.get(f"/t/c/{message.id}", params={"url": "javascript:evil()"},
                   follow_redirects=False).status_code == 400
    db.expire_all()
    events = {e.event_type for e in db.query(EmailEvent).all()}
    assert events == {EmailEventType.OPEN, EmailEventType.CLICK}


# ---------- replies ----------

class FakeLLM:
    name = "fake"

    def __init__(self, answer="POSITIVE"):
        self.answer = answer

    def complete(self, system, user, *, max_tokens=2048):
        return self.answer


def test_reply_classification_and_processing(db_session):
    from app.crm.replies import ReplySentiment, classify_reply, process_reply

    db, _ = db_session
    _, contact, _ = seed_pipeline(db)
    contact.status = ContactStatus.CONTACTED
    db.add(FollowupSchedule(contact_id=contact.id, touch_number=2,
                            scheduled_for=datetime.now(timezone.utc)))
    db.commit()

    # regex catches opt-outs even if the LLM would not
    assert classify_reply("Please REMOVE ME from your list", FakeLLM("POSITIVE")) \
        is ReplySentiment.UNSUBSCRIBE

    sentiment = process_reply(db, contact, "Yes, interested. Call me next week.",
                              FakeLLM("POSITIVE"))
    assert sentiment is ReplySentiment.POSITIVE
    assert contact.status is ContactStatus.REPLIED_POSITIVE
    schedule = db.query(FollowupSchedule).one()
    assert schedule.status is FollowupStatus.CANCELLED


# ---------- follow-up runner ----------

def test_followup_runner_drafts_due_and_cancels_replied(db_session):
    from app.followups.runner import run_due_followups

    db, _ = db_session
    _, contact, draft = seed_pipeline(db)
    contact.status = ContactStatus.CONTACTED
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    db.add(FollowupSchedule(contact_id=contact.id, touch_number=2, scheduled_for=past))

    college2 = College(name="XYZ Institute", normalized_name="xyz institute",
                       city="Nagpur", state="Maharashtra")
    db.add(college2)
    db.flush()
    replied = Contact(college_id=college2.id, full_name="Dr. B", role=CanonicalRole.DEAN,
                      email="dean@xyz.ac.in", status=ContactStatus.REPLIED_POSITIVE)
    db.add(replied)
    db.flush()
    db.add(FollowupSchedule(contact_id=replied.id, touch_number=2, scheduled_for=past))
    db.commit()

    good_body = ("Following up on ABC College note. " + "z" * 400
                 + f"\nUnsubscribe: {UNSUBSCRIBE_TOKEN}")
    llm = FakeLLM(json.dumps({"subject_options": ["a1", "a2", "a3", "a4", "a5"],
                              "body_text": good_body}))
    stats = run_due_followups(db, llm)

    assert stats == {"drafted": 1, "completed": 0, "cancelled": 1}
    touch2 = db.query(EmailDraft).filter_by(contact_id=contact.id, touch_number=2).one()
    assert touch2.status is DraftStatus.DRAFT  # enters the approval queue
    cancelled = db.query(FollowupSchedule).filter_by(contact_id=replied.id).one()
    assert cancelled.status is FollowupStatus.CANCELLED
