"""PvP mass-duels schema (Sprint 2.2.D).

Три таблицы для агрегата `MassDuel` (домен 2.2.C):

* ``pvp_mass_duels`` — корневая запись массового боя клан×клан.
  Хранит весь жизненный цикл от ``IN_PROGRESS`` до
  ``COMPLETED``/``CANCELLED``, snapshot-`hit_pct` (на момент старта
  боя; `/balance_reload` посреди боя не сбивает экономику текущего
  массового боя), времена жизненного цикла и финальные дельты с
  ``winner``-ом, когда бой завершён. Состояния ``PENDING_ACCEPT``
  здесь нет (в отличие от 1×1) — массовый бой не требует
  подтверждения, обе стороны автозаписываются на use-case-уровне
  2.2.E и сразу переходят в ``IN_PROGRESS``.

* ``pvp_mass_duel_choices`` — все участники боя (1:N от
  ``pvp_mass_duels``, каскад на удаление). Один row на каждого
  игрока обеих сторон. Поля ``clan_side`` (``clan1``/``clan2``) и
  ``initial_length_cm`` (snapshot длины на момент `create_battle`)
  — заполнены сразу. Поля ``attack``/``block``/``submitted_at`` —
  nullable, заполняются на ``submit_move(...)``. Состав
  участников фиксируется при ``add(...)``: ростер замораживается
  (никто не может присоединиться/уйти посреди боя).

* ``pvp_mass_duel_damage_entries`` — отрезолвенные удары
  (``MassDamageEntry`` × N, 1:N от ``pvp_mass_duels``, каскад).
  Заполняется только для COMPLETED-боёв через ``save(...)``;
  иммутабельно после ``resolve(...)``. Порядок сохраняется через
  ``entry_idx`` (0-based), повторяющий порядок tuple-а
  ``MassRoundOutcome.damage_entries``.

State-related инварианты охраняются CHECK-констрейнтами уровня БД
(last-line-of-defense на случай прямых SQL-правок в обход доменного
слоя):

* ``IN_PROGRESS`` ⇔ ``completed_at IS NULL ∧ cancelled_at IS NULL ∧
  final_winner IS NULL``;
* ``COMPLETED`` ⇔ ``completed_at NOT NULL ∧ cancelled_at IS NULL ∧
  final_winner NOT NULL ∧ все final_* NOT NULL``;
* ``CANCELLED`` ⇔ ``cancelled_at NOT NULL ∧ final_winner IS NULL``.

Self-team (``clan1_id == clan2_id``) запрещён CHECK-ом
``ck_pvp_mass_duels_no_self_team``. Pairing себя-в-себя в одном бою
(`clan_side='clan1' ∧ clan_side='clan2'` для одного `player_id`)
дополнительно отсекается ROSTER-инвариантом домена (`MassDuel.__post_init__`)
и не нуждается в CHECK-е на уровне БД (use-case 2.2.E фильтрует
пересечения ростеров до `MassDuel.create_battle`, ГДД §7.2 / 2.2.3).

Revision ID: 0011_pvp_mass_duels
Revises: 0010_pvp_global_lobby
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_pvp_mass_duels"
down_revision: str | Sequence[str] | None = "0010_pvp_global_lobby"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pvp_mass_duels",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("clan1_id", sa.BigInteger(), nullable=False),
        sa.Column("clan2_id", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        # Снэпшот баланса на момент create_battle.
        sa.Column("hit_pct", sa.Integer(), nullable=False),
        # Времена жизненного цикла.
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        # Финальный исход (NULL до COMPLETED).
        sa.Column("final_clan1_total_dealt", sa.Integer(), nullable=True),
        sa.Column("final_clan2_total_dealt", sa.Integer(), nullable=True),
        sa.Column("final_clan1_delta_cm", sa.Integer(), nullable=True),
        sa.Column("final_clan2_delta_cm", sa.Integer(), nullable=True),
        sa.Column("final_winner", sa.String(length=8), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_pvp_mass_duels"),
        sa.ForeignKeyConstraint(
            ["clan1_id"],
            ["clans.id"],
            name="fk_pvp_mass_duels_clan1_id_clans",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["clan2_id"],
            ["clans.id"],
            name="fk_pvp_mass_duels_clan2_id_clans",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "state IN ('in_progress', 'completed', 'cancelled')",
            name="ck_pvp_mass_duels_state_valid",
        ),
        sa.CheckConstraint(
            "hit_pct BETWEEN 0 AND 100",
            name="ck_pvp_mass_duels_hit_pct_range",
        ),
        sa.CheckConstraint(
            "clan1_id <> clan2_id",
            name="ck_pvp_mass_duels_no_self_team",
        ),
        sa.CheckConstraint(
            "final_winner IS NULL OR final_winner IN ('clan1', 'clan2', 'draw')",
            name="ck_pvp_mass_duels_final_winner_valid",
        ),
        # Группа state-related инвариантов: COMPLETED ⇒ все final_*
        # заполнены; IN_PROGRESS / CANCELLED ⇒ финальные = NULL.
        sa.CheckConstraint(
            "(state = 'in_progress' AND completed_at IS NULL"
            " AND cancelled_at IS NULL AND final_winner IS NULL"
            " AND final_clan1_total_dealt IS NULL AND final_clan2_total_dealt IS NULL"
            " AND final_clan1_delta_cm IS NULL AND final_clan2_delta_cm IS NULL)"
            " OR (state = 'completed' AND completed_at IS NOT NULL"
            " AND cancelled_at IS NULL AND final_winner IS NOT NULL"
            " AND final_clan1_total_dealt IS NOT NULL"
            " AND final_clan2_total_dealt IS NOT NULL"
            " AND final_clan1_delta_cm IS NOT NULL"
            " AND final_clan2_delta_cm IS NOT NULL)"
            " OR (state = 'cancelled' AND cancelled_at IS NOT NULL"
            " AND completed_at IS NULL AND final_winner IS NULL"
            " AND final_clan1_total_dealt IS NULL AND final_clan2_total_dealt IS NULL"
            " AND final_clan1_delta_cm IS NULL AND final_clan2_delta_cm IS NULL)",
            name="ck_pvp_mass_duels_state_invariants",
        ),
        # Zero-sum при COMPLETED: clan1_delta + clan2_delta == 0.
        sa.CheckConstraint(
            "final_clan1_delta_cm IS NULL OR (final_clan1_delta_cm + final_clan2_delta_cm) = 0",
            name="ck_pvp_mass_duels_zero_sum_delta",
        ),
        # Total_dealt не может быть отрицательным.
        sa.CheckConstraint(
            "final_clan1_total_dealt IS NULL OR final_clan1_total_dealt >= 0",
            name="ck_pvp_mass_duels_clan1_total_dealt_non_negative",
        ),
        sa.CheckConstraint(
            "final_clan2_total_dealt IS NULL OR final_clan2_total_dealt >= 0",
            name="ck_pvp_mass_duels_clan2_total_dealt_non_negative",
        ),
    )
    # Поиск по парам кланов + дате (use-case 2.2.E — поиск активных
    # массовых боёв конкретного клана для проверки кулдауна 6h).
    op.create_index(
        "ix_pvp_mass_duels_clan1_id_state",
        "pvp_mass_duels",
        ["clan1_id", "state"],
    )
    op.create_index(
        "ix_pvp_mass_duels_clan2_id_state",
        "pvp_mass_duels",
        ["clan2_id", "state"],
    )
    op.create_index(
        "ix_pvp_mass_duels_state_created_at",
        "pvp_mass_duels",
        ["state", "created_at"],
    )

    op.create_table(
        "pvp_mass_duel_choices",
        sa.Column(
            "duel_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
        ),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("clan_side", sa.String(length=8), nullable=False),
        # Снэпшот длины на момент create_battle (path-independent).
        sa.Column("initial_length_cm", sa.Integer(), nullable=False),
        # Выбор игрока на единственный тик массового боя; заполняется
        # на submit_move или force_submit_missing.
        sa.Column("attack", sa.String(length=8), nullable=True),
        sa.Column("block", sa.String(length=8), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("duel_id", "player_id", name="pk_pvp_mass_duel_choices"),
        sa.ForeignKeyConstraint(
            ["duel_id"],
            ["pvp_mass_duels.id"],
            name="fk_pvp_mass_duel_choices_duel_id_pvp_mass_duels",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["users.id"],
            name="fk_pvp_mass_duel_choices_player_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "clan_side IN ('clan1', 'clan2')",
            name="ck_pvp_mass_duel_choices_clan_side_valid",
        ),
        sa.CheckConstraint(
            "initial_length_cm >= 0",
            name="ck_pvp_mass_duel_choices_length_non_negative",
        ),
        sa.CheckConstraint(
            "attack IS NULL OR attack IN ('high', 'mid', 'low')",
            name="ck_pvp_mass_duel_choices_attack_valid",
        ),
        sa.CheckConstraint(
            "block IS NULL OR block IN ('high', 'mid', 'low')",
            name="ck_pvp_mass_duel_choices_block_valid",
        ),
        # Атака и блок одного игрока приходят парой: либо оба заданы
        # (выбор отправлен), либо оба NULL (ещё не отправил).
        sa.CheckConstraint(
            "(attack IS NULL AND block IS NULL) OR (attack IS NOT NULL AND block IS NOT NULL)",
            name="ck_pvp_mass_duel_choices_pair_consistent",
        ),
        # submitted_at согласован с парой attack/block.
        sa.CheckConstraint(
            "(attack IS NULL AND submitted_at IS NULL)"
            " OR (attack IS NOT NULL AND submitted_at IS NOT NULL)",
            name="ck_pvp_mass_duel_choices_submitted_at_consistent",
        ),
    )
    # Поиск участников боя для use-case 2.2.E (preflight перед submit_move).
    op.create_index(
        "ix_pvp_mass_duel_choices_player_id",
        "pvp_mass_duel_choices",
        ["player_id"],
    )

    op.create_table(
        "pvp_mass_duel_damage_entries",
        sa.Column(
            "duel_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
        ),
        # 0-based индекс в tuple-е MassRoundOutcome.damage_entries —
        # сохраняет порядок резолва (sortable-mapping вместо UNIQUE+ORDER BY).
        sa.Column("entry_idx", sa.Integer(), nullable=False),
        sa.Column("attacker_id", sa.BigInteger(), nullable=False),
        sa.Column("defender_id", sa.BigInteger(), nullable=False),
        sa.Column("attacker_attack", sa.String(length=8), nullable=False),
        sa.Column("defender_block", sa.String(length=8), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("damage_cm", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("duel_id", "entry_idx", name="pk_pvp_mass_duel_damage_entries"),
        sa.ForeignKeyConstraint(
            ["duel_id"],
            ["pvp_mass_duels.id"],
            name="fk_pvp_mass_duel_damage_entries_duel_id_pvp_mass_duels",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attacker_id"],
            ["users.id"],
            name="fk_pvp_mass_duel_damage_entries_attacker_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["defender_id"],
            ["users.id"],
            name="fk_pvp_mass_duel_damage_entries_defender_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "entry_idx >= 0",
            name="ck_pvp_mass_duel_damage_entries_idx_non_negative",
        ),
        sa.CheckConstraint(
            "attacker_id <> defender_id",
            name="ck_pvp_mass_duel_damage_entries_no_self",
        ),
        sa.CheckConstraint(
            "attacker_attack IN ('high', 'mid', 'low')",
            name="ck_pvp_mass_duel_damage_entries_attack_valid",
        ),
        sa.CheckConstraint(
            "defender_block IN ('high', 'mid', 'low')",
            name="ck_pvp_mass_duel_damage_entries_block_valid",
        ),
        sa.CheckConstraint(
            "damage_cm >= 0",
            name="ck_pvp_mass_duel_damage_entries_damage_non_negative",
        ),
        # Damage и blocked консистентны: если атака блокирована, damage = 0.
        sa.CheckConstraint(
            "(blocked = 0 OR damage_cm = 0)",
            name="ck_pvp_mass_duel_damage_entries_damage_zero_when_blocked",
        ),
    )


def downgrade() -> None:
    op.drop_table("pvp_mass_duel_damage_entries")
    op.drop_index(
        "ix_pvp_mass_duel_choices_player_id",
        table_name="pvp_mass_duel_choices",
    )
    op.drop_table("pvp_mass_duel_choices")
    op.drop_index(
        "ix_pvp_mass_duels_state_created_at",
        table_name="pvp_mass_duels",
    )
    op.drop_index(
        "ix_pvp_mass_duels_clan2_id_state",
        table_name="pvp_mass_duels",
    )
    op.drop_index(
        "ix_pvp_mass_duels_clan1_id_state",
        table_name="pvp_mass_duels",
    )
    op.drop_table("pvp_mass_duels")
