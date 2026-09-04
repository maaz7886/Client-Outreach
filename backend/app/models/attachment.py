"""Email attachment metadata — files stored on disk, linked to a draft or campaign."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Associated with a draft (individual attachment):
    draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_drafts.id", ondelete="CASCADE"), index=True, nullable=True,
    )
    # Associated with a campaign (sent level-1 attachment):
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=True,
    )
    # Associated with a list (list-level campaign attachment configuration):
    list_id: Mapped[int | None] = mapped_column(
        ForeignKey("contact_lists.id", ondelete="CASCADE"), index=True, nullable=True,
    )
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(500))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

