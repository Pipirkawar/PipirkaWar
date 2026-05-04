"""ORM-модель `signup_queue` (Спринт 1.2.4)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base

# SQLite не умеет AUTOINCREMENT на BigInteger.
_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


class SignupQueueORM(Base):
    """Таблица `signup_queue` — FIFO-очередь регистраций.

    `tg_id` — UNIQUE: один и тот же игрок не может стоять в очереди дважды.
    `enqueued_at` — определяет порядок (FIFO). Индекс на `enqueued_at`
    нужен и для `pop_front(N)`, и для `ROW_NUMBER`-расчёта позиции.

    Запись существует только пока игрок ждёт — после `pop_front` строка
    физически удаляется (история — в `audit_log`).
    """

    __tablename__ = "signup_queue"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(32), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
