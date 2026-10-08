"""Sessions, one-time codes and rate limits (moved out of memory, so a restart keeps them).

Revision ID: 0001
Revises:
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcl_session",
        sa.Column("id_hash", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mcl_session_expires_at", "mcl_session", ["expires_at"])
    op.create_table(
        "mcl_otp",
        sa.Column("phone_hash", sa.String(64), primary_key=True),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mcl_rate_hit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mcl_rate_hit_key_at", "mcl_rate_hit", ["key", "at"])


def downgrade() -> None:
    op.drop_table("mcl_rate_hit")
    op.drop_table("mcl_otp")
    op.drop_index("ix_mcl_session_expires_at", "mcl_session")
    op.drop_table("mcl_session")
