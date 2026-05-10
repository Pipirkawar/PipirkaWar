"""Реализация `IPrizePoolRepository` поверх таблицы `prize_pool_balance` (Спринт 4.1-B, B.3).

Контракт порта — см. `pipirik_wars.domain.monetization.ports.IPrizePoolRepository`.
Реализация опирается на инвариант миграции `0027_prize_pool_balance`:
ровно одна строка на каждую `Currency`-валюту, initial-seed-баланс `0`.

Подход к атомарности `apply_increment(...)`:

* `UPDATE prize_pool_balance SET balance_native = balance_native + :delta,
  updated_at = :now WHERE currency = :c` — atomic в Postgres за счёт
  per-row implicit lock (READ COMMITTED + UPDATE-FOR). В SQLite WAL
  атомарность гарантируется уровнем connection (один-writer).
* После UPDATE — `SELECT *` всех 3 валют для построения `PrizePool`
  (две statement-а вместо одного `UPDATE ... RETURNING`, чтобы оставаться
  максимально портабельным; SQLite `RETURNING` доступен с 3.35,
  Postgres — давно, но `SELECT` после UPDATE даёт проще mental-model).
* DB-CHECK `balance_native >= 0` — last-line-of-defense; доменный VO
  `PrizePool.apply_increment(...)` уже сторожит invariant ещё до записи.

Подход к `get_current()`:

* `SELECT currency, balance_native FROM prize_pool_balance` — все 3 строки
  читаются за один statement, собираются в `PrizePool` через
  `_assemble_pool(...)`. Если по какой-то причине строки нет (миграция
  не применена / partial-DDL), бросаем `RuntimeError` — это
  invariant-violation, не ожидаемая ветка работы.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update

from pipirik_wars.domain.monetization.entities import PrizePool
from pipirik_wars.domain.monetization.ports import IPrizePoolRepository
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    StarsPoolBalance,
    TonNanoAmount,
    UsdtDecimalAmount,
)
from pipirik_wars.infrastructure.db.models import PrizePoolBalanceORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyPrizePoolRepository(IPrizePoolRepository):
    """SQLAlchemy-реализация `IPrizePoolRepository` поверх `prize_pool_balance`."""

    __slots__ = ("_clock", "_uow")

    def __init__(
        self,
        *,
        uow: SqlAlchemyUnitOfWork,
        clock: type[datetime] = datetime,
    ) -> None:
        """DI-конструктор.

        Args:
            uow: Unit-of-Work, поверх которого репозиторий работает.
                Caller обязан открыть `async with uow:` перед вызовами.
            clock: класс/фабрика, у которого есть `now(tz=UTC)` для
                `updated_at`. Дефолт — `datetime` из stdlib; в тестах
                можно заменить на `FakeClock`-совместимый объект.
        """
        self._uow = uow
        self._clock = clock

    async def get_current(self) -> PrizePool:
        """Прочитать текущий снапшот пула из БД."""
        session = self._uow.session
        stmt = select(
            PrizePoolBalanceORM.currency,
            PrizePoolBalanceORM.balance_native,
        )
        result = await session.execute(stmt)
        rows: list[tuple[str, Decimal]] = [
            (row.currency, row.balance_native) for row in result.all()
        ]
        return _assemble_pool(rows)

    async def apply_increment(
        self,
        *,
        currency: Currency,
        amount_native: int,
    ) -> PrizePool:
        """Атомарно прибавить `amount_native` к балансу `currency` и вернуть свежий снапшот."""
        # Доменный invariant `>= 0` сторожится агрегатом `PrizePool`,
        # но для атомарности UPDATE мы передаём дельту как есть и
        # полагаемся на DB-CHECK `balance_native >= 0` как
        # last-line-of-defense (если кто-то попытается убавить ниже нуля,
        # `IntegrityError` поднимется на уровне DB).
        session = self._uow.session
        now = self._clock.now(UTC)
        update_stmt = (
            update(PrizePoolBalanceORM)
            .where(PrizePoolBalanceORM.currency == currency.value)
            .values(
                balance_native=PrizePoolBalanceORM.balance_native + Decimal(amount_native),
                updated_at=now,
            )
        )
        await session.execute(update_stmt)

        return await self.get_current()


def _assemble_pool(
    rows: Iterable[tuple[str, Decimal]],
) -> PrizePool:
    """Собрать `PrizePool` из `(currency, balance_native)`-tuple-ов.

    Все 3 валюты (`stars` / `ton_nano` / `usdt_decimal`) обязательно
    должны быть в `rows` (initial-seed гарантирован миграцией). Если
    хотя бы одной валюты нет — это invariant-violation; поднимаем
    `RuntimeError`.
    """
    by_currency: dict[Currency, int] = {}
    for currency_value, balance_native in rows:
        currency = Currency(currency_value)
        by_currency[currency] = int(balance_native)

    missing = set(Currency) - set(by_currency)
    if missing:
        raise RuntimeError(
            f"prize_pool_balance row missing for currencies: {missing}. "
            "Initial-seed (миграция 0027) не применён?",
        )

    return PrizePool(
        stars=StarsPoolBalance(by_currency[Currency.STARS]),
        ton_nano=TonNanoAmount(by_currency[Currency.TON_NANO]),
        usdt_decimal=UsdtDecimalAmount(by_currency[Currency.USDT_DECIMAL]),
    )
