"""Contact List model — a named group of contacts (many-to-many)."""

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


# Association table for the many-to-many between ContactList and Contact
contact_list_association = Table(
    "contact_list_members",
    Base.metadata,
    Column("list_id", Integer, ForeignKey("contact_lists.id", ondelete="CASCADE"),
           primary_key=True),
    Column("contact_id", Integer, ForeignKey("contacts.id", ondelete="CASCADE"),
           primary_key=True),
)


class ContactList(TimestampMixin, Base):
    """A user-created list that can contain multiple contacts.
    One contact can belong to multiple lists."""

    __tablename__ = "contact_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)

    contacts: Mapped[list["Contact"]] = relationship(  # noqa: F821
        "Contact",
        secondary=contact_list_association,
        back_populates="lists",
    )
