"""Daily activity tracking table (Sprint 2.3.B).

Хранит «активность игроков по дням МСК» — нужна для:

* `IDailyActivityRepository.list_active_member_ids(*, clan_id, within_days)` —
  доменный фильтр «не выбираем главу из неактивных» (ГДД §6.1, ПД §5
  задача 2.3.7).
* В будущем — потенциально для DAU-аналитики (если решим
  персистить DAU-counter, который сейчас живёт в памяти).

Таблица — ключ-значение по `(date, user_id)`:

* `date Date NOT NULL` — игровой день в TZ Москвы (по аналогии с
  `oracle_invocations.moscow_date`).
* `user_id BigInt NOT NULL FK users.id ON DELETE CASCADE` — кто был
  активен.
* `last_at DateTime(tz=True) NOT NULL` — UTC-время последней активности
  внутри этого дня (для отладки + потенциального tie-breaker-а).

PK `(date, user_id)` — один row на пару, идемпотентный upsert.

Index `(user_id, date DESC)` — для быстрого запроса «активность
игрока за последние N дней» (без фильтра по `clan_id` — клановый
фильтр приходит JOIN-ом к `clan_members`).

Записывает в эту таблицу — middleware на каждом сообщении (будет
в Спринте 2.3.E, см. `bot/middlewares/daily_activity.py`). На момент
2.3.B сама миграция + read-репозиторий — достаточно, чтобы доменный
сервис мог работать в integration-тестах с заранее prefilled-данными.

Revision ID: 0013_daily_active
Revises: 0012_daily_heads
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_daily_active"
down_revision: str | Sequence[str] | None = "0012_daily_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_active",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("date", "user_id", name="pk_daily_active"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_daily_active_user_id_users",
            ondelete="CASCADE",
        ),
    )
    # Запрос «активность одного user-а за последние N дней» —
    # покрывается этим индексом без сканирования.
    op.create_index(
        "ix_daily_active_user_id_date",
        "daily_active",
        ["user_id", sa.text("date DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_active_user_id_date", table_name="daily_active")
    op.drop_table("daily_active")
