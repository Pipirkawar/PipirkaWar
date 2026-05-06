"""Daily clan head assignments table (Sprint 2.3.B).

Хранит назначения «Главы клана дня 👑» (ГДД §6.1) — по одному на пару
``(clan_id, moscow_date)``. Источник назначения (``button``/``cron``)
сохраняется для последующей аналитики «какой триггер был эффективнее».

Идемпотентность гонки кнопка-vs-cron гарантируется UNIQUE-индексом
``uq_daily_heads_clan_id_moscow_date``: доменный сервис
``DailyHeadService.assign_or_get`` сначала проверяет существование, но
при гонке двух конкурентных запросов (кнопка + cron одновременно)
второй упрётся в UNIQUE и репозиторий конвертирует ``IntegrityError``
в ``DailyHeadAlreadyAssignedError`` (запрос-победитель уже сделал
работу — повтор должен вернуть существующую запись).

CHECK-инварианты на уровне БД (last-line-of-defense):

* ``bonus_cm > 0`` — премия всегда положительная.
* ``source IN ('button', 'cron')`` — единственные допустимые триггеры.

FK:

* ``clan_id → clans.id ON DELETE CASCADE`` — при удалении клана
  историческая запись о его главе теряет смысл.
* ``player_id → users.id ON DELETE CASCADE`` — при анонимизации
  / удалении игрока запись тоже удаляется (мы не сохраняем «осиротевших»
  глав, потому что бонус-длина уже начислена и зафиксирована в
  ``audit_log``).

Index ``ix_daily_heads_clan_id_assigned_at_id`` нужен для запроса
«последние N глав клана» (anti-repeat-фильтр в
``DailyHeadService._filter_avoid_recent``): сортировка по
``assigned_at DESC, id DESC`` обязательна для tie-breaker-а
(одинаковая дата — несколько cron-job-ов в одну секунду).

Revision ID: 0012_daily_heads
Revises: 0011_pvp_mass_duels
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_daily_heads"
down_revision: str | Sequence[str] | None = "0011_pvp_mass_duels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_heads",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("clan_id", sa.BigInteger(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        # Дата назначения в TZ Москвы. Хранится отдельно от
        # ``assigned_at`` (UTC), потому что именно по ней сделан UNIQUE
        # суточного назначения — в БД нет «бесплатного» способа взять
        # date(timestamp_at_tz('Europe/Moscow', assigned_at)) и в SQLite,
        # и в Postgres за один индекс. См. шаблон oracle_invocations.
        sa.Column("moscow_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("bonus_cm", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_daily_heads"),
        sa.ForeignKeyConstraint(
            ["clan_id"],
            ["clans.id"],
            name="fk_daily_heads_clan_id_clans",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name="fk_daily_heads_player_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "bonus_cm > 0",
            name="ck_daily_heads_bonus_positive",
        ),
        sa.CheckConstraint(
            "source IN ('button', 'cron')",
            name="ck_daily_heads_source_valid",
        ),
    )
    # Идемпотентность «один глава на (клан, день по Москве)» —
    # last-line-of-defense от race-кондишена кнопка+cron. Доменный
    # сервис проверяет существование preflight-ом, но если две
    # параллельные транзакции прошли проверку — UNIQUE остановит
    # одну из них.
    op.create_index(
        "uq_daily_heads_clan_id_moscow_date",
        "daily_heads",
        ["clan_id", "moscow_date"],
        unique=True,
    )
    # Anti-repeat-фильтр: «последние N глав клана» — сортировка по
    # ``assigned_at DESC, id DESC`` (id — tie-breaker для одинакового
    # таймстампа). Запрос покрывается этим индексом без bitmap-сканов.
    op.create_index(
        "ix_daily_heads_clan_id_assigned_at_id",
        "daily_heads",
        [
            "clan_id",
            sa.text("assigned_at DESC"),
            sa.text("id DESC"),
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_heads_clan_id_assigned_at_id", table_name="daily_heads")
    op.drop_index("uq_daily_heads_clan_id_moscow_date", table_name="daily_heads")
    op.drop_table("daily_heads")
