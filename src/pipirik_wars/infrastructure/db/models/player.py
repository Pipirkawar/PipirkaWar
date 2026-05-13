"""ORM-модель `users` (Спринт 1.1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base

# SQLite не умеет AUTOINCREMENT на BigInteger; в Postgres — bigserial.
_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


class UserORM(Base):
    """Таблица `users` (ГДД §1.1, §2).

    Стабильный идентификатор снаружи — `tg_id`; внутренний — `id`.
    `username` хранится как plain text без `@` (см. `domain.player.Username`)
    и периодически обновляется (Telegram это позволяет).

    `length_cm` / `thickness_level` имеют CHECK-constraint-ы, дублирующие
    инварианты VO `Length` / `Thickness` — на случай прямого UPDATE-а
    в обход доменного слоя (миграции/руко-патчи).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    length_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    thickness_level: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="active",
    )
    locale_override: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # ── Спринт 1.6.A (anti-cheat hardcap) ──
    # NULL = бан не активен; конкретное `datetime` = до этой точки игрок
    # в soft-ban (нельзя получать длину/толщину). Гейт `AnticheatGuard`
    # сравнивает с `now()` (см. Спринт 1.6.D/1.6.E).
    anticheat_ban_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("length_cm >= 0", name="length_non_negative"),
        CheckConstraint("thickness_level >= 1", name="thickness_positive"),
        CheckConstraint(
            # Расширено в Спринте 4.1-K (миграция 0039) до 8 локалей.
            "locale_override IS NULL OR locale_override IN "
            "('ru', 'en', 'pt', 'es', 'tr', 'id', 'fa', 'uk')",
            name="users_locale_override_supported",
        ),
    )
