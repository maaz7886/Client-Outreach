"""add campaigns

Revision ID: d3b2c0f4e95e
Revises: c2a1f9e3b84d
Create Date: 2026-08-16 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3b2c0f4e95e"
down_revision: Union[str, None] = "c2a1f9e3b84d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("list_id", sa.Integer(), nullable=True),
        sa.Column("list_name", sa.String(length=200), nullable=True),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("suppressed", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["list_id"], ["contact_lists.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campaigns_started_at", "campaigns", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_campaigns_started_at", table_name="campaigns")
    op.drop_table("campaigns")
