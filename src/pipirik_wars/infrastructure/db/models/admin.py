"""ORM-модель `admins`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base

# SQLite не умеет AUTOINCREMENT на BigInteger; в Postgres — bigserial.
_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


class AdminORM(Base):
    """Таблица `admins` (ГДД §18.6)."""

    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("admins.id", ondelete="SET NULL"),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
