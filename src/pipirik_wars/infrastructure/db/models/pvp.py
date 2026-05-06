"""ORM-модели PvP-подсистемы (Спринт 2.1.C, расширено в 2.1.F).

Зеркалят миграции ``0009_pvp_duels`` и ``0010_pvp_global_lobby``:
``pvp_duels`` — корневая запись агрегата ``Duel`` (домен 2.1.B),
``pvp_duel_rounds`` — completed-раунды (1:N от duel-а с каскадным
удалением), ``pvp_global_lobby`` — FIFO-очередь pending-вызовов в
режиме ``GLOBAL_ONLY`` (1:1 от ``pvp_duels``).

State-related инварианты дублируются на CHECK-уровне БД (см.
миграцию). Доменные мутации (``Duel.accept`` / ``submit_move`` / ...)
собирают валидное состояние перед записью; CHECK-и срабатывают только
при ручных SQL-правках в обход доменного слоя.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base

# SQLite не умеет AUTOINCREMENT на BigInteger.
_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


class PvpDuelORM(Base):
    """Таблица ``pvp_duels`` — агрегат боя 1×1.

    Все state-related инварианты (PENDING_ACCEPT/IN_PROGRESS/COMPLETED/
    CANCELLED ↔ обязательность/null-абельность дат, длин, pending-раунда,
    финального исхода) охраняются комплексным CHECK-ом
    ``ck_pvp_duels_state_invariants`` на уровне миграции.
    """

    __tablename__ = "pvp_duels"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    challenger_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_pvp_duels_challenger_id_users"),
        nullable=False,
    )
    challenged_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_pvp_duels_challenged_id_users"),
        nullable=True,
    )
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    hit_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    p1_initial_length_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p2_initial_length_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_round_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_p1_attack: Mapped[str | None] = mapped_column(String(8), nullable=True)
    pending_p1_block: Mapped[str | None] = mapped_column(String(8), nullable=True)
    pending_p2_attack: Mapped[str | None] = mapped_column(String(8), nullable=True)
    pending_p2_block: Mapped[str | None] = mapped_column(String(8), nullable=True)
    final_p1_total_dealt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_p2_total_dealt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_p1_delta_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_p2_delta_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_winner: Mapped[str | None] = mapped_column(String(8), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "mode IN ('chat_then_global', 'chat_only', 'global_only')",
            name="ck_pvp_duels_mode_valid",
        ),
        CheckConstraint(
            "state IN ('pending_accept', 'in_progress', 'completed', 'cancelled')",
            name="ck_pvp_duels_state_valid",
        ),
        CheckConstraint(
            "hit_pct BETWEEN 0 AND 100",
            name="ck_pvp_duels_hit_pct_range",
        ),
        CheckConstraint(
            "expected_rounds >= 1",
            name="ck_pvp_duels_expected_rounds_positive",
        ),
        CheckConstraint(
            "challenged_id IS NULL OR challenger_id <> challenged_id",
            name="ck_pvp_duels_no_self_challenge",
        ),
        CheckConstraint(
            "p1_initial_length_cm IS NULL OR p1_initial_length_cm >= 0",
            name="ck_pvp_duels_p1_length_non_negative",
        ),
        CheckConstraint(
            "p2_initial_length_cm IS NULL OR p2_initial_length_cm >= 0",
            name="ck_pvp_duels_p2_length_non_negative",
        ),
        CheckConstraint(
            "pending_round_num IS NULL OR pending_round_num >= 1",
            name="ck_pvp_duels_pending_round_positive",
        ),
        CheckConstraint(
            "pending_p1_attack IS NULL OR pending_p1_attack IN ('high', 'mid', 'low')",
            name="ck_pvp_duels_pending_p1_attack_valid",
        ),
        CheckConstraint(
            "pending_p1_block IS NULL OR pending_p1_block IN ('high', 'mid', 'low')",
            name="ck_pvp_duels_pending_p1_block_valid",
        ),
        CheckConstraint(
            "pending_p2_attack IS NULL OR pending_p2_attack IN ('high', 'mid', 'low')",
            name="ck_pvp_duels_pending_p2_attack_valid",
        ),
        CheckConstraint(
            "pending_p2_block IS NULL OR pending_p2_block IN ('high', 'mid', 'low')",
            name="ck_pvp_duels_pending_p2_block_valid",
        ),
        CheckConstraint(
            "(pending_p1_attack IS NULL AND pending_p1_block IS NULL)"
            " OR (pending_p1_attack IS NOT NULL AND pending_p1_block IS NOT NULL)",
            name="ck_pvp_duels_pending_p1_pair_consistent",
        ),
        CheckConstraint(
            "(pending_p2_attack IS NULL AND pending_p2_block IS NULL)"
            " OR (pending_p2_attack IS NOT NULL AND pending_p2_block IS NOT NULL)",
            name="ck_pvp_duels_pending_p2_pair_consistent",
        ),
        CheckConstraint(
            "final_winner IS NULL OR final_winner IN ('p1', 'p2', 'draw')",
            name="ck_pvp_duels_final_winner_valid",
        ),
        CheckConstraint(
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
        Index("ix_pvp_duels_challenger_id_state", "challenger_id", "state"),
        Index("ix_pvp_duels_challenged_id_state", "challenged_id", "state"),
        Index("ix_pvp_duels_state_created_at", "state", "created_at"),
    )


class PvpDuelRoundORM(Base):
    """Таблица ``pvp_duel_rounds`` — completed-раунды (1:N от ``pvp_duels``).

    Запись создаётся в момент авторазрешения раунда (через
    ``Duel._resolve_pending_round`` после полного pending-раунда).
    Каскадное удаление при удалении родительского ``pvp_duels``-row-а
    (что технически не должно происходить — completed/cancelled боёв
    мы храним для аудита, — но конструктивно правильно).
    """

    __tablename__ = "pvp_duel_rounds"

    duel_id: Mapped[int] = mapped_column(
        _AutoIncBigInt,
        ForeignKey("pvp_duels.id", ondelete="CASCADE", name="fk_pvp_duel_rounds_duel_id_pvp_duels"),
        primary_key=True,
    )
    round_num: Mapped[int] = mapped_column(Integer, primary_key=True)
    p1_attack: Mapped[str] = mapped_column(String(8), nullable=False)
    p1_block: Mapped[str] = mapped_column(String(8), nullable=False)
    p2_attack: Mapped[str] = mapped_column(String(8), nullable=False)
    p2_block: Mapped[str] = mapped_column(String(8), nullable=False)
    p1_attack_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    p2_attack_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    p1_damage_to_p2: Mapped[int] = mapped_column(Integer, nullable=False)
    p2_damage_to_p1: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "round_num >= 1",
            name="ck_pvp_duel_rounds_round_num_positive",
        ),
        CheckConstraint(
            "p1_attack IN ('high', 'mid', 'low')",
            name="ck_pvp_duel_rounds_p1_attack_valid",
        ),
        CheckConstraint(
            "p1_block IN ('high', 'mid', 'low')",
            name="ck_pvp_duel_rounds_p1_block_valid",
        ),
        CheckConstraint(
            "p2_attack IN ('high', 'mid', 'low')",
            name="ck_pvp_duel_rounds_p2_attack_valid",
        ),
        CheckConstraint(
            "p2_block IN ('high', 'mid', 'low')",
            name="ck_pvp_duel_rounds_p2_block_valid",
        ),
        CheckConstraint(
            "p1_damage_to_p2 >= 0",
            name="ck_pvp_duel_rounds_p1_damage_non_negative",
        ),
        CheckConstraint(
            "p2_damage_to_p1 >= 0",
            name="ck_pvp_duel_rounds_p2_damage_non_negative",
        ),
        CheckConstraint(
            "(p1_attack_blocked = 0 OR p1_damage_to_p2 = 0)",
            name="ck_pvp_duel_rounds_p1_damage_zero_when_blocked",
        ),
        CheckConstraint(
            "(p2_attack_blocked = 0 OR p2_damage_to_p1 = 0)",
            name="ck_pvp_duel_rounds_p2_damage_zero_when_blocked",
        ),
    )


class PvpGlobalLobbyORM(Base):
    """Таблица ``pvp_global_lobby`` — FIFO-очередь PvP-вызовов в режиме
    ``GLOBAL_ONLY`` (Спринт 2.1.F).

    Связь 1:1 с ``pvp_duels`` через PK = ``duel_id`` (FK CASCADE).
    Запись добавляется через `EnqueueGlobalDuel` (use-case 2.1.F.2)
    и удаляется тремя путями:

    * успешный матч из лобби (`MatchFromLobby` → `AcceptDuel` →
      `IGlobalLobbyRepository.remove`);
    * истечение TTL (`ExpireLobbyEntry` → `lobby.remove` + `Duel.cancel`);
    * отмена вызова челленджером (`CancelDuel`-cleanup).

    FIFO-pop поддерживается индексом ``ix_pvp_global_lobby_enqueued_at``
    (``ORDER BY enqueued_at ASC LIMIT 1``).
    """

    __tablename__ = "pvp_global_lobby"

    duel_id: Mapped[int] = mapped_column(
        _AutoIncBigInt,
        ForeignKey(
            "pvp_duels.id",
            ondelete="CASCADE",
            name="fk_pvp_global_lobby_duel_id_pvp_duels",
        ),
        primary_key=True,
    )
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_pvp_global_lobby_enqueued_at", "enqueued_at"),)


class PvpMassDuelORM(Base):
    """Таблица ``pvp_mass_duels`` — корневой row массового PvP-боя клан×клан
    (Спринт 2.2.D).

    Все state-related инварианты (IN_PROGRESS/COMPLETED/CANCELLED ↔
    обязательность/null-абельность ``completed_at`` / ``cancelled_at`` /
    финальных дельт и ``final_winner``) охраняются комплексным CHECK-ом
    ``ck_pvp_mass_duels_state_invariants``. Zero-sum инвариант (Σ delta = 0)
    охраняется отдельным CHECK-ом для дополнительной защиты от ручных
    SQL-правок в обход доменного слоя.
    """

    __tablename__ = "pvp_mass_duels"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    clan1_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clans.id", ondelete="CASCADE", name="fk_pvp_mass_duels_clan1_id_clans"),
        nullable=False,
    )
    clan2_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clans.id", ondelete="CASCADE", name="fk_pvp_mass_duels_clan2_id_clans"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    hit_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_clan1_total_dealt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_clan2_total_dealt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_clan1_delta_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_clan2_delta_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_winner: Mapped[str | None] = mapped_column(String(8), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "state IN ('in_progress', 'completed', 'cancelled')",
            name="ck_pvp_mass_duels_state_valid",
        ),
        CheckConstraint(
            "hit_pct BETWEEN 0 AND 100",
            name="ck_pvp_mass_duels_hit_pct_range",
        ),
        CheckConstraint(
            "clan1_id <> clan2_id",
            name="ck_pvp_mass_duels_no_self_team",
        ),
        CheckConstraint(
            "final_winner IS NULL OR final_winner IN ('clan1', 'clan2', 'draw')",
            name="ck_pvp_mass_duels_final_winner_valid",
        ),
        CheckConstraint(
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
        CheckConstraint(
            "final_clan1_delta_cm IS NULL OR (final_clan1_delta_cm + final_clan2_delta_cm) = 0",
            name="ck_pvp_mass_duels_zero_sum_delta",
        ),
        CheckConstraint(
            "final_clan1_total_dealt IS NULL OR final_clan1_total_dealt >= 0",
            name="ck_pvp_mass_duels_clan1_total_dealt_non_negative",
        ),
        CheckConstraint(
            "final_clan2_total_dealt IS NULL OR final_clan2_total_dealt >= 0",
            name="ck_pvp_mass_duels_clan2_total_dealt_non_negative",
        ),
        Index("ix_pvp_mass_duels_clan1_id_state", "clan1_id", "state"),
        Index("ix_pvp_mass_duels_clan2_id_state", "clan2_id", "state"),
        Index("ix_pvp_mass_duels_state_created_at", "state", "created_at"),
    )


class PvpMassDuelChoiceORM(Base):
    """Таблица ``pvp_mass_duel_choices`` — ростер + выборы участников
    массового боя (Спринт 2.2.D, 1:N от ``pvp_mass_duels``).

    Один row на каждого игрока обеих сторон. Запись создаётся в
    ``MassDuel.create_battle`` (через ``add(...)``-репозитория) с
    заполненным ``initial_length_cm``; ``attack``/``block``/
    ``submitted_at`` остаются NULL до ``submit_move(...)``.
    """

    __tablename__ = "pvp_mass_duel_choices"

    duel_id: Mapped[int] = mapped_column(
        _AutoIncBigInt,
        ForeignKey(
            "pvp_mass_duels.id",
            ondelete="CASCADE",
            name="fk_pvp_mass_duel_choices_duel_id_pvp_mass_duels",
        ),
        primary_key=True,
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_pvp_mass_duel_choices_player_id_users",
        ),
        primary_key=True,
    )
    clan_side: Mapped[str] = mapped_column(String(8), nullable=False)
    initial_length_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    attack: Mapped[str | None] = mapped_column(String(8), nullable=True)
    block: Mapped[str | None] = mapped_column(String(8), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "clan_side IN ('clan1', 'clan2')",
            name="ck_pvp_mass_duel_choices_clan_side_valid",
        ),
        CheckConstraint(
            "initial_length_cm >= 0",
            name="ck_pvp_mass_duel_choices_length_non_negative",
        ),
        CheckConstraint(
            "attack IS NULL OR attack IN ('high', 'mid', 'low')",
            name="ck_pvp_mass_duel_choices_attack_valid",
        ),
        CheckConstraint(
            "block IS NULL OR block IN ('high', 'mid', 'low')",
            name="ck_pvp_mass_duel_choices_block_valid",
        ),
        CheckConstraint(
            "(attack IS NULL AND block IS NULL) OR (attack IS NOT NULL AND block IS NOT NULL)",
            name="ck_pvp_mass_duel_choices_pair_consistent",
        ),
        CheckConstraint(
            "(attack IS NULL AND submitted_at IS NULL)"
            " OR (attack IS NOT NULL AND submitted_at IS NOT NULL)",
            name="ck_pvp_mass_duel_choices_submitted_at_consistent",
        ),
        Index("ix_pvp_mass_duel_choices_player_id", "player_id"),
    )


class PvpMassDuelDamageEntryORM(Base):
    """Таблица ``pvp_mass_duel_damage_entries`` — отрезолвенные удары
    массового боя (Спринт 2.2.D, 1:N от ``pvp_mass_duels``, заполняется
    только для COMPLETED-боёв).

    Хранит 0-based ``entry_idx`` для сохранения порядка tuple-а
    ``MassRoundOutcome.damage_entries``. Запись иммутабельна после
    ``MassDuel.resolve(...)`` (как и сам outcome в домене).
    """

    __tablename__ = "pvp_mass_duel_damage_entries"

    duel_id: Mapped[int] = mapped_column(
        _AutoIncBigInt,
        ForeignKey(
            "pvp_mass_duels.id",
            ondelete="CASCADE",
            name="fk_pvp_mass_duel_damage_entries_duel_id_pvp_mass_duels",
        ),
        primary_key=True,
    )
    entry_idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    attacker_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_pvp_mass_duel_damage_entries_attacker_id_users",
        ),
        nullable=False,
    )
    defender_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_pvp_mass_duel_damage_entries_defender_id_users",
        ),
        nullable=False,
    )
    attacker_attack: Mapped[str] = mapped_column(String(8), nullable=False)
    defender_block: Mapped[str] = mapped_column(String(8), nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    damage_cm: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "entry_idx >= 0",
            name="ck_pvp_mass_duel_damage_entries_idx_non_negative",
        ),
        CheckConstraint(
            "attacker_id <> defender_id",
            name="ck_pvp_mass_duel_damage_entries_no_self",
        ),
        CheckConstraint(
            "attacker_attack IN ('high', 'mid', 'low')",
            name="ck_pvp_mass_duel_damage_entries_attack_valid",
        ),
        CheckConstraint(
            "defender_block IN ('high', 'mid', 'low')",
            name="ck_pvp_mass_duel_damage_entries_block_valid",
        ),
        CheckConstraint(
            "damage_cm >= 0",
            name="ck_pvp_mass_duel_damage_entries_damage_non_negative",
        ),
        CheckConstraint(
            "(blocked = 0 OR damage_cm = 0)",
            name="ck_pvp_mass_duel_damage_entries_damage_zero_when_blocked",
        ),
    )
