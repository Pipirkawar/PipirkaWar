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
    reserved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # E.11a (Спринт 4.1-E): winner_id заполняется в одной транзакции с
    # `status='claimed'`. Используется покрывающим индексом
    # `(winner_id, currency, status, claimed_at)` для rolling-30d
    # `EvaluatePayoutLimit`-проверки (E.6/E.10).
    winner_id: Mapped[int | None] = mapped_column(
        BigInteger(),
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
        # D.9.b invariant: ACTIVE-лот не может иметь reserved_at; RESERVED-лот
        # обязан иметь reserved_at. Для CLAIMED / REFUNDED — любое значение.
        CheckConstraint(
            "(status = 'active' AND reserved_at IS NULL) "
            "OR (status = 'reserved' AND reserved_at IS NOT NULL) "
            "OR (status IN ('claimed', 'refunded'))",
            name="ck_prize_lots_reserved_at_consistent",
        ),
        Index(
            "ix_prize_lots_status_currency",
            "status",
            "currency",
        ),
        # D.9.b composite-индекс для `list_expired_reserved(...)`-запроса:
        # `WHERE status = 'reserved' AND reserved_at <= :cutoff ORDER BY
        # reserved_at ASC LIMIT N`. Покрывающий — Postgres использует
        # index-only scan, SQLite — обычный index scan.
        Index(
            "ix_prize_lots_status_reserved_at",
            "status",
            "reserved_at",
        ),
        # E.11a (Спринт 4.1-E): покрывающий индекс для rolling-30d
        # payout-limit-чека (`sum_claimed_in_window` /
        # `oldest_claimed_at_in_window`).
        Index(
            "ix_prize_lots_winner_currency_status_claimed_at",
            "winner_id",
            "currency",
            "status",
            "claimed_at",
        ),
        # E.11a invariants: winner_id заполняется только для
        # status='claimed'; legacy CLAIMED-лоты (до E.11a) с
        # winner_id=NULL допускаются.
        CheckConstraint(
            "(status = 'claimed') OR (winner_id IS NULL)",
            name="ck_prize_lots_winner_id_iff_claimed_or_null",
        ),
        CheckConstraint(
            "winner_id IS NULL OR winner_id > 0",
            name="ck_prize_lots_winner_id_positive",
        ),
    )
