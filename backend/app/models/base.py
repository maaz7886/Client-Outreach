"""Declarative base, shared column helpers, and every domain enum.

Enums are stored as strings (native_enum=False) so adding a member is an
ordinary migration on any database, including SQLite in tests."""

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CollegeType(str, enum.Enum):
    GOVERNMENT = "GOVERNMENT"
    PRIVATE = "PRIVATE"
    AUTONOMOUS = "AUTONOMOUS"
    DEEMED = "DEEMED"
    UNKNOWN = "UNKNOWN"


class CanonicalRole(str, enum.Enum):
    TPO = "TPO"
    PLACEMENT_DIRECTOR = "PLACEMENT_DIRECTOR"
    TRAINING_OFFICER = "TRAINING_OFFICER"
    HOD = "HOD"
    DEAN = "DEAN"
    DIRECTOR = "DIRECTOR"
    PRINCIPAL = "PRINCIPAL"
    VICE_PRINCIPAL = "VICE_PRINCIPAL"
    INNOVATION_CELL_HEAD = "INNOVATION_CELL_HEAD"
    ECELL_HEAD = "ECELL_HEAD"
    INCUBATION_HEAD = "INCUBATION_HEAD"
    AI_CS_DEPT_HEAD = "AI_CS_DEPT_HEAD"
    OTHER = "OTHER"


class ContactStatus(str, enum.Enum):
    DISCOVERED = "DISCOVERED"
    VERIFIED = "VERIFIED"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"
    QUEUED = "QUEUED"
    CONTACTED = "CONTACTED"
    REPLIED_POSITIVE = "REPLIED_POSITIVE"
    REPLIED_NEGATIVE = "REPLIED_NEGATIVE"
    NO_REPLY_EXHAUSTED = "NO_REPLY_EXHAUSTED"
    BOUNCED = "BOUNCED"
    UNSUBSCRIBED = "UNSUBSCRIBED"
    MEETING_SCHEDULED = "MEETING_SCHEDULED"
    WON = "WON"
    LOST = "LOST"


class SourceType(str, enum.Enum):
    OFFICIAL_WEBSITE = "OFFICIAL_WEBSITE"
    MANDATORY_DISCLOSURE_PDF = "MANDATORY_DISCLOSURE_PDF"
    GOVT_DATABASE = "GOVT_DATABASE"
    ENRICHMENT_API = "ENRICHMENT_API"
    NEWS_ARTICLE = "NEWS_ARTICLE"
    CONFERENCE_PAGE = "CONFERENCE_PAGE"
    PUBLIC_DOCUMENT = "PUBLIC_DOCUMENT"
    MANUAL = "MANUAL"


class ResearchStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    WEBSITE_UNAVAILABLE = "WEBSITE_UNAVAILABLE"
    FAILED = "FAILED"


class DraftStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    QUEUED = "QUEUED"
    SENT = "SENT"


class MessageStatus(str, enum.Enum):
    SENT = "SENT"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"


class EmailEventType(str, enum.Enum):
    OPEN = "OPEN"
    CLICK = "CLICK"
    BOUNCE = "BOUNCE"
    REPLY = "REPLY"
    UNSUBSCRIBE = "UNSUBSCRIBE"


class FollowupStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    CANCELLED = "CANCELLED"


class SuppressionReason(str, enum.Enum):
    UNSUBSCRIBED = "UNSUBSCRIBED"
    HARD_BOUNCE = "HARD_BOUNCE"
    COMPLAINT = "COMPLAINT"
    MANUAL = "MANUAL"


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"
