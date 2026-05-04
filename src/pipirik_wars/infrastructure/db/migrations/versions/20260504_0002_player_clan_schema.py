"""Player & clan schema (Sprint 1.1).

Revision ID: 0002_player_clan
Revises: 0001_initial
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_player_clan"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=True),
        sa.Column("length_cm", sa.Integer(), nullable=False),
        sa.Column("thickness_level", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="active",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("tg_id", name="uq_users_tg_id"),
        sa.CheckConstraint("length_cm >= 0", name="ck_users_length_non_negative"),
        sa.CheckConstraint(
            "thickness_level >= 1",
            name="ck_users_thickness_positive",
        ),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "clans",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="active",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_clans"),
        sa.UniqueConstraint("chat_id", name="uq_clans_chat_id"),
    )

    op.create_table(
        "clan_members",
        sa.Column("clan_id", sa.BigInteger(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=16),
            server_default="member",
            nullable=False,
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("clan_id", "player_id", name="pk_clan_members"),
        sa.ForeignKeyConstraint(
            ["clan_id"],
            ["clans.id"],
            name="fk_clan_members_clan_id_clans",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name="fk_clan_members_player_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("player_id", name="uq_clan_members_player_id"),
    )


def downgrade() -> None:
    op.drop_table("clan_members")
    op.drop_table("clans")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
