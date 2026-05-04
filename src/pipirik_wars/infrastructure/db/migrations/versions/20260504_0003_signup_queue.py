"""Signup queue (Sprint 1.2.4).

Revision ID: 0003_signup_queue
Revises: 0002_player_clan
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_signup_queue"
down_revision: str | Sequence[str] | None = "0002_player_clan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signup_queue",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=True),
        sa.Column("locale", sa.String(length=16), nullable=True),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_signup_queue"),
        sa.UniqueConstraint("tg_id", name="uq_signup_queue_tg_id"),
    )
    op.create_index(
        "ix_signup_queue_enqueued_at",
        "signup_queue",
        ["enqueued_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_signup_queue_enqueued_at", table_name="signup_queue")
    op.drop_table("signup_queue")
