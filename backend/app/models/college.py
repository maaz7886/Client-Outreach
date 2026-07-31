from datetime import datetime

from sqlalchemy import JSON, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CollegeType, ResearchStatus, TimestampMixin


class College(TimestampMixin, Base):
    __tablename__ = "colleges"
    # normalized_name + city is the dedup key for fuzzy-matched discoveries
    __table_args__ = (
        UniqueConstraint("normalized_name", "city", name="uq_college_name_city"),
        Index("ix_colleges_state", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    normalized_name: Mapped[str] = mapped_column(String(300))
    city: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(120))
    website: Mapped[str | None] = mapped_column(String(500))
    naac_grade: Mapped[str | None] = mapped_column(String(10))
    nirf_rank: Mapped[int | None] = mapped_column(Integer)
    affiliation: Mapped[str | None] = mapped_column(String(300))
    college_type: Mapped[CollegeType] = mapped_column(
        Enum(CollegeType, native_enum=False, length=20), default=CollegeType.UNKNOWN
    )
    student_strength: Mapped[int | None] = mapped_column(Integer)
    discovery_source: Mapped[str | None] = mapped_column(String(500))

    contacts: Mapped[list["Contact"]] = relationship(back_populates="college")  # noqa: F821
    research: Mapped["ResearchSummary | None"] = relationship(back_populates="college")


class ResearchSummary(TimestampMixin, Base):
    __tablename__ = "research_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    college_id: Mapped[int] = mapped_column(ForeignKey("colleges.id"), unique=True)
    status: Mapped[ResearchStatus] = mapped_column(
        Enum(ResearchStatus, native_enum=False, length=25), default=ResearchStatus.PENDING
    )
    # structured fields: known_for, departments, achievements, ai_initiatives,
    # hackathons, industry_collaborations, ai_clubs, ecell, placements, ...
    # each entry is {"value": ..., "source_url": ...} — provenance is mandatory
    summary: Mapped[dict | None] = mapped_column(JSON)
    summary_text: Mapped[str | None] = mapped_column(Text)
    source_urls: Mapped[list | None] = mapped_column(JSON)
    llm_provider: Mapped[str | None] = mapped_column(String(50))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

    college: Mapped[College] = relationship(back_populates="research")
