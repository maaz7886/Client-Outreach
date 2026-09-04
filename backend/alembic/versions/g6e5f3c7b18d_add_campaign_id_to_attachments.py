"""add campaign_id to attachments and make draft_id nullable

Revision ID: g6e5f3c7b18d
Revises: f5d4e2b6a07c
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g6e5f3c7b18d"
down_revision: Union[str, None] = "f5d4e2b6a07c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make draft_id nullable to allow campaign-only attachments
    with op.batch_alter_table("attachments") as batch_op:
        batch_op.alter_column(
            "draft_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column("campaign_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("list_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_attachments_campaign_id",
            "campaigns",
            ["campaign_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_attachments_list_id",
            "contact_lists",
            ["list_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_attachments_campaign_id", ["campaign_id"])
        batch_op.create_index("ix_attachments_list_id", ["list_id"])


def downgrade() -> None:
    with op.batch_alter_table("attachments") as batch_op:
        batch_op.drop_index("ix_attachments_list_id")
        batch_op.drop_index("ix_attachments_campaign_id")
        batch_op.drop_constraint("fk_attachments_list_id", type_="foreignkey")
        batch_op.drop_constraint("fk_attachments_campaign_id", type_="foreignkey")
        batch_op.drop_column("list_id")
        batch_op.drop_column("campaign_id")
        batch_op.alter_column(
            "draft_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
