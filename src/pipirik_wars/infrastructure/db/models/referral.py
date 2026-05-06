"""ORM-модель `referrals` (Спринт 2.4.B).

Зеркало миграции `0015_referrals`. Хранит реферальные связи
(ГДД §13.1) — по одной записи на приглашённого игрока (`referred_id`
UNIQUE).

CHECK + UNIQUE + Index-инварианты дублируют миграцию (см.
`20260506_0015_referrals.py`):

* `referrer_id <> referred_id` — само-реферал запрещён;
* `last_milestone_thickness >= 0`;
* `referred_id` уникален (один игрок = одна реферальная запись);
* `(referrer_id, created_at DESC, id DESC)` — для «последние N
  рефералов реферера».
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base

# SQLite не умеет AUTOINCREMENT на BigInteger.
_AutoIncBigInt = BigInteger().with_variant(Integer, "sqlite")


class ReferralORM(Base):
    """Таблица `referrals` — журнал реферальных связей."""

    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(_AutoIncBigInt, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_referrals_referrer_id_users",
        ),
        nullable=False,
    )
    referred_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_referrals_referred_id_users",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signup_granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_milestone_thickness: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    __table_args__ = (
        CheckConstraint(
            "referrer_id <> referred_id",
            name="ck_referrals_no_self_referral",
        ),
        CheckConstraint(
            "last_milestone_thickness >= 0",
            name="ck_referrals_milestone_non_negative",
        ),
        Index(
            "uq_referrals_referred_id",
            "referred_id",
            unique=True,
        ),
        Index(
            "ix_referrals_referrer_id_created_at_id",
            "referrer_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )
