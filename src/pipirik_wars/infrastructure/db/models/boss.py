"""ORM-модели рейд-боссов и их участников (Спринт 3.3-B, ГДД §10).

Зеркалят структуру миграции `0020_boss_fights` (см. там же подробное
описание CHECK-инвариантов и индексов). Здесь они продублированы для
случая `Base.metadata.create_all()` в integration-тестах (см. fixtures
в `tests/integration/db/`).

Имена ограничений / индексов **обязаны** совпадать с миграцией
`0020_boss_fights` — иначе `alembic` будет падать на drop-е constraint-а
в downgrade-е, а Postgres — на конфликте имён.

Босс хранится **на корневой таблице** `boss_fights` (поле
`boss_player_id`), а не в `boss_participants` — это даёт O(1) доступ
к HP босса в раунд-резолверe (Спринт 3.3-C) и упрощает модель «один
босс ↔ N рейдеров» (см. ГДД §10.3).
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base

# SQLite не поддерживает AUTOINCREMENT на BigInteger; в Postgres — bigserial.
_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


class BossFightORM(Base):
    """Таблица `boss_fights` — корневая запись рейд-боя (ГДД §10)."""

    __tablename__ = "boss_fights"

    id: Mapped[int] = mapped_column(
        _AutoIncBigInt,
        primary_key=True,
        autoincrement=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    summoner_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_boss_fights_summoner_player_id_users",
        ),
        nullable=False,
    )
    boss_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_boss_fights_boss_player_id_users",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lobby_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    random_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    initial_boss_length_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    current_boss_length_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('raid')",
            name="ck_boss_fights_kind_valid",
        ),
        CheckConstraint(
            "status IN ('lobby', 'in_battle', 'finished', 'cancelled')",
            name="ck_boss_fights_status_valid",
        ),
        CheckConstraint(
            "summoner_player_id <> boss_player_id",
            name="ck_boss_fights_summoner_not_boss",
        ),
        CheckConstraint(
            "lobby_ends_at > started_at",
            name="ck_boss_fights_lobby_after_start",
        ),
        CheckConstraint(
            "initial_boss_length_cm > 0",
            name="ck_boss_fights_initial_boss_length_positive",
        ),
        CheckConstraint(
            "current_boss_length_cm >= 0",
            name="ck_boss_fights_current_boss_length_non_negative",
        ),
        CheckConstraint(
            "current_boss_length_cm <= initial_boss_length_cm",
            name="ck_boss_fights_current_boss_length_le_initial",
        ),
        CheckConstraint(
            "current_round >= 0",
            name="ck_boss_fights_current_round_non_negative",
        ),
        CheckConstraint(
            "((status = 'finished' OR status = 'cancelled') AND finished_at IS NOT NULL)"
            " OR ((status = 'lobby' OR status = 'in_battle') AND finished_at IS NULL)",
            name="ck_boss_fights_finished_at_matches_status",
        ),
        Index(
            "ix_boss_fights_status_lobby_ends_at",
            "status",
            "lobby_ends_at",
        ),
        Index(
            "ix_boss_fights_status_finished_at",
            "status",
            "finished_at",
        ),
        Index(
            "ix_boss_fights_summoner_player_id_status",
            "summoner_player_id",
            "status",
        ),
        Index(
            "ix_boss_fights_boss_player_id_status",
            "boss_player_id",
            "status",
        ),
        Index(
            "ix_boss_fights_started_at",
            "started_at",
        ),
    )


class BossParticipantORM(Base):
    """Таблица `boss_participants` — рейдер ↔ рейд-бой (ГДД §10.3).

    Композитный PK `(boss_fight_id, player_id)` — игрок может состоять
    в каждом рейде ровно один раз. Доменная сущность `BossParticipant`
    тоже не имеет суррогатного `id` — `(boss_fight_id, player_id)`
    образует естественный ключ.

    Босс **не хранится** в этой таблице — он на `BossFightORM.boss_player_id`.
    """

    __tablename__ = "boss_participants"

    boss_fight_id: Mapped[int] = mapped_column(
        _AutoIncBigInt,
        ForeignKey(
            "boss_fights.id",
            ondelete="CASCADE",
            name="fk_boss_participants_boss_fight_id_boss_fights",
        ),
        primary_key=True,
        nullable=False,
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_boss_participants_player_id_users",
        ),
        primary_key=True,
        nullable=False,
    )
    is_summoner: Mapped[bool] = mapped_column(Boolean, nullable=False)
    length_at_join_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "length_at_join_cm > 0",
            name="ck_boss_participants_length_positive",
        ),
        Index(
            "ix_boss_participants_player_id",
            "player_id",
        ),
        Index(
            "uq_boss_participants_one_summoner_per_boss_fight",
            "boss_fight_id",
            unique=True,
            sqlite_where=text("is_summoner = 1"),
            postgresql_where=text("is_summoner = true"),
        ),
    )


__all__ = ["BossFightORM", "BossParticipantORM"]
