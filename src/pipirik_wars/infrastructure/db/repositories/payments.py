"""Реализация `IPaymentLedger` поверх таблицы `payments` (Спринт 4.1-A, A.5).

Append-only ledger Telegram Stars / TON / USDT платежей. Контракт порта
— см. `pipirik_wars.domain.monetization.ports.IPaymentLedger`. Этот
адаптер пользуется тем же паттерном, что и
`SqlAlchemyRouletteSpinRepository` (Спринт 3.5-B): диалект-специфичный
`INSERT ... ON CONFLICT DO NOTHING` (Postgres / SQLite одинаково),
повторный `SELECT` для возврата сохранённой строки.

Семантика дедупликации — полностью идемпотентная (антифрод 4.1.4):

* первая вставка — создаёт строку и возвращает свежий `Payment`-VO;
* повторный `charge(...)` с тем же `(player_id, idempotency_key)` и
  теми же `(currency, amount_native)` — возвращает сохранённый
  `Payment`-VO без побочных эффектов;
* повторный `charge(...)` с тем же `(player_id, idempotency_key)`, но
  другим `(currency | amount_native)`-tuple — поднимает
  `IdempotencyConflictError` (с атрибутами существующей и попытавшейся
  записей).

Дедупликация — на паре `(player_id, idempotency_key)`, чтобы разные
игроки могли использовать одинаковые ключи (что не противоречит
антифроду — ключи стабильны для конкретного `(player, payment)`-flow).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Insert as PgInsert, insert as pg_insert
from sqlalchemy.dialects.sqlite import Insert as SqliteInsert, insert as sqlite_insert
from sqlalchemy.sql.dml import Insert as DialectInsert

from pipirik_wars.domain.monetization.entities import Payment, PaymentStatus
from pipirik_wars.domain.monetization.errors import IdempotencyConflictError
from pipirik_wars.domain.monetization.ports import IPaymentLedger
from pipirik_wars.domain.monetization.value_objects import Currency, IdempotencyKey
from pipirik_wars.infrastructure.db.models import PaymentORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyPaymentLedger(IPaymentLedger):
    """SQLAlchemy-реализация `IPaymentLedger` поверх таблицы `payments`."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def charge(
        self,
        *,
        player_id: int,
        currency: Currency,
        amount_native: int,
        idempotency_key: IdempotencyKey,
        status: PaymentStatus,
        occurred_at: datetime,
        provider_payment_id: str | None = None,
        payload: Mapping[str, str] | None = None,
    ) -> Payment:
        """Записать платёж (idempotent по `(player_id, idempotency_key)`)."""
        confirmed_at = occurred_at if status is PaymentStatus.CONFIRMED else None
        payload_dict: dict[str, str] = dict(payload) if payload is not None else {}

        session = self._uow.session
        dialect = session.bind.dialect.name if session.bind is not None else ""
        values = {
            "player_id": player_id,
            "currency": currency.value,
            "amount_native": Decimal(amount_native),
            "idempotency_key": idempotency_key.value,
            "status": status.value,
            "provider_payment_id": provider_payment_id,
            "payload": payload_dict,
            "created_at": occurred_at,
            "confirmed_at": confirmed_at,
        }
        stmt: DialectInsert
        if dialect == "postgresql":
            pg_stmt: PgInsert = pg_insert(PaymentORM).values(values)
            stmt = pg_stmt.on_conflict_do_nothing(
                index_elements=[PaymentORM.player_id, PaymentORM.idempotency_key],
            )
        else:
            sl_stmt: SqliteInsert = sqlite_insert(PaymentORM).values(values)
            stmt = sl_stmt.on_conflict_do_nothing(
                index_elements=[PaymentORM.player_id, PaymentORM.idempotency_key],
            )
        await session.execute(stmt)

        # Прочитать сохранённую строку (свежевставленную либо
        # существующую с прошлого вызова) и сравнить `(currency,
        # amount_native)` для антифрод-защиты.
        select_stmt = select(PaymentORM).where(
            PaymentORM.player_id == player_id,
            PaymentORM.idempotency_key == idempotency_key.value,
        )
        result = await session.execute(select_stmt)
        row = result.scalar_one()

        existing_amount_native = int(row.amount_native)
        if row.currency != currency.value or existing_amount_native != amount_native:
            raise IdempotencyConflictError(
                idempotency_key=idempotency_key.value,
                existing_player_id=row.player_id,
                existing_currency=Currency(row.currency),
                existing_amount_native=existing_amount_native,
                attempted_player_id=player_id,
                attempted_currency=currency,
                attempted_amount_native=amount_native,
            )

        return _orm_to_payment(row)

    async def get_by_idempotency_key(
        self,
        *,
        idempotency_key: IdempotencyKey,
    ) -> Payment | None:
        """Найти платёж по `idempotency_key` (любого игрока) или вернуть `None`."""
        session = self._uow.session
        stmt = select(PaymentORM).where(
            PaymentORM.idempotency_key == idempotency_key.value,
        )
        result = await session.execute(stmt)
        row = result.scalars().first()
        if row is None:
            return None
        return _orm_to_payment(row)


def _orm_to_payment(row: PaymentORM) -> Payment:
    """Свернуть ORM-строку в доменный VO `Payment`.

    SQLAlchemy + aiosqlite возвращает naïve-datetime для
    `DateTime(timezone=True)`-колонок (драйверный квирк SQLite — он не
    хранит TZ-инфу). Postgres вернёт TZ-aware. Доменный VO `Payment`
    отказывает naïve-datetime, поэтому здесь мы нормализуем naïve
    значения как UTC. Это безопасно: на запись use-case всегда
    передаёт UTC-моменты (см. `IClock.now()` контракт).
    """
    return Payment(
        player_id=row.player_id,
        currency=Currency(row.currency),
        amount_native=int(row.amount_native),
        idempotency_key=IdempotencyKey(row.idempotency_key),
        status=PaymentStatus(row.status),
        created_at=_ensure_utc(row.created_at),
        provider_payment_id=row.provider_payment_id,
        confirmed_at=_ensure_utc(row.confirmed_at) if row.confirmed_at is not None else None,
        payload=MappingProxyType(dict(row.payload)),
    )


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
