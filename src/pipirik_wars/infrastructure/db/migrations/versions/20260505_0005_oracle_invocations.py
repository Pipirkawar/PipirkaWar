"""Oracle invocations table (Sprint 1.4.B).

Revision ID: 0005_oracle_invocations
Revises: 0004_forest_runs
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_oracle_invocations"
down_revision: str | Sequence[str] | None = "0004_forest_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oracle_invocations",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        # Дата вызова в TZ Москвы. Хранится отдельно от UTC-таймстампа
        # `occurred_at`, потому что именно по ней сделан UNIQUE-индекс
        # суточного кулдауна — в БД нет «бесплатного» способа взять
        # date(timestamp_at_tz('Europe/Moscow', occurred_at)) и в SQLite,
        # и в Postgres за один индекс.
        sa.Column("moscow_date", sa.Date(), nullable=False),
        sa.Column("bonus_cm", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_oracle_invocations"),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name="fk_oracle_invocations_player_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "bonus_cm > 0",
            name="ck_oracle_invocations_bonus_positive",
        ),
    )
    # Уникальность «один /oracle на (игрок, день по Москве)» — last-line
    # защита от race-кондишена; preflight в use-case-е дешёвый, но не
    # покрывает параллельные запросы.
    op.create_index(
        "uq_oracle_invocations_player_id_moscow_date",
        "oracle_invocations",
        ["player_id", "moscow_date"],
        unique=True,
    )
    # Аналитика «сколько /oracle сегодня» (без фильтра по игроку).
    op.create_index(
        "ix_oracle_invocations_moscow_date",
        "oracle_invocations",
        ["moscow_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_oracle_invocations_moscow_date", table_name="oracle_invocations")
    op.drop_index(
        "uq_oracle_invocations_player_id_moscow_date",
        table_name="oracle_invocations",
    )
    op.drop_table("oracle_invocations")
