"""ORM-модель `daily_heads` (Спринт 2.3.B).

Зеркало миграции `0012_daily_heads`. Хранит назначения «Главы клана дня»
(ГДД §6.1) — по одному на пару `(clan_id, moscow_date)`.

CHECK + UNIQUE + Index-инварианты дублируют миграцию (см.
`20260506_0012_daily_heads.py`):

* `bonus_cm > 0` — премия всегда положительная;
* `source IN ('button', 'cron')` — единственные допустимые триггеры;
* `(clan_id, moscow_date)` уникальна — last-line-of-defense от race
  «кнопка + cron одновременно»;
* `(clan_id, assigned_at DESC, id DESC)` — для `list_recent_for_clan`
  (anti-repeat-фильтр).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
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


class DailyHeadAssignmentORM(Base):
    """Таблица `daily_heads` — журнал назначений главы клана дня."""

    __tablename__ = "daily_heads"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    clan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "clans.id",
            ondelete="CASCADE",
            name="fk_daily_heads_clan_id_clans",
        ),
        nullable=False,
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_daily_heads_player_id_users",
        ),
        nullable=False,
    )
    moscow_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    bonus_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "bonus_cm > 0",
            name="ck_daily_heads_bonus_positive",
        ),
        CheckConstraint(
            "source IN ('button', 'cron')",
            name="ck_daily_heads_source_valid",
        ),
        Index(
            "uq_daily_heads_clan_id_moscow_date",
            "clan_id",
            "moscow_date",
            unique=True,
        ),
        Index(
            "ix_daily_heads_clan_id_assigned_at_id",
            "clan_id",
            text("assigned_at DESC"),
            text("id DESC"),
        ),
    )
