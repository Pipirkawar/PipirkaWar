"""PvP duels schema (Sprint 2.1.C).

Две таблицы для агрегата `Duel` (домен 2.1.B):

* ``pvp_duels`` — корневая запись боя 1×1. Хранит весь жизненный
  цикл от ``PENDING_ACCEPT`` до ``COMPLETED``/``CANCELLED``,
  снэпшоты баланса (``hit_pct`` / ``expected_rounds``) и длин
  игроков на момент ``accept``-а, текущий pending-раунд (4 колонки
  для выборов p1/p2 — все nullable, заполняются по мере
  ``submit_move``-ов), и финальные дельты с ``winner``-ом, когда
  бой завершён.

* ``pvp_duel_rounds`` — completed-раунды (1:N от ``pvp_duels``,
  каскад на удаление). Каждая запись — результат ``resolve_round``
  (``RoundChoice``-ы обоих + флаги блокировок + нанесённые
  damage-ы). Ключ — ``(duel_id, round_num)``.

**State-related инварианты в БД** охраняются CHECK-констрейнтами:
``IN_PROGRESS`` ⇔ ``accepted_at NOT NULL`` ∧ ``pX_initial_length_cm NOT NULL``
∧ ``pending_round_num NOT NULL``; ``COMPLETED`` ⇔ ``completed_at NOT NULL``
∧ ``final_winner NOT NULL``; ``CANCELLED`` ⇔ ``cancelled_at NOT NULL``;
``PENDING_ACCEPT`` ⇔ всё остальное null. Это last-line-of-defense на
случай прямых SQL-правок в обход доменного слоя.

**Single-active-duel-per-player инвариант** — НЕ охраняется на уровне
БД: один игрок может иметь несколько ``PENDING_ACCEPT``-вызовов
(в разных чатах) и один ``IN_PROGRESS``-бой. Activity-lock
(``activity_locks`` table из 0.2) и use-case 2.1.D следят, чтобы
``IN_PROGRESS``-бой был не более одного. Дублировать как partial
unique index здесь — преждевременная оптимизация.

**Self-challenge** запрещён CHECK-ом ``challenger_id != challenged_id``
(когда ``challenged_id IS NOT NULL``).

Revision ID: 0009_pvp_duels
Revises: 0008_audit_log_delta_cm
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_pvp_duels"
down_revision: str | Sequence[str] | None = "0008_audit_log_delta_cm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pvp_duels",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column("challenger_id", sa.BigInteger(), nullable=False),
        # NULL для GLOBAL_ONLY-вызова до accept-а; задан в момент accept.
        sa.Column("challenged_id", sa.BigInteger(), nullable=True),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        # Снэпшот баланса в момент create_challenge.
        sa.Column("hit_pct", sa.Integer(), nullable=False),
        sa.Column("expected_rounds", sa.Integer(), nullable=False),
        # Снэпшот длин в момент accept (NULL до accept-а).
        sa.Column("p1_initial_length_cm", sa.Integer(), nullable=True),
        sa.Column("p2_initial_length_cm", sa.Integer(), nullable=True),
        # Времена жизненного цикла.
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        # Текущий pending-раунд (NULL вне IN_PROGRESS).
        sa.Column("pending_round_num", sa.Integer(), nullable=True),
        sa.Column("pending_p1_attack", sa.String(length=8), nullable=True),
        sa.Column("pending_p1_block", sa.String(length=8), nullable=True),
        sa.Column("pending_p2_attack", sa.String(length=8), nullable=True),
        sa.Column("pending_p2_block", sa.String(length=8), nullable=True),
        # Финальный исход (NULL до COMPLETED).
        sa.Column("final_p1_total_dealt", sa.Integer(), nullable=True),
        sa.Column("final_p2_total_dealt", sa.Integer(), nullable=True),
        sa.Column("final_p1_delta_cm", sa.Integer(), nullable=True),
        sa.Column("final_p2_delta_cm", sa.Integer(), nullable=True),
        sa.Column("final_winner", sa.String(length=8), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_pvp_duels"),
        sa.ForeignKeyConstraint(
            ["challenger_id"],
            ["users.id"],
            name="fk_pvp_duels_challenger_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["challenged_id"],
            ["users.id"],
            name="fk_pvp_duels_challenged_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "mode IN ('chat_then_global', 'chat_only', 'global_only')",
            name="ck_pvp_duels_mode_valid",
        ),
        sa.CheckConstraint(
            "state IN ('pending_accept', 'in_progress', 'completed', 'cancelled')",
            name="ck_pvp_duels_state_valid",
        ),
        sa.CheckConstraint(
            "hit_pct BETWEEN 0 AND 100",
            name="ck_pvp_duels_hit_pct_range",
        ),
        sa.CheckConstraint(
            "expected_rounds >= 1",
            name="ck_pvp_duels_expected_rounds_positive",
        ),
        sa.CheckConstraint(
            "challenged_id IS NULL OR challenger_id <> challenged_id",
            name="ck_pvp_duels_no_self_challenge",
        ),
        sa.CheckConstraint(
            "p1_initial_length_cm IS NULL OR p1_initial_length_cm >= 0",
            name="ck_pvp_duels_p1_length_non_negative",
        ),
        sa.CheckConstraint(
            "p2_initial_length_cm IS NULL OR p2_initial_length_cm >= 0",
            name="ck_pvp_duels_p2_length_non_negative",
        ),
        sa.CheckConstraint(
            "pending_round_num IS NULL OR pending_round_num >= 1",
            name="ck_pvp_duels_pending_round_positive",
        ),
        sa.CheckConstraint(
            "pending_p1_attack IS NULL OR pending_p1_attack IN ('high', 'mid', 'low')",
            name="ck_pvp_duels_pending_p1_attack_valid",
        ),
        sa.CheckConstraint(
            "pending_p1_block IS NULL OR pending_p1_block IN ('high', 'mid', 'low')",
            name="ck_pvp_duels_pending_p1_block_valid",
        ),
        sa.CheckConstraint(
            "pending_p2_attack IS NULL OR pending_p2_attack IN ('high', 'mid', 'low')",
            name="ck_pvp_duels_pending_p2_attack_valid",
        ),
        sa.CheckConstraint(
            "pending_p2_block IS NULL OR pending_p2_block IN ('high', 'mid', 'low')",
            name="ck_pvp_duels_pending_p2_block_valid",
        ),
        # Атака и блок одного игрока приходят парой: либо оба заданы,
        # либо оба NULL (игрок ещё не ответил в текущем раунде).
        sa.CheckConstraint(
            "(pending_p1_attack IS NULL AND pending_p1_block IS NULL)"
            " OR (pending_p1_attack IS NOT NULL AND pending_p1_block IS NOT NULL)",
            name="ck_pvp_duels_pending_p1_pair_consistent",
        ),
        sa.CheckConstraint(
            "(pending_p2_attack IS NULL AND pending_p2_block IS NULL)"
            " OR (pending_p2_attack IS NOT NULL AND pending_p2_block IS NOT NULL)",
            name="ck_pvp_duels_pending_p2_pair_consistent",
        ),
        sa.CheckConstraint(
            "final_winner IS NULL OR final_winner IN ('p1', 'p2', 'draw')",
            name="ck_pvp_duels_final_winner_valid",
        ),
        # Группа state-related инвариантов: каждое состояние — свой
        # шаблон NULL/NOT NULL.
        sa.CheckConstraint(
            "(state = 'pending_accept' AND accepted_at IS NULL"
            " AND completed_at IS NULL AND cancelled_at IS NULL"
            " AND p1_initial_length_cm IS NULL AND p2_initial_length_cm IS NULL"
            " AND pending_round_num IS NULL"
            " AND final_winner IS NULL)"
            " OR (state = 'in_progress' AND accepted_at IS NOT NULL"
            " AND completed_at IS NULL AND cancelled_at IS NULL"
            " AND p1_initial_length_cm IS NOT NULL AND p2_initial_length_cm IS NOT NULL"
            " AND pending_round_num IS NOT NULL"
            " AND final_winner IS NULL)"
            " OR (state = 'completed' AND accepted_at IS NOT NULL"
            " AND completed_at IS NOT NULL AND cancelled_at IS NULL"
            " AND p1_initial_length_cm IS NOT NULL AND p2_initial_length_cm IS NOT NULL"
            " AND pending_round_num IS NULL"
            " AND final_winner IS NOT NULL)"
            " OR (state = 'cancelled' AND cancelled_at IS NOT NULL)",
            name="ck_pvp_duels_state_invariants",
        ),
    )
    # Поиск активных боёв игрока (use-case 2.1.D — preflight перед ChallengeDuel).
    op.create_index(
        "ix_pvp_duels_challenger_id_state",
        "pvp_duels",
        ["challenger_id", "state"],
    )
    op.create_index(
        "ix_pvp_duels_challenged_id_state",
        "pvp_duels",
        ["challenged_id", "state"],
    )
    # Сканирование экспирированных pending-вызовов (job 2.1.F — auto-cancel/promote по TTL).
    op.create_index(
        "ix_pvp_duels_state_created_at",
        "pvp_duels",
        ["state", "created_at"],
    )

    op.create_table(
        "pvp_duel_rounds",
        sa.Column(
            "duel_id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            nullable=False,
        ),
        sa.Column("round_num", sa.Integer(), nullable=False),
        sa.Column("p1_attack", sa.String(length=8), nullable=False),
        sa.Column("p1_block", sa.String(length=8), nullable=False),
        sa.Column("p2_attack", sa.String(length=8), nullable=False),
        sa.Column("p2_block", sa.String(length=8), nullable=False),
        sa.Column("p1_attack_blocked", sa.Boolean(), nullable=False),
        sa.Column("p2_attack_blocked", sa.Boolean(), nullable=False),
        sa.Column("p1_damage_to_p2", sa.Integer(), nullable=False),
        sa.Column("p2_damage_to_p1", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("duel_id", "round_num", name="pk_pvp_duel_rounds"),
        sa.ForeignKeyConstraint(
            ["duel_id"],
            ["pvp_duels.id"],
            name="fk_pvp_duel_rounds_duel_id_pvp_duels",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "round_num >= 1",
            name="ck_pvp_duel_rounds_round_num_positive",
        ),
        sa.CheckConstraint(
            "p1_attack IN ('high', 'mid', 'low')",
            name="ck_pvp_duel_rounds_p1_attack_valid",
        ),
        sa.CheckConstraint(
            "p1_block IN ('high', 'mid', 'low')",
            name="ck_pvp_duel_rounds_p1_block_valid",
        ),
        sa.CheckConstraint(
            "p2_attack IN ('high', 'mid', 'low')",
            name="ck_pvp_duel_rounds_p2_attack_valid",
        ),
        sa.CheckConstraint(
            "p2_block IN ('high', 'mid', 'low')",
            name="ck_pvp_duel_rounds_p2_block_valid",
        ),
        sa.CheckConstraint(
            "p1_damage_to_p2 >= 0",
            name="ck_pvp_duel_rounds_p1_damage_non_negative",
        ),
        sa.CheckConstraint(
            "p2_damage_to_p1 >= 0",
            name="ck_pvp_duel_rounds_p2_damage_non_negative",
        ),
        # Damage и attack_blocked консистентны: если атака блокирована,
        # damage от этой атаки = 0.
        sa.CheckConstraint(
            "(p1_attack_blocked = 0 OR p1_damage_to_p2 = 0)",
            name="ck_pvp_duel_rounds_p1_damage_zero_when_blocked",
        ),
        sa.CheckConstraint(
            "(p2_attack_blocked = 0 OR p2_damage_to_p1 = 0)",
            name="ck_pvp_duel_rounds_p2_damage_zero_when_blocked",
        ),
    )


def downgrade() -> None:
    op.drop_table("pvp_duel_rounds")
    op.drop_index("ix_pvp_duels_state_created_at", table_name="pvp_duels")
    op.drop_index("ix_pvp_duels_challenged_id_state", table_name="pvp_duels")
    op.drop_index("ix_pvp_duels_challenger_id_state", table_name="pvp_duels")
    op.drop_table("pvp_duels")
