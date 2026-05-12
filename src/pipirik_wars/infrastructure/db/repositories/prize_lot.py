"""Реализация `IPrizeLotRepository` поверх таблицы `prize_lots` (Спринт 4.1-C, C.3).

Контракт порта — см. `pipirik_wars.domain.monetization.ports.IPrizeLotRepository`.
Реализация опирается на схему миграции `0030_prize_lots`: одна строка
на лот, CHECK-инварианты как last-line-of-defense, compound-индекс
`(status, currency)` под `list_active(...)`.

Подходы:

* `add(lot)` — `INSERT INTO prize_lots (...) VALUES (...) RETURNING id`
  для портабельного получения автогенерированного `id`. SQLAlchemy 2.x
  `Insert(...).returning(...)` поддержан и Postgres-ом, и SQLite ≥ 3.35
  (aiosqlite в тестах). После INSERT возвращаем доменный `PrizeLot` с
  проставленным `id` через `dataclasses.replace`.
* `get_by_id(lot_id)` — точечный `SELECT ... WHERE id = :id`.
  Возвращает `None`, если строки нет (без `PrizeLotNotFoundError` —
  политика порта).
* `list_active(currency)` — `SELECT * WHERE status='active' AND
  currency=:c ORDER BY id ASC`. Compound-индекс
  `ix_prize_lots_status_currency` покрывает этот запрос.
* `update_status(lot_id, new_status, claimed_at?)` — атомарный
  `UPDATE ... WHERE id=:id AND status IN (валидные source-статусы для
  `new_status`)`. `rowcount=1` → перешли успешно; `rowcount=0` →
  делаем отдельный `SELECT` и различаем: строки нет
  (`PrizeLotNotFoundError`) или статус уже другой
  (`PrizeLotStatusTransitionError`). Это даёт race-condition защиту
  «два игрока резервируют один и тот же лот» — proxy `UPDATE ... WHERE
  status='active'` сработает только для первого.

DB-CHECK-ограничения (миграция `0030`) — last-line-of-defense; доменные
invariants `PrizeLot.__post_init__` сторожат то же самое ещё до записи.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import CursorResult, func, select, update

from pipirik_wars.domain.monetization.entities import PrizeLot, PrizeLotStatus
from pipirik_wars.domain.monetization.errors import (
    PrizeLotNotFoundError,
    PrizeLotStatusTransitionError,
)
from pipirik_wars.domain.monetization.ports import IPrizeLotRepository
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    FeeBufferAmount,
)
from pipirik_wars.infrastructure.db.models import PrizeLotORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

# Разрешённые source-статусы для каждого target-статуса.
# Совпадает с `_PRIZE_LOT_TRANSITIONS` в `domain/monetization/entities.py`,
# но обращённое отображение (target → set of valid sources) — это удобнее
# для построения `UPDATE ... WHERE status IN (...)`-запроса.
_VALID_SOURCES_FOR_TARGET: dict[PrizeLotStatus, frozenset[PrizeLotStatus]] = {
    PrizeLotStatus.RESERVED: frozenset({PrizeLotStatus.ACTIVE}),
    PrizeLotStatus.CLAIMED: frozenset({PrizeLotStatus.RESERVED}),
    PrizeLotStatus.REFUNDED: frozenset(
        {PrizeLotStatus.ACTIVE, PrizeLotStatus.RESERVED},
    ),
}


class SqlAlchemyPrizeLotRepository(IPrizeLotRepository):
    """SQLAlchemy-реализация `IPrizeLotRepository` поверх `prize_lots`."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        """DI-конструктор.

        Args:
            uow: Unit-of-Work, поверх которого репозиторий работает.
                Caller обязан открыть `async with uow:` перед вызовами.
        """
        self._uow = uow

    async def add(self, *, lot: PrizeLot) -> PrizeLot:
        """Записать новый лот в `prize_lots` и вернуть его с проставленным `id`."""
        session = self._uow.session
        orm = PrizeLotORM(
            currency=lot.currency.value,
            amount_native=Decimal(lot.amount_native),
            fee_buffer_native=Decimal(lot.fee_buffer_native.value),
            status=lot.status.value,
            created_at=lot.created_at,
            reserved_at=lot.reserved_at,
            claimed_at=lot.claimed_at,
        )
        session.add(orm)
        await session.flush()
        return PrizeLot(
            id=orm.id,
            currency=lot.currency,
            amount_native=lot.amount_native,
            fee_buffer_native=lot.fee_buffer_native,
            status=lot.status,
            created_at=lot.created_at,
            reserved_at=lot.reserved_at,
            claimed_at=lot.claimed_at,
        )

    async def get_by_id(self, *, lot_id: int) -> PrizeLot | None:
        """Получить лот по `id` или `None`."""
        session = self._uow.session
        stmt = select(PrizeLotORM).where(PrizeLotORM.id == lot_id)
        result = await session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return _orm_to_domain(orm)

    async def list_active(self, *, currency: Currency) -> Sequence[PrizeLot]:
        """Все `status=ACTIVE`-лоты `currency`, упорядоченные `ORDER BY id ASC`."""
        session = self._uow.session
        stmt = (
            select(PrizeLotORM)
            .where(
                PrizeLotORM.status == PrizeLotStatus.ACTIVE.value,
                PrizeLotORM.currency == currency.value,
            )
            .order_by(PrizeLotORM.id.asc())
        )
        result = await session.execute(stmt)
        return tuple(_orm_to_domain(orm) for orm in result.scalars().all())

    async def update_status(
        self,
        *,
        lot_id: int,
        new_status: PrizeLotStatus,
        reserved_at: datetime | None = None,
        claimed_at: datetime | None = None,
    ) -> PrizeLot:
        """Атомарно перевести лот в `new_status`."""
        if new_status is PrizeLotStatus.ACTIVE:
            raise ValueError(
                "PrizeLotRepository.update_status: ACTIVE is not a valid target "
                "(lots are created in ACTIVE via add(...))",
            )
        if new_status is PrizeLotStatus.RESERVED and reserved_at is None:
            raise ValueError(
                "PrizeLotRepository.update_status: reserved_at is required for RESERVED",
            )
        if new_status is not PrizeLotStatus.RESERVED and reserved_at is not None:
            raise ValueError(
                f"PrizeLotRepository.update_status: reserved_at must be None for "
                f"{new_status.value!r}",
            )
        if new_status is PrizeLotStatus.CLAIMED and claimed_at is None:
            raise ValueError(
                "PrizeLotRepository.update_status: claimed_at is required for CLAIMED",
            )
        if new_status is not PrizeLotStatus.CLAIMED and claimed_at is not None:
            raise ValueError(
                f"PrizeLotRepository.update_status: claimed_at must be None for "
                f"{new_status.value!r}",
            )

        session = self._uow.session
        valid_sources = _VALID_SOURCES_FOR_TARGET[new_status]
        valid_source_values = tuple(status.value for status in valid_sources)

        # На RESERVED-переходе пишем выставляем reserved_at; на CLAIMED /
        # REFUNDED — не трогаем это поле (сохраняется существующее
        # значение; для пути RESERVED → CLAIMED/REFUNDED оно было
        # выставлено на RESERVED-переходе; для пути ACTIVE → REFUNDED
        # оно продолжает быть NULL).
        values: dict[str, object] = {"status": new_status.value}
        if new_status is PrizeLotStatus.RESERVED:
            values["reserved_at"] = reserved_at
        if new_status is PrizeLotStatus.CLAIMED:
            values["claimed_at"] = claimed_at

        stmt = (
            update(PrizeLotORM)
            .where(
                PrizeLotORM.id == lot_id,
                PrizeLotORM.status.in_(valid_source_values),
            )
            .values(**values)
        )
        result = await session.execute(stmt)
        if not isinstance(result, CursorResult):  # pragma: no cover  (защита от изменений API)
            raise RuntimeError("UPDATE must return CursorResult")
        if result.rowcount and result.rowcount > 0:
            updated = await self.get_by_id(lot_id=lot_id)
            if updated is None:  # pragma: no cover — race с DELETE невозможен
                raise PrizeLotNotFoundError(lot_id=lot_id)
            return updated

        # `rowcount=0` → лот либо отсутствует, либо в неподходящем статусе.
        current = await self.get_by_id(lot_id=lot_id)
        if current is None:
            raise PrizeLotNotFoundError(lot_id=lot_id)
        raise PrizeLotStatusTransitionError(
            lot_id=lot_id,
            from_status=current.status,
            to_status=new_status,
        )

    async def list_expired_reserved(
        self,
        *,
        currency: Currency,
        expired_before: datetime,
        limit: int = 100,
    ) -> Sequence[PrizeLot]:
        """Все RESERVED-лоты `currency` с `reserved_at <= expired_before`."""
        session = self._uow.session
        stmt = (
            select(PrizeLotORM)
            .where(
                PrizeLotORM.status == PrizeLotStatus.RESERVED.value,
                PrizeLotORM.currency == currency.value,
                PrizeLotORM.reserved_at <= expired_before,
            )
            .order_by(PrizeLotORM.reserved_at.asc(), PrizeLotORM.id.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return tuple(_orm_to_domain(orm) for orm in result.scalars().all())

    async def sum_claimed_in_window(
        self,
        *,
        player_id: int,
        currency: Currency,
        since: datetime,
    ) -> int:
        """Сумма `amount_native` по CLAIMED-лотам игрока в окне `claimed_at >= since`.

        Не реализовано до шага **E.11** (`prize_lots.winner_id`-миграция).
        До того момента порт всё ещё валидно объявлен в `IPrizeLotRepository`,
        реализация в этом классе возвращает `NotImplementedError`, чтобы
        случайный вызов до E.11 не приводил к silent-zero (`0` без winner-
        фильтра был бы крайне опасен — он отключил бы лимит для всех игроков).

        После E.11 здесь будет::

            SELECT COALESCE(SUM(amount_native), 0) FROM prize_lots
            WHERE winner_id = :player_id AND currency = :currency
              AND status = 'CLAIMED' AND claimed_at >= :since;
        """
        del player_id, currency, since  # used by E.11
        raise NotImplementedError(
            "SqlAlchemyPrizeLotRepository.sum_claimed_in_window: schema "
            "migration `prize_lots.winner_id` ещё не сделана (Спринт 4.1-E "
            "шаг E.11). До E.11 этот метод не подключён к ClaimPrize-flow "
            "(IPayoutLimitChecker hook делается в E.10 ПОСЛЕ E.11)."
        )

    async def oldest_claimed_at_in_window(
        self,
        *,
        player_id: int,
        currency: Currency,
        since: datetime,
    ) -> datetime | None:
        """Самый ранний `claimed_at` для player+currency в окне (>= since).

        Не реализовано до шага **E.11** (см. `sum_claimed_in_window`).
        """
        del player_id, currency, since  # used by E.11
        raise NotImplementedError(
            "SqlAlchemyPrizeLotRepository.oldest_claimed_at_in_window: schema "
            "migration `prize_lots.winner_id` ещё не сделана (Спринт 4.1-E "
            "шаг E.11)."
        )

    async def count_by_status(
        self,
        *,
        currency: Currency,
        status: PrizeLotStatus,
    ) -> int:
        """Количество лотов в указанном `status` для `currency`."""
        session = self._uow.session
        stmt = select(func.count()).where(
            PrizeLotORM.currency == currency.value,
            PrizeLotORM.status == status.value,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one())


def _orm_to_domain(orm: PrizeLotORM) -> PrizeLot:
    """Собрать `PrizeLot`-VO из ORM-строки.

    SQLAlchemy + aiosqlite возвращает naïve-datetime для
    `DateTime(timezone=True)`-колонок (драйверный квирк SQLite — он не
    хранит TZ-инфу). Postgres вернёт TZ-aware. Доменный VO `PrizeLot`
    отказывает naïve-datetime, поэтому здесь мы нормализуем naïve
    значения как UTC. Это безопасно: на запись use-case всегда
    передаёт UTC-моменты (см. `IClock.now()` контракт).
    """
    return PrizeLot(
        id=orm.id,
        currency=Currency(orm.currency),
        amount_native=int(orm.amount_native),
        fee_buffer_native=FeeBufferAmount(int(orm.fee_buffer_native)),
        status=PrizeLotStatus(orm.status),
        created_at=_ensure_utc(orm.created_at),
        reserved_at=_ensure_utc(orm.reserved_at) if orm.reserved_at is not None else None,
        claimed_at=_ensure_utc(orm.claimed_at) if orm.claimed_at is not None else None,
    )


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
