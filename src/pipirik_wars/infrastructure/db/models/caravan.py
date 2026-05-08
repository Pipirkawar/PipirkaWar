"""ORM-модели каравана и его участников (Спринт 3.2-B, ГДД §9).

Зеркалят структуру миграции `0019_caravans` (см. там же подробное описание
CHECK-инвариантов и индексов). Здесь они продублированы для случая
`Base.metadata.create_all()` в integration-тестах (см. fixtures в
`tests/integration/db/`).

Имена ограничений / индексов **обязаны** совпадать с миграцией
`0019_caravans` — иначе `alembic` будет падать на drop-е constraint-а
в downgrade-е, а Postgres — на конфликте имён.
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


class CaravanORM(Base):
    """Таблица `caravans` — корневая запись каравана (ГДД §9)."""

    __tablename__ = "caravans"

    id: Mapped[int] = mapped_column(
        _AutoIncBigInt,
        primary_key=True,
        autoincrement=True,
    )
    sender_clan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "clans.id",
            ondelete="CASCADE",
            name="fk_caravans_sender_clan_id_clans",
        ),
        nullable=False,
    )
    receiver_clan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "clans.id",
            ondelete="CASCADE",
            name="fk_caravans_receiver_clan_id_clans",
        ),
        nullable=False,
    )
    leader_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_caravans_leader_player_id_users",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lobby_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    battle_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    random_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('lobby', 'in_battle', 'finished', 'cancelled')",
            name="ck_caravans_status_valid",
        ),
        CheckConstraint(
            "sender_clan_id <> receiver_clan_id",
            name="ck_caravans_no_self_target",
        ),
        CheckConstraint(
            "lobby_ends_at > started_at",
            name="ck_caravans_lobby_after_start",
        ),
        CheckConstraint(
            "battle_ends_at > lobby_ends_at",
            name="ck_caravans_battle_after_lobby",
        ),
        CheckConstraint(
            "((status = 'finished' OR status = 'cancelled') AND finished_at IS NOT NULL)"
            " OR ((status = 'lobby' OR status = 'in_battle') AND finished_at IS NULL)",
            name="ck_caravans_finished_at_matches_status",
        ),
        Index(
            "ix_caravans_sender_clan_id_status",
            "sender_clan_id",
            "status",
        ),
        Index(
            "ix_caravans_receiver_clan_id_status",
            "receiver_clan_id",
            "status",
        ),
        Index(
            "ix_caravans_status_lobby_ends_at",
            "status",
            "lobby_ends_at",
        ),
        Index(
            "ix_caravans_status_battle_ends_at",
            "status",
            "battle_ends_at",
        ),
        Index(
            "uq_caravans_one_active_per_sender",
            "sender_clan_id",
            unique=True,
            sqlite_where=text("status IN ('lobby', 'in_battle')"),
            postgresql_where=text("status IN ('lobby', 'in_battle')"),
        ),
    )


class CaravanParticipantORM(Base):
    """Таблица `caravan_participants` — участник каравана (ГДД §9.4).

    Композитный PK `(caravan_id, player_id)` — игрок может состоять
    в каждом караване ровно один раз. На доменном уровне сущность
    `CaravanParticipant` тоже не имеет суррогатного `id` —
    `(caravan_id, player_id)` образует естественный ключ.
    """

    __tablename__ = "caravan_participants"

    caravan_id: Mapped[int] = mapped_column(
        _AutoIncBigInt,
        ForeignKey(
            "caravans.id",
            ondelete="CASCADE",
            name="fk_caravan_participants_caravan_id_caravans",
        ),
        primary_key=True,
        nullable=False,
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_caravan_participants_player_id_users",
        ),
        primary_key=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_leader: Mapped[bool] = mapped_column(Boolean, nullable=False)
    contribution_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "role IN ('caravaneer', 'defender', 'raider')",
            name="ck_caravan_participants_role_valid",
        ),
        CheckConstraint(
            "(is_leader = 0 AND role IN ('caravaneer', 'defender', 'raider'))"
            " OR (is_leader = 1 AND role = 'caravaneer')",
            name="ck_caravan_participants_leader_implies_caravaneer",
        ),
        CheckConstraint(
            "(role = 'caravaneer' AND contribution_cm IS NOT NULL AND contribution_cm > 0)"
            " OR (role IN ('defender', 'raider') AND contribution_cm IS NULL)",
            name="ck_caravan_participants_contribution_matches_role",
        ),
        Index(
            "ix_caravan_participants_caravan_id_role",
            "caravan_id",
            "role",
        ),
        Index(
            "ix_caravan_participants_player_id",
            "player_id",
        ),
        Index(
            "uq_caravan_participants_one_leader_per_caravan",
            "caravan_id",
            unique=True,
            sqlite_where=text("is_leader = 1"),
            postgresql_where=text("is_leader = true"),
        ),
    )


__all__ = ["CaravanORM", "CaravanParticipantORM"]
