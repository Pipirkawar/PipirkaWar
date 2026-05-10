"""ORM-модель `prize_pool_balance` — баланс призового пула per-currency (Спринт 4.1-B, B.3).

Таблица из 3 строк (`stars` / `ton_nano` / `usdt_decimal`), каждая
хранит текущий баланс пула в native-юнитах своей валюты. Строки
создаются initial-seed-ом в миграции `0027_prize_pool_balance` с
`balance_native = 0`; в дальнейшем atomic UPDATE через
`SqlAlchemyPrizePoolRepository.apply_increment(...)` (B.3) изменяет
`balance_native` и обновляет `updated_at`.

Колонки и инварианты — см. миграцию `0027_prize_pool_balance`. Этот
модуль — SQLAlchemy-маппинг таблицы для `SqlAlchemyPrizePoolRepository`
(B.3).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base


class PrizePoolBalanceORM(Base):
    """Строка таблицы `prize_pool_balance` — одна валюта призового пула.

    Identity на уровне БД — автоинкрементный `id`; identity на
    доменном уровне — `currency` (UNIQUE-constraint).
    """

    __tablename__ = "prize_pool_balance"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    balance_native: Mapped[Decimal] = mapped_column(
        Numeric(precision=38, scale=0),
        nullable=False,
        server_default=text("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("currency", name="uq_prize_pool_balance_currency"),
        CheckConstraint(
            "currency IN ('stars', 'ton_nano', 'usdt_decimal')",
            name="ck_prize_pool_balance_currency_whitelist",
        ),
        CheckConstraint(
            "balance_native >= 0",
            name="ck_prize_pool_balance_balance_native_non_negative",
        ),
    )
