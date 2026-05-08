"""Caravans persistence (Спринт 3.2-B, ГДД §9): caravans + caravan_participants.

Доменный слой 3.2-A добавил `domain/caravan/` (Спринт 3.2-A, PR #108):
агрегат `Caravan` + участник `CaravanParticipant` + порты-репо. Эта
миграция (3.2-B) приземляет их на БД:

1. **`caravans`** — корневая таблица каравана (один row на бой).
   Хранит весь жизненный цикл `LOBBY → IN_BATTLE → FINISHED|CANCELLED`,
   `random_seed` (snapshot для воспроизводимости боя 3.2-C), временные
   метки `started_at`/`lobby_ends_at`/`battle_ends_at`/`finished_at`,
   ссылки на отправителя/получателя/лидера-игрока.

2. **`caravan_participants`** — 1:N от `caravans`, каскад на удаление.
   Один row на каждого участника (`CARAVANEER`/`DEFENDER`/`RAIDER`),
   `is_leader=true` ровно у одного — у `CARAVANEER`-лидера каравана.

CHECK-инварианты — last-line-of-defense на случай прямых SQL-правок:

* `status IN ('lobby', 'in_battle', 'finished', 'cancelled')`;
* `sender_clan_id <> receiver_clan_id` (нельзя слать караван «себе»);
* `lobby_ends_at > started_at`;
* `battle_ends_at > lobby_ends_at`;
* `(status='finished' OR status='cancelled') AND finished_at IS NOT NULL`
  ИЛИ `(status='lobby' OR status='in_battle') AND finished_at IS NULL`;
* `participants.role IN ('caravaneer', 'defender', 'raider')`;
* лидером может быть только караванщик: `(is_leader=true AND role='caravaneer')`
  ИЛИ `is_leader=false`;
* контрибьюция консистентна с ролью: караванщик обязан внести `> 0`,
  защитник/рейдер — обязан `NULL`.

Индексы:

* `(sender_clan_id, status)` / `(receiver_clan_id, status)` — preflight
  `CreateCaravan` + cooldown-сканирование 12-часового окна.
* Partial-unique `(sender_clan_id) WHERE status IN ('lobby', 'in_battle')`
  — жёсткий БД-инвариант «у клана-отправителя ≤ 1 активного каравана».
* `(status, lobby_ends_at)` / `(status, battle_ends_at)` — recovery-скан
  после рестарта APScheduler-а: найти лобби/бои, чьи таймеры пропустили.
* `(caravan_id, role)` на `caravan_participants` — capacity-чек
  «сколько уже рейдеров/защитников» (см. `JoinCaravanLobby._ensure_capacity`).
* `UNIQUE (caravan_id, player_id)` на `caravan_participants` — БД-инвариант
  «один игрок может вступить в караван лишь один раз».
* Partial-unique `(caravan_id) WHERE is_leader=true` — у каждого
  каравана ровно один лидер (или пока не создан вовсе).

Расширений `audit_log_source_whitelist` миграция не делает — экономика
3.2-C ещё не приземлена; `caravan_reward` уже есть в whitelist
с миграции 0018 (заведено заранее под Спринт 3.2-C).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_caravans"
down_revision: str | Sequence[str] | None = "0018_pve_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "caravans",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("sender_clan_id", sa.BigInteger(), nullable=False),
        sa.Column("receiver_clan_id", sa.BigInteger(), nullable=False),
        sa.Column("leader_player_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lobby_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("battle_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("random_seed", sa.BigInteger(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_caravans"),
        sa.ForeignKeyConstraint(
            ["sender_clan_id"],
            ["clans.id"],
            name="fk_caravans_sender_clan_id_clans",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["receiver_clan_id"],
            ["clans.id"],
            name="fk_caravans_receiver_clan_id_clans",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["leader_player_id"],
            ["users.id"],
            name="fk_caravans_leader_player_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('lobby', 'in_battle', 'finished', 'cancelled')",
            name="ck_caravans_status_valid",
        ),
        sa.CheckConstraint(
            "sender_clan_id <> receiver_clan_id",
            name="ck_caravans_no_self_target",
        ),
        sa.CheckConstraint(
            "lobby_ends_at > started_at",
            name="ck_caravans_lobby_after_start",
        ),
        sa.CheckConstraint(
            "battle_ends_at > lobby_ends_at",
            name="ck_caravans_battle_after_lobby",
        ),
        sa.CheckConstraint(
            "((status = 'finished' OR status = 'cancelled') AND finished_at IS NOT NULL)"
            " OR ((status = 'lobby' OR status = 'in_battle') AND finished_at IS NULL)",
            name="ck_caravans_finished_at_matches_status",
        ),
    )
    op.create_index(
        "ix_caravans_sender_clan_id_status",
        "caravans",
        ["sender_clan_id", "status"],
    )
    op.create_index(
        "ix_caravans_receiver_clan_id_status",
        "caravans",
        ["receiver_clan_id", "status"],
    )
    op.create_index(
        "ix_caravans_status_lobby_ends_at",
        "caravans",
        ["status", "lobby_ends_at"],
    )
    op.create_index(
        "ix_caravans_status_battle_ends_at",
        "caravans",
        ["status", "battle_ends_at"],
    )
    op.create_index(
        "uq_caravans_one_active_per_sender",
        "caravans",
        ["sender_clan_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('lobby', 'in_battle')"),
        postgresql_where=sa.text("status IN ('lobby', 'in_battle')"),
    )

    op.create_table(
        "caravan_participants",
        sa.Column(
            "caravan_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
        ),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_leader", sa.Boolean(), nullable=False),
        sa.Column("contribution_cm", sa.Integer(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "caravan_id",
            "player_id",
            name="pk_caravan_participants",
        ),
        sa.ForeignKeyConstraint(
            ["caravan_id"],
            ["caravans.id"],
            name="fk_caravan_participants_caravan_id_caravans",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name="fk_caravan_participants_player_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "role IN ('caravaneer', 'defender', 'raider')",
            name="ck_caravan_participants_role_valid",
        ),
        sa.CheckConstraint(
            "(is_leader = 0 AND role IN ('caravaneer', 'defender', 'raider'))"
            " OR (is_leader = 1 AND role = 'caravaneer')",
            name="ck_caravan_participants_leader_implies_caravaneer",
        ),
        sa.CheckConstraint(
            "(role = 'caravaneer' AND contribution_cm IS NOT NULL AND contribution_cm > 0)"
            " OR (role IN ('defender', 'raider') AND contribution_cm IS NULL)",
            name="ck_caravan_participants_contribution_matches_role",
        ),
    )
    op.create_index(
        "ix_caravan_participants_caravan_id_role",
        "caravan_participants",
        ["caravan_id", "role"],
    )
    op.create_index(
        "ix_caravan_participants_player_id",
        "caravan_participants",
        ["player_id"],
    )
    op.create_index(
        "uq_caravan_participants_one_leader_per_caravan",
        "caravan_participants",
        ["caravan_id"],
        unique=True,
        sqlite_where=sa.text("is_leader = 1"),
        postgresql_where=sa.text("is_leader = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_caravan_participants_one_leader_per_caravan",
        table_name="caravan_participants",
    )
    op.drop_index(
        "ix_caravan_participants_player_id",
        table_name="caravan_participants",
    )
    op.drop_index(
        "ix_caravan_participants_caravan_id_role",
        table_name="caravan_participants",
    )
    op.drop_table("caravan_participants")
    op.drop_index(
        "uq_caravans_one_active_per_sender",
        table_name="caravans",
    )
    op.drop_index(
        "ix_caravans_status_battle_ends_at",
        table_name="caravans",
    )
    op.drop_index(
        "ix_caravans_status_lobby_ends_at",
        table_name="caravans",
    )
    op.drop_index(
        "ix_caravans_receiver_clan_id_status",
        table_name="caravans",
    )
    op.drop_index(
        "ix_caravans_sender_clan_id_status",
        table_name="caravans",
    )
    op.drop_table("caravans")
