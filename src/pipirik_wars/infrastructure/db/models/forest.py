"""ORM-модели лесной подсистемы (Спринт 1.3.B)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
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

# SQLite не умеет AUTOINCREMENT на BigInteger.
_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


class ForestRunORM(Base):
    """Таблица `forest_runs` — поход игрока в лес.

    На уровне БД охраняем те же инварианты, что и в use-case:
    - `status` ∈ `('in_progress', 'finished')`;
    - `drop_kind` ∈ `('none', 'item', 'name')`;
    - payload (`drop_item_id`/`drop_name`) совместим с `drop_kind`;
    - `IN_PROGRESS` ⇔ `finished_at IS NULL`;
    - `ends_at > started_at`;
    - не более одной `IN_PROGRESS`-записи на игрока (partial unique index).

    Всё это дублирует `domain.forest.ForestRun`-инварианты — на случай
    прямого UPDATE-а в обход доменного слоя (ручные фиксы / миграции).
    """

    __tablename__ = "forest_runs"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_forest_runs_player_id_users"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    branch_name: Mapped[str] = mapped_column(String(32), nullable=False)
    length_delta_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    drop_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    drop_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    drop_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "length_delta_cm >= 0",
            name="ck_forest_runs_length_non_negative",
        ),
        CheckConstraint(
            "status IN ('in_progress', 'finished')",
            name="ck_forest_runs_status_valid",
        ),
        CheckConstraint(
            "drop_kind IN ('none', 'item', 'name')",
            name="ck_forest_runs_drop_kind_valid",
        ),
        CheckConstraint(
            "(drop_kind = 'none' AND drop_item_id IS NULL AND drop_name IS NULL)"
            " OR (drop_kind = 'item' AND drop_item_id IS NOT NULL AND drop_name IS NULL)"
            " OR (drop_kind = 'name' AND drop_item_id IS NULL AND drop_name IS NOT NULL)",
            name="ck_forest_runs_drop_payload_matches_kind",
        ),
        CheckConstraint(
            "(status = 'in_progress' AND finished_at IS NULL)"
            " OR (status = 'finished' AND finished_at IS NOT NULL)",
            name="ck_forest_runs_finished_at_matches_status",
        ),
        CheckConstraint(
            "ends_at > started_at",
            name="ck_forest_runs_ends_after_start",
        ),
        Index("ix_forest_runs_player_id_status", "player_id", "status"),
        Index("ix_forest_runs_status_ends_at", "status", "ends_at"),
        Index(
            "uq_forest_runs_one_active_per_player",
            "player_id",
            unique=True,
            sqlite_where=text("status = 'in_progress'"),
            postgresql_where=text("status = 'in_progress'"),
        ),
    )
