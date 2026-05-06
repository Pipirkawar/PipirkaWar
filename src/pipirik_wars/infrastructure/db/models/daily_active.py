"""ORM-модель `daily_active` (Спринт 2.3.B).

Зеркало миграции `0013_daily_active`. Хранит «активность игроков по
дням МСК» — нужна для `IDailyActivityRepository.list_active_member_ids`
(ГДД §6.1, ПД §5 задача 2.3.7).

PK `(date, user_id)` — один row на пару, идемпотентный upsert.
Запись на каждое сообщение делает middleware (Спринт 2.3.E,
`bot/middlewares/daily_activity.py`); на момент 2.3.B сама ORM-модель
+ read-репозиторий — достаточно для integration-тестов с заранее
prefilled-данными.
"""

from __future__ import annotations

from datetime import date as date_t, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base


class DailyActiveORM(Base):
    """Таблица `daily_active` — активность игроков по дням МСК."""

    __tablename__ = "daily_active"

    date: Mapped[date_t] = mapped_column(Date, primary_key=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_daily_active_user_id_users",
        ),
        primary_key=True,
        nullable=False,
    )
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "ix_daily_active_user_id_date",
            "user_id",
            text("date DESC"),
        ),
    )
