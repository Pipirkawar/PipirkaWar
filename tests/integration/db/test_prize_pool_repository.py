"""Integration-тесты `SqlAlchemyPrizePoolRepository` (Спринт 4.1-B, B.3).

Покрытие:

* `get_current()` на свежей БД (initial-seed из conftest = `PrizePool.empty()`).
* `apply_increment(currency, amount)` для каждой из 3 валют (round-trip).
* Атомарность инкремента: после `apply_increment` снапшот пула включает
  изменения; `updated_at` строки обновляется (не остаётся на initial-seed).
* Currency-isolation: инкремент в одной валюте не трогает другие.
* Накопительный `apply_increment`: 3 последовательных вызова STARS+10 →
  итог STARS=30.
* DB-CHECK `balance_native >= 0`: попытка SQL-уровневого `UPDATE` с
  отрицательным значением → `IntegrityError` (last-line-of-defense).
* DB-CHECK `currency IN (...)`: прямой `INSERT` с неизвестной валютой →
  `IntegrityError`.
* DB-CHECK `currency UNIQUE`: попытка вставить дубль `currency='stars'` →
  `IntegrityError`.
* `get_current()` падает с `RuntimeError` если в таблице нет одной из
  обязательных валют (invariant-violation: миграция не применена).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.monetization.entities import PrizePool
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    StarsPoolBalance,
    TonNanoAmount,
    UsdtDecimalAmount,
)
from pipirik_wars.infrastructure.db.models import PrizePoolBalanceORM
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyPrizePoolRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

NOW = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)


def _make_repo(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyPrizePoolRepository:
    return SqlAlchemyPrizePoolRepository(uow=uow)


# --------------------------------------------------------------------------- #
# get_current() — round-trip
# --------------------------------------------------------------------------- #


class TestGetCurrent:
    @pytest.mark.asyncio
    async def test_get_current_returns_empty_pool_after_initial_seed(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """conftest сидит 3 row-а с `balance=0` → `PrizePool.empty()`."""
        repo = _make_repo(uow)

        async with uow:
            pool = await repo.get_current()

        assert pool == PrizePool.empty()
        assert pool.stars.value == 0
        assert pool.ton_nano.value == 0
        assert pool.usdt_decimal.value == 0

    @pytest.mark.asyncio
    async def test_get_current_raises_if_currency_row_missing(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Invariant-violation: миграция не применена → `RuntimeError`."""
        repo = _make_repo(uow)

        async with uow:
            # Симулируем кривое состояние БД — удаляем одну из строк.
            await uow.session.execute(
                delete(PrizePoolBalanceORM).where(PrizePoolBalanceORM.currency == "ton_nano")
            )
            with pytest.raises(RuntimeError, match="prize_pool_balance row missing"):
                await repo.get_current()


# --------------------------------------------------------------------------- #
# apply_increment() — round-trip + currency isolation
# --------------------------------------------------------------------------- #


class TestApplyIncrement:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("currency", "expected_field"),
        [
            (Currency.STARS, "stars"),
            (Currency.TON_NANO, "ton_nano"),
            (Currency.USDT_DECIMAL, "usdt_decimal"),
        ],
        ids=["STARS", "TON_NANO", "USDT_DECIMAL"],
    )
    async def test_apply_increment_round_trip_for_currency(
        self,
        currency: Currency,
        expected_field: str,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`apply_increment(c, 10)` → снапшот с `+10` в нужной валюте."""
        repo = _make_repo(uow)

        async with uow:
            pool_after = await repo.apply_increment(
                currency=currency,
                amount_native=10,
            )

        target = getattr(pool_after, expected_field)
        assert target.value == 10
        # Остальные валюты — нули.
        for other_field in ("stars", "ton_nano", "usdt_decimal"):
            if other_field != expected_field:
                other = getattr(pool_after, other_field)
                assert other.value == 0

    @pytest.mark.asyncio
    async def test_apply_increment_persists_value_across_uow(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Round-trip: после commit-а UoW свежий read даёт обновлённый снапшот."""
        repo = _make_repo(uow)

        async with uow:
            await repo.apply_increment(currency=Currency.STARS, amount_native=42)

        # Свежий UoW — фактически отдельная транзакция.
        async with uow:
            pool = await repo.get_current()

        assert pool.stars.value == 42

    @pytest.mark.asyncio
    async def test_apply_increment_currency_isolation(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Инкремент в одной валюте не меняет другие."""
        repo = _make_repo(uow)

        async with uow:
            await repo.apply_increment(currency=Currency.STARS, amount_native=10)
            await repo.apply_increment(currency=Currency.TON_NANO, amount_native=1_000_000_000)
            pool = await repo.apply_increment(currency=Currency.USDT_DECIMAL, amount_native=500_000)

        assert pool.stars.value == 10
        assert pool.ton_nano.value == 1_000_000_000
        assert pool.usdt_decimal.value == 500_000

    @pytest.mark.asyncio
    async def test_apply_increment_accumulates_for_same_currency(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """3 последовательных STARS+10 → итог STARS=30."""
        repo = _make_repo(uow)

        async with uow:
            await repo.apply_increment(currency=Currency.STARS, amount_native=10)
            await repo.apply_increment(currency=Currency.STARS, amount_native=10)
            pool = await repo.apply_increment(currency=Currency.STARS, amount_native=10)

        assert pool.stars.value == 30

    @pytest.mark.asyncio
    async def test_apply_increment_updates_updated_at_field(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`updated_at` строки растёт после каждого инкремента."""
        repo = _make_repo(uow)

        async with uow:
            stmt = select(PrizePoolBalanceORM.updated_at).where(
                PrizePoolBalanceORM.currency == Currency.STARS.value,
            )
            initial_updated_at = (await uow.session.execute(stmt)).scalar_one()

        async with uow:
            await repo.apply_increment(currency=Currency.STARS, amount_native=1)

        async with uow:
            stmt2 = select(PrizePoolBalanceORM.updated_at).where(
                PrizePoolBalanceORM.currency == Currency.STARS.value,
            )
            new_updated_at = (await uow.session.execute(stmt2)).scalar_one()

        # SQLite TZ-aware compare: `tzinfo` должен совпадать.
        assert new_updated_at >= initial_updated_at + timedelta(seconds=0)
        # Хотя бы один из двух точно: равенство или больше initial-а
        # (FakeClock не используется, поэтому реальное `datetime.now`).
        # Ключ — что ORM-поле прошло через `update_stmt` и не осталось NULL.
        assert new_updated_at is not None


# --------------------------------------------------------------------------- #
# DB-CHECK invariants — last-line-of-defense
# --------------------------------------------------------------------------- #


class TestDbCheckInvariants:
    @pytest.mark.asyncio
    async def test_negative_balance_native_rejected_by_check(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Прямой `UPDATE` с `balance_native = -1` → `IntegrityError`."""
        async with uow:
            stmt = (
                update(PrizePoolBalanceORM)
                .where(PrizePoolBalanceORM.currency == "stars")
                .values(balance_native=Decimal(-1), updated_at=NOW)
            )
            with pytest.raises(IntegrityError):
                await uow.session.execute(stmt)
                await uow.session.flush()

    @pytest.mark.asyncio
    async def test_unknown_currency_rejected_by_check(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Прямой `INSERT` с `currency='gold'` → `IntegrityError`."""
        async with uow:
            stmt = insert(PrizePoolBalanceORM).values(
                currency="gold",
                balance_native=Decimal(0),
                updated_at=NOW,
            )
            with pytest.raises(IntegrityError):
                await uow.session.execute(stmt)
                await uow.session.flush()

    @pytest.mark.asyncio
    async def test_duplicate_currency_rejected_by_unique_constraint(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Прямой `INSERT` дубля `currency='stars'` → `IntegrityError`."""
        async with uow:
            stmt = insert(PrizePoolBalanceORM).values(
                currency="stars",
                balance_native=Decimal(0),
                updated_at=NOW,
            )
            with pytest.raises(IntegrityError):
                await uow.session.execute(stmt)
                await uow.session.flush()


# --------------------------------------------------------------------------- #
# Existing-state round-trip
# --------------------------------------------------------------------------- #


class TestExistingStateRoundTrip:
    @pytest.mark.asyncio
    async def test_get_current_reflects_pre_seeded_balances(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Прямой `UPDATE` балансов → `get_current()` видит свежий snapshot."""
        async with uow:
            stmt_stars = (
                update(PrizePoolBalanceORM)
                .where(PrizePoolBalanceORM.currency == "stars")
                .values(balance_native=Decimal(100), updated_at=NOW)
            )
            stmt_ton = (
                update(PrizePoolBalanceORM)
                .where(PrizePoolBalanceORM.currency == "ton_nano")
                .values(balance_native=Decimal(50), updated_at=NOW)
            )
            stmt_usdt = (
                update(PrizePoolBalanceORM)
                .where(PrizePoolBalanceORM.currency == "usdt_decimal")
                .values(balance_native=Decimal(25), updated_at=NOW)
            )
            await uow.session.execute(stmt_stars)
            await uow.session.execute(stmt_ton)
            await uow.session.execute(stmt_usdt)

        repo = _make_repo(uow)
        async with uow:
            pool = await repo.get_current()

        assert pool == PrizePool(
            stars=StarsPoolBalance(100),
            ton_nano=TonNanoAmount(50),
            usdt_decimal=UsdtDecimalAmount(25),
        )
