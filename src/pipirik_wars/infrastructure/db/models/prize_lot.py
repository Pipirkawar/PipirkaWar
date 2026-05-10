"""ORM-модель `prize_lots` — лоты крипто-приза (Спринт 4.1-C, C.3).

Каждая строка — один лот, нарезанный из `PrizePool` через
application-сервис `GeneratePrizeLots` (шаг C.2) и сохранённый
`SqlAlchemyPrizeLotRepository.add(...)` (этот шаг). Жизненный цикл
строки — машина состояний `ACTIVE → RESERVED → CLAIMED|REFUNDED`
(`PrizeLotStatus`); атомарная смена `status` через
`update_status(...)`-метод репозитория.

Колонки и инварианты — см. миграцию `0030_prize_lots`. Этот
модуль — SQLAlchemy-маппинг таблицы для
`SqlAlchemyPrizeLotRepository` (C.3).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base


class PrizeLotORM(Base):
    """Строка таблицы `prize_lots` — один лот крипто-приза.

    Identity на уровне БД — автоинкрементный `id`. Identity на уровне
    домена эквивалентна тому же `id`-у (после `add(...)`-вставки).
    """

    __tablename__ = "prize_lots"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_native: Mapped[Decimal] = mapped_column(
        Numeric(precision=38, scale=0),
        nullable=False,
    )
    fee_buffer_native: Mapped[Decimal] = mapped_column(
        Numeric(precision=38, scale=0),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "currency IN ('stars', 'ton_nano', 'usdt_decimal')",
            name="ck_prize_lots_currency_whitelist",
        ),
        CheckConstraint(
            "amount_native >= 1",
            name="ck_prize_lots_amount_native_positive",
        ),
        CheckConstraint(
            "fee_buffer_native >= 0",
            name="ck_prize_lots_fee_buffer_non_negative",
        ),
        CheckConstraint(
            "amount_native > fee_buffer_native",
            name="ck_prize_lots_amount_greater_than_fee_buffer",
        ),
        CheckConstraint(
            "status IN ('active', 'reserved', 'claimed', 'refunded')",
            name="ck_prize_lots_status_whitelist",
        ),
        CheckConstraint(
            "(status = 'claimed' AND claimed_at IS NOT NULL) "
            "OR (status <> 'claimed' AND claimed_at IS NULL)",
            name="ck_prize_lots_claimed_at_iff_claimed",
        ),
        Index(
            "ix_prize_lots_status_currency",
            "status",
            "currency",
        ),
    )
