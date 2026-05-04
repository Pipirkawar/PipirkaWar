"""Forest runs table (Sprint 1.3.B).

Revision ID: 0004_forest_runs
Revises: 0003_signup_queue
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_forest_runs"
down_revision: str | Sequence[str] | None = "0003_signup_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forest_runs",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("branch_name", sa.String(length=32), nullable=False),
        sa.Column("length_delta_cm", sa.Integer(), nullable=False),
        sa.Column("drop_kind", sa.String(length=8), nullable=False),
        sa.Column("drop_item_id", sa.String(length=64), nullable=True),
        sa.Column("drop_name", sa.String(length=64), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_forest_runs"),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name="fk_forest_runs_player_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "length_delta_cm >= 0",
            name="ck_forest_runs_length_non_negative",
        ),
        sa.CheckConstraint(
            "status IN ('in_progress', 'finished')",
            name="ck_forest_runs_status_valid",
        ),
        sa.CheckConstraint(
            "drop_kind IN ('none', 'item', 'name')",
            name="ck_forest_runs_drop_kind_valid",
        ),
        sa.CheckConstraint(
            # Только один из drop_item_id / drop_name может быть не-NULL,
            # и тот — строго совместим с drop_kind. Это «запоминающий» CHECK,
            # который не даёт записать item-дроп без id или name-дроп без value.
            "(drop_kind = 'none' AND drop_item_id IS NULL AND drop_name IS NULL)"
            " OR (drop_kind = 'item' AND drop_item_id IS NOT NULL AND drop_name IS NULL)"
            " OR (drop_kind = 'name' AND drop_item_id IS NULL AND drop_name IS NOT NULL)",
            name="ck_forest_runs_drop_payload_matches_kind",
        ),
        sa.CheckConstraint(
            # IN_PROGRESS-поход не имеет finished_at; FINISHED-поход — обязан иметь.
            "(status = 'in_progress' AND finished_at IS NULL)"
            " OR (status = 'finished' AND finished_at IS NOT NULL)",
            name="ck_forest_runs_finished_at_matches_status",
        ),
        sa.CheckConstraint(
            "ends_at > started_at",
            name="ck_forest_runs_ends_after_start",
        ),
    )
    # Поиск активного похода игрока (StartForestRun preflight).
    op.create_index(
        "ix_forest_runs_player_id_status",
        "forest_runs",
        ["player_id", "status"],
    )
    # Сканирование готовых к финишу запусков (FinishForestRun job, 1.3.C).
    op.create_index(
        "ix_forest_runs_status_ends_at",
        "forest_runs",
        ["status", "ends_at"],
    )
    # Инвариант «у игрока не больше одного IN_PROGRESS-похода» —
    # частичный уникальный индекс. На SQLite (test-движке) частичные
    # индексы поддерживаются, на Postgres — тоже, синтаксис общий.
    op.create_index(
        "uq_forest_runs_one_active_per_player",
        "forest_runs",
        ["player_id"],
        unique=True,
        sqlite_where=sa.text("status = 'in_progress'"),
        postgresql_where=sa.text("status = 'in_progress'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_forest_runs_one_active_per_player",
        table_name="forest_runs",
    )
    op.drop_index("ix_forest_runs_status_ends_at", table_name="forest_runs")
    op.drop_index("ix_forest_runs_player_id_status", table_name="forest_runs")
    op.drop_table("forest_runs")
