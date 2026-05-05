"""PvP global FIFO lobby (Sprint 2.1.F).

Таблица ``pvp_global_lobby`` хранит pending-дуэли в режиме
``GLOBAL_ONLY`` (или авто-промоутнутые из ``CHAT_THEN_GLOBAL``),
ожидающие подбор оппонента. Связь с ``pvp_duels`` — 1:1 через
``duel_id`` (он же PK), каскадное удаление: если основной duel-row
удалён, лобби-запись пропадает автоматически.

Поля:

* ``duel_id`` — PK, FK→``pvp_duels(id)`` ON DELETE CASCADE.
* ``enqueued_at`` — момент постановки в очередь (UTC, tz-aware).
  Индекс ``ix_pvp_global_lobby_enqueued_at`` поддерживает
  ``ORDER BY enqueued_at ASC LIMIT 1`` для атомарного
  ``pop_oldest`` (паттерн FIFO).

Не дублируем CHECK на ``state='pending_accept'`` или
``mode='global_only'`` в этой таблице — поддержание этих инвариантов
лежит на use-case-ах (`EnqueueGlobalDuel`/`MatchFromLobby`/
`ExpireLobbyEntry`). Если шедулер промахнётся и оставит запись на
уже-завершённой дуэли, fix — на стороне CleanupExpiredLobby (TTL),
а не на CHECK-constraint.

Revision ID: 0010_pvp_global_lobby
Revises: 0009_pvp_duels
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_pvp_global_lobby"
down_revision: str | Sequence[str] | None = "0009_pvp_duels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pvp_global_lobby",
        sa.Column(
            "duel_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
        ),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("duel_id", name="pk_pvp_global_lobby"),
        sa.ForeignKeyConstraint(
            ["duel_id"],
            ["pvp_duels.id"],
            name="fk_pvp_global_lobby_duel_id_pvp_duels",
            ondelete="CASCADE",
        ),
    )
    # FIFO-pop: SELECT ... ORDER BY enqueued_at ASC LIMIT 1.
    op.create_index(
        "ix_pvp_global_lobby_enqueued_at",
        "pvp_global_lobby",
        ["enqueued_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pvp_global_lobby_enqueued_at", table_name="pvp_global_lobby")
    op.drop_table("pvp_global_lobby")
