"""Schema-level tests: relationships round-trip, and the compliance
constraints (touch cap, suppression uniqueness, confidence bounds) actually
reject bad data at the database layer."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Base,
    CanonicalRole,
    College,
    Contact,
    ContactSource,
    EmailDraft,
    SourceType,
    SuppressionEntry,
    SuppressionReason,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _college(**kw) -> College:
    defaults = dict(
        name="Test Institute of Technology",
        normalized_name="test institute of technology",
        city="Pune",
        state="Maharashtra",
    )
    defaults.update(kw)
    return College(**defaults)


def test_contact_with_provenance_roundtrip(db):
    college = _college()
    contact = Contact(
        college=college,
        full_name="Dr. A Sharma",
        role=CanonicalRole.TPO,
        email="tpo@example.edu",
        confidence=95,
        sources=[
            ContactSource(
                field_name="email",
                source_type=SourceType.OFFICIAL_WEBSITE,
                source_url="https://example.edu/placement",
                collected_at=datetime.now(timezone.utc),
            )
        ],
    )
    db.add(contact)
    db.commit()

    loaded = db.get(Contact, contact.id)
    assert loaded.college.city == "Pune"
    assert loaded.sources[0].source_type is SourceType.OFFICIAL_WEBSITE


def test_confidence_bounds_enforced(db):
    db.add(_college())
    db.commit()
    db.add(Contact(college_id=1, full_name="X", confidence=101))
    with pytest.raises(IntegrityError):
        db.commit()


def test_touch_cap_enforced(db):
    college = _college()
    contact = Contact(college=college, full_name="Dr. B", email="b@example.edu")
    db.add(contact)
    db.commit()

    db.add(EmailDraft(contact_id=contact.id, touch_number=5))
    with pytest.raises(IntegrityError):
        db.commit()


def test_duplicate_touch_rejected(db):
    college = _college()
    contact = Contact(college=college, full_name="Dr. C", email="c@example.edu")
    db.add(contact)
    db.commit()

    db.add_all(
        [
            EmailDraft(contact_id=contact.id, touch_number=1),
            EmailDraft(contact_id=contact.id, touch_number=1),
        ]
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_suppression_email_unique(db):
    db.add(SuppressionEntry(email="no@example.edu", reason=SuppressionReason.UNSUBSCRIBED))
    db.commit()
    db.add(SuppressionEntry(email="no@example.edu", reason=SuppressionReason.HARD_BOUNCE))
    with pytest.raises(IntegrityError):
        db.commit()


def test_college_dedup_key(db):
    db.add(_college())
    db.commit()
    db.add(_college(name="TEST Institute Of Technology"))
    with pytest.raises(IntegrityError):
        db.commit()
