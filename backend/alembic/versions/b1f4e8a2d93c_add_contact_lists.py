"""add contact lists

Revision ID: b1f4e8a2d93c
Revises: a3637d12c61b
Create Date: 2026-08-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1f4e8a2d93c"
down_revision: Union[str, None] = "a3637d12c61b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contact_lists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "contact_list_members",
        sa.Column("list_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["list_id"], ["contact_lists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("list_id", "contact_id"),
    )


def downgrade() -> None:
    op.drop_table("contact_list_members")
    op.drop_table("contact_lists")
