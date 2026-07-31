"""Seed a local dev database with demo data so the dashboard has something to
show. Idempotent-ish: wipes and recreates. Dev only — never run in prod."""

from datetime import datetime, timedelta, timezone

from app.core.db import SessionLocal, engine
from app.core.security import hash_password
from app.models import (
    Base, CanonicalRole, College, Contact, ContactStatus, DraftStatus,
    EmailDraft, EmailEvent, EmailEventType, EmailMessage, MessageStatus,
    ResearchStatus, ResearchSummary, SourceType, User, UserRole,
)
from app.models.contact import ContactSource
from app.personalize.lint import UNSUBSCRIBE_TOKEN

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
now = datetime.now(timezone.utc)

BODY = (
    "Dear {name},\n\n"
    "I came across {college}'s work on {hook}, and it stood out. AI literacy is "
    "quickly becoming a baseline expectation in campus placements, and hands-on "
    "exposure makes a real difference for students.\n\n"
    "We run practical, industry-focused, interactive guest sessions on Artificial "
    "Intelligence and would be glad to host one for your students at no cost.\n\n"
    "Would you be open to a short call to see if this fits your training calendar?\n\n"
    "Warm regards,\nMaaz Patel\nAIValytics\n\n"
    f"Unsubscribe: {UNSUBSCRIBE_TOKEN}"
)

COLLEGES = [
    ("Sinhgad College of Engineering", "Pune", "Maharashtra", "A+", 87, "pre-placement AI training drives"),
    ("VJTI", "Mumbai", "Maharashtra", "A", 42, "the Technovanza tech fest"),
    ("COEP Technological University", "Pune", "Maharashtra", "A+", 55, "its innovation and incubation centre"),
    ("Walchand College of Engineering", "Sangli", "Maharashtra", "A", None, "Smart India Hackathon wins"),
    ("SGGS Institute", "Nanded", "Maharashtra", "A", None, "its E-Cell activities"),
    ("RCOEM", "Nagpur", "Maharashtra", None, None, "industry collaboration cells"),
    ("PES University", "Bengaluru", "Karnataka", "A++", 35, "its Centre for Innovation"),
    ("BMS College of Engineering", "Bengaluru", "Karnataka", "A++", 73, "hackathon culture"),
    ("SVNIT", "Surat", "Gujarat", "A", 65, "AI/DS department growth"),
    ("Nirma University", "Ahmedabad", "Gujarat", "A+", 60, "placement cell initiatives"),
]

ROLES = [
    ("Dr. A. Sharma", "Training & Placement Officer", CanonicalRole.TPO),
    ("Dr. P. Kulkarni", "HOD, Computer Science", CanonicalRole.AI_CS_DEPT_HEAD),
    ("Prof. S. Iyer", "Innovation Cell Coordinator", CanonicalRole.INNOVATION_CELL_HEAD),
]

with SessionLocal() as db:
    db.add(User(email="maaz@aivalytics.com", full_name="Maaz Patel",
                hashed_password=hash_password("demo1234"), role=UserRole.ADMIN))

    statuses = [
        ContactStatus.VERIFIED, ContactStatus.CONTACTED, ContactStatus.CONTACTED,
        ContactStatus.REPLIED_POSITIVE, ContactStatus.NEEDS_MANUAL_REVIEW,
        ContactStatus.MEETING_SCHEDULED, ContactStatus.VERIFIED, ContactStatus.CONTACTED,
        ContactStatus.WON, ContactStatus.VERIFIED,
    ]
    for i, (name, city, state, naac, nirf, hook) in enumerate(COLLEGES):
        college = College(name=name, normalized_name=name.lower(), city=city, state=state,
                          website=f"https://{name.split()[0].lower()}.example.edu",
                          naac_grade=naac, nirf_rank=nirf)
        db.add(college)
        db.flush()
        db.add(ResearchSummary(
            college_id=college.id, status=ResearchStatus.DONE,
            summary={"known_for": {"value": hook, "source_url": college.website}},
        ))
        person, designation, role = ROLES[i % len(ROLES)]
        email = None if statuses[i] is ContactStatus.NEEDS_MANUAL_REVIEW \
            else f"tpo@{name.split()[0].lower()}.example.edu"
        contact = Contact(college_id=college.id, full_name=person,
                          designation_raw=designation, role=role, email=email,
                          confidence=95 if email else 40, status=statuses[i],
                          email_mx_valid=bool(email) or None)
        db.add(contact)
        db.flush()
        if email:
            db.add(ContactSource(contact_id=contact.id, field_name="email",
                                 source_type=SourceType.OFFICIAL_WEBSITE,
                                 source_url=f"{college.website}/placement",
                                 collected_at=now))
        body = BODY.format(name=person, college=name, hook=hook)
        subjects = [
            f"AI guest lecture for {name} students",
            f"Practical AI session for {name}, {city}",
            f"Industry AI workshop proposal - {name}",
            "Helping your students prepare for AI-era hiring",
            "AI workshop for your training calendar",
        ]
        draft_status = (DraftStatus.DRAFT if statuses[i] is ContactStatus.VERIFIED
                        else DraftStatus.SENT if statuses[i] in
                        (ContactStatus.CONTACTED, ContactStatus.REPLIED_POSITIVE,
                         ContactStatus.MEETING_SCHEDULED, ContactStatus.WON)
                        else None)
        if draft_status:
            draft = EmailDraft(contact_id=contact.id, touch_number=1,
                               subject_options=subjects, chosen_subject=subjects[0],
                               body_text=body,
                               lint_report={"ok": True, "errors": [], "warnings": []},
                               status=draft_status)
            db.add(draft)
            db.flush()
            if draft_status is DraftStatus.SENT:
                msg = EmailMessage(draft_id=draft.id, contact_id=contact.id,
                                   provider="smtp", status=MessageStatus.SENT,
                                   sent_at=now - timedelta(days=i))
                db.add(msg)
                db.flush()
                db.add(EmailEvent(message_id=msg.id, event_type=EmailEventType.OPEN))
                if statuses[i] in (ContactStatus.REPLIED_POSITIVE,
                                   ContactStatus.MEETING_SCHEDULED, ContactStatus.WON):
                    db.add(EmailEvent(message_id=msg.id, event_type=EmailEventType.REPLY,
                                      meta={"sentiment": "POSITIVE"}))
    db.commit()
    print("Seeded: 10 colleges, 10 contacts, drafts + messages + events.")
    print("Login: maaz@aivalytics.com / demo1234")
