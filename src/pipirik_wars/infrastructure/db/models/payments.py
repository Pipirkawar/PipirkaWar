"""ORM-модель `payments` — append-only ledger Telegram Stars / TON / USDT (Спринт 4.1-A).

Append-only таблица: каждый платёж (`/roulette_paid`-invoice → TG Stars
`successful_payment`) кладётся одной строкой; статус меняется только
`PENDING → CONFIRMED | REFUNDED` (последнее — в 4.1-A→4.1-E через
`mark_confirmed` / `mark_refunded`-методы; на 4.1-A use-case
`SpinPaidRoulette` пишет сразу со статусом `CONFIRMED`).

Колонки и инварианты — см. миграцию `0026_payments`. Этот модуль —
SQLAlchemy-маппинг таблицы для `SqlAlchemyPaymentLedger` (Спринт 4.1-A).

JSON-колонка `payload` — портабельная (`JSON`): Postgres
сериализует как JSONB-совместимый JSON, SQLite (тесты) — как
TEXT-обёртку. Если в Postgres понадобится GIN-индекс по `payload` —
расширим в отдельной миграции (4.1-D / 4.1-E).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base


class PaymentORM(Base):
    """Строка таблицы `payments` — одно платёжное событие (Спринт 4.1-A).

    Identity на уровне БД — автоинкрементный `id`; identity на
    доменном уровне — `(player_id, idempotency_key)`-tuple
    (`UNIQUE`-индекс ОRM зеркалит доменную идентичность).
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_payments_player_id_users",
        ),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_native: Mapped[Decimal] = mapped_column(
        Numeric(precision=38, scale=0),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'pending'"),
    )
    provider_payment_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    payload: Mapped[dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
        server_default=text("'{}'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "idempotency_key",
            name="uq_payments_player_id_idempotency_key",
        ),
        CheckConstraint(
            "currency IN ('stars', 'ton_nano', 'usdt_decimal')",
            name="ck_payments_currency_whitelist",
        ),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'refunded')",
            name="ck_payments_status_whitelist",
        ),
        CheckConstraint(
            "amount_native >= 1",
            name="ck_payments_amount_native_positive",
        ),
        CheckConstraint(
            "(status = 'confirmed' AND confirmed_at IS NOT NULL "
            "AND provider_payment_id IS NOT NULL) "
            "OR (status != 'confirmed')",
            name="ck_payments_confirmed_consistency",
        ),
        CheckConstraint(
            "(status != 'pending') OR (confirmed_at IS NULL)",
            name="ck_payments_pending_no_confirmed_at",
        ),
        Index(
            "ix_payments_idempotency_key",
            "idempotency_key",
        ),
    )
