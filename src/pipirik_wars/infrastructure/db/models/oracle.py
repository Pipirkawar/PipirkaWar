"""ORM-модель `oracle_invocations` (Спринт 1.4.B)."""

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
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base

# SQLite не умеет AUTOINCREMENT на BigInteger.
_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


class OracleInvocationORM(Base):
    """Таблица `oracle_invocations` — суточный лог вызовов `/oracle`.

    На уровне БД охраняем те же инварианты, что и в use-case:
    - `bonus_cm > 0` (предсказатель всегда выдаёт ≥ 1 см длины);
    - `(player_id, moscow_date)` уникален — один `/oracle` в сутки.

    Эти ограничения дублируют доменный кулдаун-чек на случай, если
    кто-то обходит use-case (ручные SQL/миграции).
    """

    __tablename__ = "oracle_invocations"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_oracle_invocations_player_id_users",
        ),
        nullable=False,
    )
    moscow_date: Mapped[date] = mapped_column(Date, nullable=False)
    bonus_cm: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "bonus_cm > 0",
            name="ck_oracle_invocations_bonus_positive",
        ),
        Index(
            "uq_oracle_invocations_player_id_moscow_date",
            "player_id",
            "moscow_date",
            unique=True,
        ),
        Index(
            "ix_oracle_invocations_moscow_date",
            "moscow_date",
        ),
    )
