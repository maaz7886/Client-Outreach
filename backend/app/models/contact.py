from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    CanonicalRole,
    ContactStatus,
    SourceType,
    TimestampMixin,
)


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("college_id", "email", name="uq_contact_college_email"),
        CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_contact_confidence"),
        Index("ix_contacts_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"))
    full_name: Mapped[str] = mapped_column(String(200))
    designation_raw: Mapped[str | None] = mapped_column(String(300))
    role: Mapped[CanonicalRole] = mapped_column(
        Enum(CanonicalRole, native_enum=False, length=30), default=CanonicalRole.OTHER
    )
    department: Mapped[str | None] = mapped_column(String(200))
    # every field below is nullable: NOT_FOUND is represented by NULL, never a guess
    email: Mapped[str | None] = mapped_column(String(320))
    email_mx_valid: Mapped[bool | None] = mapped_column(Boolean)
    phone_office: Mapped[str | None] = mapped_column(String(30))
    phone_direct: Mapped[str | None] = mapped_column(String(30))
    phone_mobile_public: Mapped[str | None] = mapped_column(String(30))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ContactStatus] = mapped_column(
        Enum(ContactStatus, native_enum=False, length=25), default=ContactStatus.DISCOVERED
    )
    notes: Mapped[str | None] = mapped_column(Text)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    college: Mapped["College"] = relationship(back_populates="contacts")  # noqa: F821
    sources: Mapped[list["ContactSource"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )
    lists: Mapped[list["ContactList"]] = relationship(  # noqa: F821
        "ContactList",
        secondary="contact_list_members",
        back_populates="contacts",
    )


class ContactSource(Base):
    """Provenance: one row per (field, source) — a contact merged from three
    pages keeps all three citations."""

    __tablename__ = "contact_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    field_name: Mapped[str] = mapped_column(String(50))  # e.g. "email", "phone_office"
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False, length=30))
    source_url: Mapped[str] = mapped_column(String(1000))
    excerpt: Mapped[str | None] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    contact: Mapped[Contact] = relationship(back_populates="sources")
