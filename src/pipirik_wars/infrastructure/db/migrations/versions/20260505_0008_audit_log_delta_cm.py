"""Audit-log delta_cm column (Sprint 1.6.C).

Добавляем `audit_log.delta_cm INT NULL` — фактически применённую дельту длины
в сантиметрах. Заполняется в Спринте 1.6.D (`progression.add_length`); до этого
момента всегда `NULL`. На вход в anti-cheat-агрегацию (Спринт 1.6.C —
`SqlAlchemyAnticheatRepository.sum_organic_in_window`) попадают строки с
`delta_cm IS NOT NULL AND delta_cm > 0`.

**Зачем отдельная колонка, а не вычисление через JSON `before/after`:**
SUM по JSON-extract-у непортабелен (SQLite vs Postgres) и плохо индексируется.
Отдельная числовая колонка делает агрегацию однозначной и быстрой
(после composite-индекса, который добавится при необходимости в 1.6.H).

**Знак:** `delta_cm` — знаковое число. Положительные — organic-прирост,
отрицательные — refund-ы (`admin_refund`). Anti-cheat-окно учитывает
только `delta_cm > 0` (см. ГДД §3.3.4: `admin_refund` обнуляет действие,
не агрегируется как положительный рост).

**Backfill:** для старых строк `delta_cm = NULL` (нет дефолта). Они и так не
участвовали бы в агрегации (`source = 'unknown'` — не organic).

Revision ID: 0008_audit_log_delta_cm
Revises: 0007_anticheat_foundation
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_audit_log_delta_cm"
down_revision: str | Sequence[str] | None = "0007_anticheat_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        batch.add_column(
            sa.Column("delta_cm", sa.Integer(), nullable=True),
        )
        # Composite index для anti-cheat-агрегации (Sprint 1.6.C):
        # `WHERE target_kind='player' AND target_id=:pid AND source IN (...) AND
        #   delta_cm IS NOT NULL AND delta_cm > 0 AND occurred_at >= :since`.
        # `(target_id, source, occurred_at)` достаточно — `target_kind='player'`
        # — это точка-фильтр (низкая селективность), а `delta_cm > 0` — финальный
        # row-filter после bitmap-merge. На SQLite индекс работает аналогично.
        batch.create_index(
            "ix_audit_log_target_source_occurred",
            ["target_id", "source", "occurred_at"],
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_index("ix_audit_log_target_source_occurred")
        batch.drop_column("delta_cm")
