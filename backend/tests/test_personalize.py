"""Phase 5 tests: lint gate, fact-sheet grounding (NOT_FOUND never reaches the
prompt), draft generation with retry-on-lint-failure, approval rules."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import (
    Base,
    CanonicalRole,
    College,
    Contact,
    ContactStatus,
    DraftStatus,
    ResearchSummary,
    ResearchStatus,
)
from app.personalize.engine import approve_draft, build_fact_sheet, generate_draft
from app.personalize.lint import UNSUBSCRIBE_TOKEN, lint_draft

GOOD_BODY = (
    "Dear Dr. Kumar,\n\n"
    "I came across ABC College's placement cell work on AI workshops with industry "
    "partners, and it aligns closely with what we do. AI literacy is quickly becoming "
    "a baseline expectation in campus hiring, and students who can demonstrate hands-on "
    "familiarity stand out.\n\n"
    "We run practical, industry-focused, interactive guest sessions on Artificial "
    "Intelligence — live tools, real use cases, no slideware marathons. We would be "
    "glad to host one for your students at no cost.\n\n"
    "Would you be open to a short call to see if this could fit your training calendar?\n\n"
    "Warm regards,\nMaaz Patel\nAIValytics\n\n"
    f"Unsubscribe: {UNSUBSCRIBE_TOKEN}"
)

GOOD_SUBJECTS = [
    "AI guest lecture for ABC College students",
    "Practical AI session for ABC College, Pune",
    "Industry AI workshop proposal - ABC College",
    "Helping ABC College students prepare for AI-era hiring",
    "AI workshop for your placement training calendar",
]


# ---------- lint ----------

def test_lint_accepts_good_draft():
    report = lint_draft(GOOD_SUBJECTS, GOOD_BODY, "ABC College")
    assert report["ok"], report


def test_lint_catches_placeholder_leak_and_missing_unsub():
    body = GOOD_BODY.replace("ABC College's", "[College Name]'s").replace(
        f"Unsubscribe: {UNSUBSCRIBE_TOKEN}", ""
    )
    report = lint_draft(GOOD_SUBJECTS, body, "ABC College")
    assert not report["ok"]
    joined = " ".join(report["errors"])
    assert "placeholder" in joined and "unsubscribe" in joined


def test_lint_requires_five_subjects_and_college_mention():
    report = lint_draft(GOOD_SUBJECTS[:2], "too short", "ABC College")
    assert not report["ok"]
    assert any("5 subject" in e for e in report["errors"])


# ---------- fixtures ----------

@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def contact(db):
    college = College(name="ABC College", normalized_name="abc college",
                      city="Pune", state="Maharashtra", website="https://abc.example/")
    db.add(college)
    db.flush()
    db.add(ResearchSummary(
        college_id=college.id,
        status=ResearchStatus.DONE,
        summary={
            "placement_activities": {"value": "Runs AI workshops with industry.",
                                     "source_url": "https://abc.example/placement"},
            "ai_initiatives": {"value": "NOT_FOUND", "source_url": None},
        },
    ))
    c = Contact(college_id=college.id, full_name="Dr. Anil Kumar",
                designation_raw="TPO", role=CanonicalRole.TPO,
                email="tpo@abc.ac.in", confidence=95, status=ContactStatus.VERIFIED)
    db.add(c)
    db.commit()
    return c


# ---------- fact sheet grounding ----------

def test_fact_sheet_omits_not_found(db, contact):
    research = db.query(ResearchSummary).one()
    sheet = build_fact_sheet(contact, research)
    assert "Runs AI workshops" in sheet
    assert "NOT_FOUND" not in sheet
    assert "AI INITIATIVES" not in sheet  # unknown field absent, not blank


# ---------- generation ----------

class FakeLLM:
    name = "fake"

    def __init__(self, responses: list[dict]):
        self._responses = responses
        self.calls = 0

    def complete(self, system, user, *, max_tokens=2048):
        payload = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return json.dumps(payload)


def test_generate_draft_happy_path(db, contact):
    llm = FakeLLM([{"subject_options": GOOD_SUBJECTS, "body_text": GOOD_BODY}])
    draft = generate_draft(db, contact, llm)
    assert draft.status is DraftStatus.DRAFT
    assert draft.lint_report["ok"]
    assert len(draft.subject_options) == 5
    assert UNSUBSCRIBE_TOKEN in draft.body_text


def test_generate_draft_retries_on_lint_failure(db, contact):
    bad = {"subject_options": GOOD_SUBJECTS,
           "body_text": "Hi [College Name], buy now!"}
    good = {"subject_options": GOOD_SUBJECTS, "body_text": GOOD_BODY}
    llm = FakeLLM([bad, good])
    draft = generate_draft(db, contact, llm)
    assert llm.calls == 2
    assert draft.lint_report["ok"]


def test_generate_draft_refuses_unverified_contact(db, contact):
    contact.status = ContactStatus.NEEDS_MANUAL_REVIEW
    db.commit()
    with pytest.raises(ValueError, match="not draftable"):
        generate_draft(db, contact, FakeLLM([{}]))


def test_unsubscribe_token_appended_when_llm_forgets(db, contact):
    body_without = GOOD_BODY.replace(f"\n\nUnsubscribe: {UNSUBSCRIBE_TOKEN}", "")
    llm = FakeLLM([{"subject_options": GOOD_SUBJECTS, "body_text": body_without}])
    draft = generate_draft(db, contact, llm)
    assert UNSUBSCRIBE_TOKEN in draft.body_text
    assert draft.lint_report["ok"]


# ---------- approval ----------

def test_approve_requires_passing_lint(db, contact):
    llm = FakeLLM([{"subject_options": [], "body_text": "junk"}])
    draft = generate_draft(db, contact, llm)
    assert not draft.lint_report["ok"]
    with pytest.raises(ValueError, match="fails lint"):
        approve_draft(db, draft, user_id=None)


def test_approve_writes_audit_and_locks_draft(db, contact):
    from app.models import AuditLog

    llm = FakeLLM([{"subject_options": GOOD_SUBJECTS, "body_text": GOOD_BODY}])
    draft = generate_draft(db, contact, llm)
    approve_draft(db, draft, user_id=None)
    assert draft.status is DraftStatus.APPROVED
    assert db.query(AuditLog).filter_by(action="draft.approve").count() == 1
    # approved drafts are immutable: regenerate returns it untouched
    body_before = draft.body_text
    again = generate_draft(db, contact, FakeLLM([{"subject_options": [], "body_text": "x"}]))
    assert again.id == draft.id and again.body_text == body_before
