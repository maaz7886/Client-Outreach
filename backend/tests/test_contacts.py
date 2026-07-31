"""Phase 4 tests: role mapping, confidence rubric, grounded extraction
(fabricated emails/people must not survive), and the discovery engine
end-to-end against a mock college site with a fake LLM."""

import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.contacts.engine import discover_contacts
from app.contacts.extractor import extract_people
from app.contacts.roles import canonical_role
from app.contacts.scoring import confidence_score
from app.contacts.verify import check_email
from app.models import (
    Base,
    CanonicalRole,
    College,
    Contact,
    ContactStatus,
    SourceType,
)
from app.research.fetcher import PoliteFetcher


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


# ---------- roles ----------

@pytest.mark.parametrize(
    ("designation", "expected"),
    [
        ("Training & Placement Officer", CanonicalRole.TPO),
        ("TPO", CanonicalRole.TPO),
        ("Director of Placements", CanonicalRole.PLACEMENT_DIRECTOR),
        ("Principal", CanonicalRole.PRINCIPAL),
        ("Vice-Principal", CanonicalRole.VICE_PRINCIPAL),
        ("HOD, Computer Science & Engineering", CanonicalRole.AI_CS_DEPT_HEAD),
        ("Head of Department (Mechanical)", CanonicalRole.HOD),
        ("Dean Academics", CanonicalRole.DEAN),
        ("Coordinator, Institution's Innovation Cell", CanonicalRole.INNOVATION_CELL_HEAD),
        ("E-Cell Faculty Head", CanonicalRole.ECELL_HEAD),
        ("Assistant Professor", CanonicalRole.OTHER),
        (None, CanonicalRole.OTHER),
    ],
)
def test_canonical_role(designation, expected):
    assert canonical_role(designation) is expected


# ---------- scoring rubric ----------

def test_confidence_rubric_matches_spec():
    assert confidence_score({SourceType.OFFICIAL_WEBSITE}) == 95
    assert confidence_score(
        {SourceType.OFFICIAL_WEBSITE, SourceType.GOVT_DATABASE}
    ) >= 95
    assert 80 <= confidence_score(
        {SourceType.GOVT_DATABASE, SourceType.PUBLIC_DOCUMENT}
    ) <= 95
    assert 60 <= confidence_score(
        {SourceType.ENRICHMENT_API, SourceType.NEWS_ARTICLE}
    ) <= 80
    assert confidence_score({SourceType.NEWS_ARTICLE}) < 60
    assert confidence_score(set()) == 0


# ---------- email verification ----------

def test_check_email_syntax_and_mx():
    assert check_email("not-an-email") is False
    assert check_email("a@b", mx_lookup=lambda d: True) is False  # bad TLD
    assert check_email("tpo@college.ac.in", mx_lookup=lambda d: True) is True
    assert check_email("tpo@college.ac.in", mx_lookup=lambda d: None) is None


# ---------- grounded extraction ----------

PAGE_TEXT = """Training and Placement Cell
Dr. Anil Kumar, Training & Placement Officer
Email: tpo@abc.ac.in  Phone: +91 98765 43210
Dr. Sunita Rao, Principal — principal@abc.ac.in
"""


class FakeLLM:
    name = "fake"

    def __init__(self, payload):
        self._payload = payload

    def complete(self, system, user, *, max_tokens=2048):
        return json.dumps(self._payload)


def test_extract_people_grounds_every_field():
    payload = [
        {"full_name": "Dr. Anil Kumar", "designation": "Training & Placement Officer",
         "department": None, "email": "tpo@abc.ac.in", "phone": "+91 98765 43210"},
        # fabricated email for a real person -> email must be nulled
        {"full_name": "Dr. Sunita Rao", "designation": "Principal",
         "department": None, "email": "sunita.rao@gmail.com", "phone": None},
        # entirely invented person -> dropped
        {"full_name": "Dr. Imaginary Person", "designation": "Dean",
         "department": None, "email": "dean@abc.ac.in", "phone": None},
    ]
    people = extract_people(PAGE_TEXT, FakeLLM(payload))
    assert [p["full_name"] for p in people] == ["Dr. Anil Kumar", "Dr. Sunita Rao"]
    assert people[0]["email"] == "tpo@abc.ac.in"
    assert people[0]["phone"] == "+91 98765 43210"
    assert people[1]["email"] is None  # fabricated address did not survive


# ---------- engine end-to-end ----------

SITE = {
    "https://abc.example/robots.txt": httpx.Response(404),
    "https://abc.example/": httpx.Response(
        200,
        text='<a href="/placement">Placement</a><p>Welcome to ABC College</p>',
        headers={"content-type": "text/html"},
    ),
    "https://abc.example/placement": httpx.Response(
        200,
        text="<p>Dr. Anil Kumar, Training and Placement Officer. "
             "Email: tpo@abc.ac.in Phone: +91 98765 43210</p>"
             "<p>Mr. Ravi Student, Placement Coordinator (Student)</p>",
        headers={"content-type": "text/html"},
    ),
}


def make_fetcher(routes):
    def handler(request):
        return routes.get(str(request.url), httpx.Response(404))

    return PoliteFetcher(delay_seconds=0, transport=httpx.MockTransport(handler),
                         sleep=lambda s: None)


ENGINE_PAYLOAD = [
    {"full_name": "Dr. Anil Kumar", "designation": "Training and Placement Officer",
     "department": "Placement Cell", "email": "tpo@abc.ac.in", "phone": "+91 98765 43210"},
    {"full_name": "Prof. Nobody", "designation": "Assistant Professor",
     "department": None, "email": None, "phone": None},
]


def _college(db):
    college = College(name="ABC College", normalized_name="abc college",
                      city="Pune", state="Maharashtra", website="https://abc.example/")
    db.add(college)
    db.commit()
    return college


def test_discover_contacts_end_to_end(db):
    college = _college(db)
    contacts = discover_contacts(
        db, college, make_fetcher(SITE), FakeLLM(ENGINE_PAYLOAD),
        mx_lookup=lambda d: True,
    )
    assert len(contacts) == 1  # Assistant Professor filtered out (not a target role)
    tpo = contacts[0]
    assert tpo.role is CanonicalRole.TPO
    assert tpo.email == "tpo@abc.ac.in"
    assert tpo.confidence >= 95
    assert tpo.status is ContactStatus.VERIFIED
    assert tpo.email_mx_valid is True
    urls = {s.source_url for s in tpo.sources}
    assert any("placement" in u or "abc.example" in u for u in urls)


def test_discover_contacts_is_idempotent(db):
    college = _college(db)
    fetcher_args = (make_fetcher(SITE), FakeLLM(ENGINE_PAYLOAD))
    discover_contacts(db, college, *fetcher_args, mx_lookup=lambda d: True)
    discover_contacts(db, college, make_fetcher(SITE), FakeLLM(ENGINE_PAYLOAD),
                      mx_lookup=lambda d: True)
    assert db.query(Contact).count() == 1  # merged, not duplicated
    contact = db.query(Contact).one()
    citation_pairs = [(s.field_name, s.source_url) for s in contact.sources]
    assert len(citation_pairs) == len(set(citation_pairs))  # no duplicate citations


def test_no_email_contact_flagged_for_manual_review(db):
    college = _college(db)
    payload = [{"full_name": "Dr. Anil Kumar", "designation": "TPO",
                "department": None, "email": None, "phone": None}]
    site = dict(SITE)
    site["https://abc.example/placement"] = httpx.Response(
        200, text="<p>Dr. Anil Kumar, TPO</p>", headers={"content-type": "text/html"}
    )
    contacts = discover_contacts(db, college, make_fetcher(site), FakeLLM(payload),
                                 mx_lookup=lambda d: True)
    assert contacts[0].status is ContactStatus.NEEDS_MANUAL_REVIEW
    assert contacts[0].email is None  # NOT_FOUND stays NULL, never guessed
