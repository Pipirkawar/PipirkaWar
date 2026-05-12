"""ORM-модель ``payout_freeze`` — singleton freeze-флага крипто-выплат (Спринт 4.1-E, E.11a).

Одна строка таблицы (``id = 1``, enforced CHECK-ом) хранит глобальный
freeze-флаг крипто-выплат: TON и USDT (Stars-выплаты идут отдельным
каналом и не затрагиваются). Колонки полностью симметричны полям
доменного агрегата ``PayoutFreeze``:

* ``id = 1`` — singleton-ключ, CHECK ``id = 1`` гарантирует уникальность.
* ``is_frozen BOOLEAN NOT NULL`` — текущее состояние.
* ``frozen_by_admin_id BIGINT NULL`` — id админа (при ``is_frozen=TRUE``).
* ``frozen_at TIMESTAMPTZ NULL`` — TZ-aware момент последнего изменения.
* ``reason TEXT NULL`` — обязательный комментарий админа.

DB-инварианты — last-line-of-defense; доменные ``PayoutFreeze.
__post_init__`` сторожат то же самое ещё до записи.

Этот ORM-модуль используется ``SqlAlchemyPayoutFreezeRepository`` для
``get_state()`` / ``set_frozen(...)`` / ``set_unfrozen(...)``-операций.
Seed-строка ``(id=1, is_frozen=FALSE)`` создаётся в Alembic-миграции
``0037_payout_freeze_and_prize_lot_winner_id`` через ``INSERT`` в
``upgrade()``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pipirik_wars.infrastructure.db.base import Base


class PayoutFreezeORM(Base):
    """Singleton-строка таблицы ``payout_freeze`` (Спринт 4.1-E, E.11a).

    Identity на уровне БД — ``id`` с CHECK ``id = 1`` (одна строка).
    Identity на уровне домена не нужна — два идентичных снапшота
    ``PayoutFreeze`` неотличимы.
    """

    __tablename__ = "payout_freeze"

    id: Mapped[int] = mapped_column(
        Integer(),
        primary_key=True,
        nullable=False,
    )
    is_frozen: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
    )
    frozen_by_admin_id: Mapped[int | None] = mapped_column(
        BigInteger(),
        nullable=True,
    )
    frozen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(
        Text(),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "id = 1",
            name="ck_payout_freeze_singleton",
        ),
        CheckConstraint(
            "(is_frozen = 0 AND frozen_by_admin_id IS NULL "
            "AND frozen_at IS NULL AND reason IS NULL) "
            "OR (is_frozen = 1 AND frozen_by_admin_id IS NOT NULL "
            "AND frozen_at IS NOT NULL AND reason IS NOT NULL)",
            name="ck_payout_freeze_attrs_consistent",
        ),
        CheckConstraint(
            "frozen_by_admin_id IS NULL OR frozen_by_admin_id > 0",
            name="ck_payout_freeze_admin_id_positive",
        ),
        CheckConstraint(
            "reason IS NULL OR LENGTH(reason) > 0",
            name="ck_payout_freeze_reason_non_empty",
        ),
    )
