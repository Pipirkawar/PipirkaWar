"""Integration-тесты ``SqlAlchemyWalletRepository`` (Спринт 4.1-D, D.4).

Покрытие:

* ``add_or_replace`` создаёт строку (первичный INSERT).
* ``add_or_replace`` идемпотентен: повторный вызов с тем же
  ``(player_id, currency)`` обновляет ``address`` и ``linked_at``.
* ``get_by_player_and_currency`` возвращает ``None`` для отсутствующей пары.
* Currency-isolation: TON и USDT кошельки одного player живут параллельно.
* DB-CHECK ``currency IN ('ton_nano','usdt_decimal')`` — прямой INSERT
  ``currency='stars'`` падает ``IntegrityError``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.monetization.entities import Wallet
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.infrastructure.db.models import WalletORM
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyWalletRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

NOW = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 5, 11, 13, 0, tzinfo=UTC)
_TON_ADDR_1 = "0:" + "a1" * 32
_TON_ADDR_2 = "0:" + "b2" * 32
_USDT_ADDR = "0:" + "c3" * 32


def _make_repo(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyWalletRepository:
    return SqlAlchemyWalletRepository(uow=uow)


class TestAddOrReplace:
    @pytest.mark.asyncio
    async def test_first_insert(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = _make_repo(uow)
        wallet = Wallet(
            player_id=42,
            address=_TON_ADDR_1,
            currency=Currency.TON_NANO,
            linked_at=NOW,
        )
        async with uow:
            saved = await repo.add_or_replace(wallet=wallet)
            await uow.commit()
        assert saved == wallet

        async with uow:
            fetched = await repo.get_by_player_and_currency(
                player_id=42, currency=Currency.TON_NANO
            )
        assert fetched == wallet

    @pytest.mark.asyncio
    async def test_replace_existing(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = _make_repo(uow)
        old = Wallet(
            player_id=42,
            address=_TON_ADDR_1,
            currency=Currency.TON_NANO,
            linked_at=NOW,
        )
        new = Wallet(
            player_id=42,
            address=_TON_ADDR_2,
            currency=Currency.TON_NANO,
            linked_at=LATER,
        )
        async with uow:
            await repo.add_or_replace(wallet=old)
            await uow.commit()
        async with uow:
            await repo.add_or_replace(wallet=new)
            await uow.commit()

        async with uow:
            fetched = await repo.get_by_player_and_currency(
                player_id=42, currency=Currency.TON_NANO
            )
        assert fetched == new

    @pytest.mark.asyncio
    async def test_currency_isolation(self, uow: SqlAlchemyUnitOfWork) -> None:
        """TON и USDT кошельки одного player не пересекаются."""
        repo = _make_repo(uow)
        ton = Wallet(
            player_id=42,
            address=_TON_ADDR_1,
            currency=Currency.TON_NANO,
            linked_at=NOW,
        )
        usdt = Wallet(
            player_id=42,
            address=_USDT_ADDR,
            currency=Currency.USDT_DECIMAL,
            linked_at=NOW,
        )
        async with uow:
            await repo.add_or_replace(wallet=ton)
            await repo.add_or_replace(wallet=usdt)
            await uow.commit()

        async with uow:
            ton_fetched = await repo.get_by_player_and_currency(
                player_id=42, currency=Currency.TON_NANO
            )
            usdt_fetched = await repo.get_by_player_and_currency(
                player_id=42, currency=Currency.USDT_DECIMAL
            )
        assert ton_fetched == ton
        assert usdt_fetched == usdt


class TestGetByPlayerAndCurrency:
    @pytest.mark.asyncio
    async def test_returns_none_for_missing_player(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = _make_repo(uow)
        async with uow:
            fetched = await repo.get_by_player_and_currency(
                player_id=999, currency=Currency.TON_NANO
            )
        assert fetched is None


class TestDbConstraints:
    @pytest.mark.asyncio
    async def test_currency_stars_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        """DB-CHECK ``ck_wallets_currency_whitelist`` исключает ``stars``."""
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(WalletORM).values(
                        player_id=42,
                        currency="stars",
                        address=_TON_ADDR_1,
                        linked_at=NOW,
                    )
                )

    @pytest.mark.asyncio
    async def test_address_empty_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        """DB-CHECK ``ck_wallets_address_non_empty`` исключает пустую строку."""
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(WalletORM).values(
                        player_id=42,
                        currency="ton_nano",
                        address="",
                        linked_at=NOW,
                    )
                )
