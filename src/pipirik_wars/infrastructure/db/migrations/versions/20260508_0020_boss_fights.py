"""Boss fights persistence (Спринт 3.3-B, ГДД §10): boss_fights + boss_participants.

Доменный слой 3.3-A добавил `domain/bosses/` (Спринт 3.3-A, PR #112):
агрегат `BossFight` + участник `BossParticipant` + порты-репо. Эта
миграция (3.3-B) приземляет их на БД:

1. **`boss_fights`** — корневая таблица рейд-боя (один row на бой).
   Хранит весь жизненный цикл `LOBBY → IN_BATTLE → FINISHED|CANCELLED`,
   `random_seed` (snapshot для воспроизводимости резолва раундов 3.3-C),
   тип босса (`kind`, на старте 3.3 — только `'raid'`), временные
   метки `started_at`/`lobby_ends_at`/`finished_at`, ссылки на
   саммонера и игрока-босса (`summoner_player_id` / `boss_player_id`).
   Поля HP босса (`initial_boss_length_cm`, `current_boss_length_cm`)
   и счётчик раундов (`current_round`) хранятся прямо на агрегате —
   босс **не пишется** в `boss_participants` (см. ГДД §10.3).

2. **`boss_participants`** — 1:N от `boss_fights`, каскад на удаление.
   Один row на каждого рейдера; `is_summoner=true` ровно у одного
   рейдера — у саммонера, который кинул вызов. Босс здесь не хранится.

CHECK-инварианты — last-line-of-defense на случай прямых SQL-правок:

* `boss_fights.kind IN ('raid')` (ГДД §10 — только этот тип на 3.3);
* `boss_fights.status IN ('lobby', 'in_battle', 'finished', 'cancelled')`;
* `summoner_player_id <> boss_player_id` (саммонер не может быть боссом);
* `lobby_ends_at > started_at`;
* `initial_boss_length_cm > 0`;
* `current_boss_length_cm >= 0` и `current_boss_length_cm <= initial_boss_length_cm`;
* `current_round >= 0`;
* `(status='finished' OR status='cancelled') AND finished_at IS NOT NULL`
  ИЛИ `(status='lobby' OR status='in_battle') AND finished_at IS NULL`;
* `boss_participants.length_at_join_cm > 0`.

Индексы:

* `(status, lobby_ends_at)` / `(status, finished_at)` — recovery-скан
  после рестарта APScheduler-а: найти лобби/бои, чьи таймеры пропустили.
* `(summoner_player_id, status)` / `(boss_player_id, status)` —
  preflight `SummonBoss`-а («у этого игрока уже есть активный рейд?»);
  активность саммонера ловится `activity_lock`-ом, но индекс ускоряет
  ad-hoc admin-запросы.
* `started_at` (DESC через order_by) — `get_last_global_started_at`-запрос
  «когда был последний призыв на сервере» (4-часовой глобальный кулдаун
  ГДД §10.1).
* `(boss_fight_id, player_id)` — композитный PK, гарантирует «один
  игрок — один рейд — одна запись» (UNIQUE на БД-уровне).
* Partial-unique `(boss_fight_id) WHERE is_summoner=true` — у каждого
  рейда ровно один саммонер.

Расширений `audit_log_source_whitelist` миграция не делает — рейд-бой
не выдаёт прямых наград длиной (резолв раундов и награды — Спринт 3.3-C);
там же будет добавлен соответствующий source-key, если он появится в
audit-экономике.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_boss_fights"
down_revision: str | Sequence[str] | None = "0019_caravans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "boss_fights",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("summoner_player_id", sa.BigInteger(), nullable=False),
        sa.Column("boss_player_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lobby_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("random_seed", sa.BigInteger(), nullable=False),
        sa.Column("initial_boss_length_cm", sa.Integer(), nullable=False),
        sa.Column("current_boss_length_cm", sa.Integer(), nullable=False),
        sa.Column("current_round", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_boss_fights"),
        sa.ForeignKeyConstraint(
            ["summoner_player_id"],
            ["users.id"],
            name="fk_boss_fights_summoner_player_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["boss_player_id"],
            ["users.id"],
            name="fk_boss_fights_boss_player_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('raid')",
            name="ck_boss_fights_kind_valid",
        ),
        sa.CheckConstraint(
            "status IN ('lobby', 'in_battle', 'finished', 'cancelled')",
            name="ck_boss_fights_status_valid",
        ),
        sa.CheckConstraint(
            "summoner_player_id <> boss_player_id",
            name="ck_boss_fights_summoner_not_boss",
        ),
        sa.CheckConstraint(
            "lobby_ends_at > started_at",
            name="ck_boss_fights_lobby_after_start",
        ),
        sa.CheckConstraint(
            "initial_boss_length_cm > 0",
            name="ck_boss_fights_initial_boss_length_positive",
        ),
        sa.CheckConstraint(
            "current_boss_length_cm >= 0",
            name="ck_boss_fights_current_boss_length_non_negative",
        ),
        sa.CheckConstraint(
            "current_boss_length_cm <= initial_boss_length_cm",
            name="ck_boss_fights_current_boss_length_le_initial",
        ),
        sa.CheckConstraint(
            "current_round >= 0",
            name="ck_boss_fights_current_round_non_negative",
        ),
        sa.CheckConstraint(
            "((status = 'finished' OR status = 'cancelled') AND finished_at IS NOT NULL)"
            " OR ((status = 'lobby' OR status = 'in_battle') AND finished_at IS NULL)",
            name="ck_boss_fights_finished_at_matches_status",
        ),
    )
    op.create_index(
        "ix_boss_fights_status_lobby_ends_at",
        "boss_fights",
        ["status", "lobby_ends_at"],
    )
    op.create_index(
        "ix_boss_fights_status_finished_at",
        "boss_fights",
        ["status", "finished_at"],
    )
    op.create_index(
        "ix_boss_fights_summoner_player_id_status",
        "boss_fights",
        ["summoner_player_id", "status"],
    )
    op.create_index(
        "ix_boss_fights_boss_player_id_status",
        "boss_fights",
        ["boss_player_id", "status"],
    )
    op.create_index(
        "ix_boss_fights_started_at",
        "boss_fights",
        ["started_at"],
    )

    op.create_table(
        "boss_participants",
        sa.Column(
            "boss_fight_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
        ),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("is_summoner", sa.Boolean(), nullable=False),
        sa.Column("length_at_join_cm", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "boss_fight_id",
            "player_id",
            name="pk_boss_participants",
        ),
        sa.ForeignKeyConstraint(
            ["boss_fight_id"],
            ["boss_fights.id"],
            name="fk_boss_participants_boss_fight_id_boss_fights",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name="fk_boss_participants_player_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "length_at_join_cm > 0",
            name="ck_boss_participants_length_positive",
        ),
    )
    op.create_index(
        "ix_boss_participants_player_id",
        "boss_participants",
        ["player_id"],
    )
    op.create_index(
        "uq_boss_participants_one_summoner_per_boss_fight",
        "boss_participants",
        ["boss_fight_id"],
        unique=True,
        sqlite_where=sa.text("is_summoner = 1"),
        postgresql_where=sa.text("is_summoner = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_boss_participants_one_summoner_per_boss_fight",
        table_name="boss_participants",
    )
    op.drop_index(
        "ix_boss_participants_player_id",
        table_name="boss_participants",
    )
    op.drop_table("boss_participants")
    op.drop_index(
        "ix_boss_fights_started_at",
        table_name="boss_fights",
    )
    op.drop_index(
        "ix_boss_fights_boss_player_id_status",
        table_name="boss_fights",
    )
    op.drop_index(
        "ix_boss_fights_summoner_player_id_status",
        table_name="boss_fights",
    )
    op.drop_index(
        "ix_boss_fights_status_finished_at",
        table_name="boss_fights",
    )
    op.drop_index(
        "ix_boss_fights_status_lobby_ends_at",
        table_name="boss_fights",
    )
    op.drop_table("boss_fights")
