from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    DraftStatus,
    EmailEventType,
    FollowupStatus,
    MessageStatus,
    SuppressionReason,
    TimestampMixin,
    utcnow,
)


class EmailDraft(TimestampMixin, Base):
    __tablename__ = "email_drafts"
    __table_args__ = (
        # 1 initial + 3 follow-ups, enforced here so no code path can exceed it
        CheckConstraint("touch_number >= 1 AND touch_number <= 4", name="ck_draft_touch_cap"),
        UniqueConstraint("contact_id", "touch_number", name="uq_draft_contact_touch"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"))
    touch_number: Mapped[int] = mapped_column(Integer, default=1)
    subject_options: Mapped[list | None] = mapped_column(JSON)  # 5 generated options
    chosen_subject: Mapped[str | None] = mapped_column(String(300))
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    lint_report: Mapped[dict | None] = mapped_column(JSON)  # placeholder-leak, spam-words, length
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus, native_enum=False, length=15), default=DraftStatus.DRAFT
    )
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list["EmailMessage"]] = relationship(back_populates="draft")


class EmailMessage(Base):
    """A concrete send attempt of an approved draft."""

    __tablename__ = "email_messages"
    __table_args__ = (Index("ix_messages_contact", "contact_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("email_drafts.id"))
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"))
    provider: Mapped[str] = mapped_column(String(30))  # smtp | gmail | graph
    provider_message_id: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, native_enum=False, length=10)
    )
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    draft: Mapped[EmailDraft] = relationship(back_populates="messages")
    events: Mapped[list["EmailEvent"]] = relationship(back_populates="message")


class EmailEvent(Base):
    __tablename__ = "email_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("email_messages.id"))
    event_type: Mapped[EmailEventType] = mapped_column(
        Enum(EmailEventType, native_enum=False, length=15)
    )
    meta: Mapped[dict | None] = mapped_column(JSON)  # user-agent, url clicked, reply sentiment…
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    message: Mapped[EmailMessage] = relationship(back_populates="events")


class FollowupSchedule(Base):
    __tablename__ = "followup_schedules"
    __table_args__ = (
        CheckConstraint("touch_number >= 2 AND touch_number <= 4", name="ck_followup_touch"),
        UniqueConstraint("contact_id", "touch_number", name="uq_followup_contact_touch"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"))
    touch_number: Mapped[int] = mapped_column(Integer)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[FollowupStatus] = mapped_column(
        Enum(FollowupStatus, native_enum=False, length=10), default=FollowupStatus.PENDING
    )
    cancelled_reason: Mapped[str | None] = mapped_column(String(200))


class SuppressionEntry(Base):
    """Checked by the sender at send time. Presence here makes an address
    unmailable regardless of what is queued."""

    __tablename__ = "suppression_list"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    reason: Mapped[SuppressionReason] = mapped_column(
        Enum(SuppressionReason, native_enum=False, length=15)
    )
    detail: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
