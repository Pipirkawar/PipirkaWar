"""ORM-модели PvE-походов гор и данжона (Спринт 3.1-B, ГДД §8).

Зеркальные структуры — отличаются только именами таблицы и
constraint-ов. Хранят:
- `branch_name` (`str`) — имя ветки исхода в `balance.{mountains,dungeon}.outcomes`;
- `branch_sign` (`str` ∈ `{'gain', 'loss'}`) — знак ветки. Дублирует
  знак `length_delta_cm` для CHECK-инварианта «знак ветки согласован
  со знаком дельты»; на доменном уровне (`MountainRun`/`DungeonRun`)
  избыточен, repo при deserialize-е игнорирует, при INSERT — выводит
  из `length_delta_cm`;
- `length_delta_cm` (`int`, **знаковая**) — `gain → ≥ 0`, `loss → ≤ 0`;
- `drops` (`JSON`) — массив `[{"item_id": "..."}]` длиной 0..max_drops.

CHECK-инварианты, индексы и partial-unique — см. миграцию
`20260507_0018_pve_runs.py`. Здесь они продублированы для
`Base.metadata.create_all()`-сценариев в integration-тестах.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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

# SQLite не умеет AUTOINCREMENT на BigInteger; в Postgres — нативный bigserial.
_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


def _pve_run_table_args(table_name: str) -> tuple[Any, ...]:
    """Build the standard CHECK + index set for `mountain_runs`/`dungeon_runs`.

    Имена ограничений / индексов обязаны совпадать с миграцией
    `0018_pve_runs.py`, иначе alembic будет падать на drop-е
    constraint-а в downgrade-е, а Postgres — на конфликте имён.
    """
    return (
        CheckConstraint(
            "status IN ('in_progress', 'finished')",
            name=f"ck_{table_name}_status_valid",
        ),
        CheckConstraint(
            "branch_sign IN ('gain', 'loss')",
            name=f"ck_{table_name}_branch_sign_valid",
        ),
        CheckConstraint(
            "(branch_sign = 'gain' AND length_delta_cm >= 0)"
            " OR (branch_sign = 'loss' AND length_delta_cm <= 0)",
            name=f"ck_{table_name}_sign_matches_delta",
        ),
        CheckConstraint(
            "(status = 'in_progress' AND finished_at IS NULL)"
            " OR (status = 'finished' AND finished_at IS NOT NULL)",
            name=f"ck_{table_name}_finished_at_matches_status",
        ),
        CheckConstraint(
            "ends_at > started_at",
            name=f"ck_{table_name}_ends_after_start",
        ),
        Index(f"ix_{table_name}_player_id_status", "player_id", "status"),
        Index(f"ix_{table_name}_status_ends_at", "status", "ends_at"),
        Index(
            f"uq_{table_name}_one_active_per_player",
            "player_id",
            unique=True,
            sqlite_where=text("status = 'in_progress'"),
            postgresql_where=text("status = 'in_progress'"),
        ),
    )


class MountainRunORM(Base):
    """Таблица `mountain_runs` — поход в горы (ГДД §8)."""

    __tablename__ = "mountain_runs"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_mountain_runs_player_id_users",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    branch_name: Mapped[str] = mapped_column(String(32), nullable=False)
    branch_sign: Mapped[str] = mapped_column(String(8), nullable=False)
    length_delta_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    drops: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = _pve_run_table_args("mountain_runs")


class DungeonRunORM(Base):
    """Таблица `dungeon_runs` — поход в данжон (ГДД §8). Структура зеркалит горную."""

    __tablename__ = "dungeon_runs"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_dungeon_runs_player_id_users",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    branch_name: Mapped[str] = mapped_column(String(32), nullable=False)
    branch_sign: Mapped[str] = mapped_column(String(8), nullable=False)
    length_delta_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    drops: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = _pve_run_table_args("dungeon_runs")


__all__ = ["DungeonRunORM", "MountainRunORM"]
