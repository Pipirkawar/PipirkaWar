"""Integration-тесты `SqlAlchemyPrizeLotRepository` (Спринт 4.1-C, C.3).

Покрытие:

* `add(lot)` — round-trip: новый лот сохраняется, БД назначает
  `id`, все поля совпадают с переданным `PrizeLot`.
* `get_by_id(lot_id)` — точечный чтение существующего лота +
  `None` для несуществующего.
* `list_active(currency)` — фильтрация по `status=ACTIVE` + `currency`,
  сортировка `ORDER BY id ASC`, currency-isolation.
* `update_status(...)` — машина состояний `ACTIVE → RESERVED → CLAIMED`,
  `ACTIVE → REFUNDED`, `RESERVED → REFUNDED`; race-condition с
  `ACTIVE → RESERVED` дважды → `PrizeLotStatusTransitionError` на втором
  вызове; несуществующий `lot_id` → `PrizeLotNotFoundError`.
* DB-CHECK `amount_native >= 1`, `fee_buffer_native >= 0`,
  `amount_native > fee_buffer_native`, `currency IN (...)`,
  `status IN (...)`, `claimed_at IFF status='claimed'` —
  попытка прямого SQL-инсерта с нарушающими значениями →
  `IntegrityError` (last-line-of-defense).
* Persistence across UoW: после commit-а UoW следующий read даёт
  обновлённый снапшот.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.monetization.entities import PrizeLot, PrizeLotStatus
from pipirik_wars.domain.monetization.errors import (
    PrizeLotNotFoundError,
    PrizeLotStatusTransitionError,
)
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    FeeBufferAmount,
)
from pipirik_wars.infrastructure.db.models import PrizeLotORM
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyPrizeLotRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

NOW = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)


def _make_repo(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyPrizeLotRepository:
    return SqlAlchemyPrizeLotRepository(uow=uow)


def _fresh_lot(
    *,
    currency: Currency = Currency.USDT_DECIMAL,
    amount_native: int = 1_000_000,
    fee_buffer_native: int = 100_000,
    created_at: datetime | None = None,
) -> PrizeLot:
    return PrizeLot.freshly_generated(
        currency=currency,
        amount_native=amount_native,
        fee_buffer_native=FeeBufferAmount(fee_buffer_native),
        created_at=created_at or NOW,
    )


# --------------------------------------------------------------------------- #
# add(lot) — round-trip
# --------------------------------------------------------------------------- #


class TestAdd:
    @pytest.mark.asyncio
    async def test_add_assigns_id_and_persists_all_fields(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`add(...)` назначает `id` и сохраняет все поля без потерь."""
        repo = _make_repo(uow)
        fresh = _fresh_lot()

        async with uow:
            saved = await repo.add(lot=fresh)

        assert saved.id is not None
        assert saved.id > 0
        assert saved.currency is fresh.currency
        assert saved.amount_native == fresh.amount_native
        assert saved.fee_buffer_native == fresh.fee_buffer_native
        assert saved.status is PrizeLotStatus.ACTIVE
        assert saved.created_at == fresh.created_at
        assert saved.claimed_at is None

    @pytest.mark.asyncio
    async def test_add_two_lots_get_distinct_ids(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            first = await repo.add(lot=_fresh_lot())
            second = await repo.add(lot=_fresh_lot(amount_native=2_000_000))
        assert first.id is not None
        assert second.id is not None
        assert first.id != second.id
        assert second.id > first.id

    @pytest.mark.asyncio
    async def test_add_persists_across_uow(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """После commit-а UoW свежий read возвращает тот же лот."""
        repo = _make_repo(uow)
        async with uow:
            saved = await repo.add(lot=_fresh_lot())
        assert saved.id is not None

        async with uow:
            loaded = await repo.get_by_id(lot_id=saved.id)

        assert loaded == saved


# --------------------------------------------------------------------------- #
# get_by_id
# --------------------------------------------------------------------------- #


class TestGetById:
    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_for_missing(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            loaded = await repo.get_by_id(lot_id=999_999)
        assert loaded is None

    @pytest.mark.asyncio
    async def test_get_by_id_roundtrip_each_currency(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            stars = await repo.add(
                lot=_fresh_lot(
                    currency=Currency.STARS,
                    amount_native=500,
                    fee_buffer_native=50,
                ),
            )
            ton = await repo.add(
                lot=_fresh_lot(
                    currency=Currency.TON_NANO,
                    amount_native=1_000_000_000,
                    fee_buffer_native=10_000_000,
                ),
            )
            usdt = await repo.add(
                lot=_fresh_lot(
                    currency=Currency.USDT_DECIMAL,
                    amount_native=5_000_000,
                    fee_buffer_native=200_000,
                ),
            )

        async with uow:
            assert await repo.get_by_id(lot_id=stars.id or 0) == stars
            assert await repo.get_by_id(lot_id=ton.id or 0) == ton
            assert await repo.get_by_id(lot_id=usdt.id or 0) == usdt


# --------------------------------------------------------------------------- #
# list_active(currency)
# --------------------------------------------------------------------------- #


class TestListActive:
    @pytest.mark.asyncio
    async def test_list_active_empty_on_fresh_db(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            result = await repo.list_active(currency=Currency.USDT_DECIMAL)
        assert result == ()

    @pytest.mark.asyncio
    async def test_list_active_filters_by_currency(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            usdt = await repo.add(lot=_fresh_lot(currency=Currency.USDT_DECIMAL))
            await repo.add(
                lot=_fresh_lot(
                    currency=Currency.TON_NANO,
                    amount_native=1_000_000_000,
                    fee_buffer_native=10_000_000,
                ),
            )

        async with uow:
            usdt_active = await repo.list_active(currency=Currency.USDT_DECIMAL)
            stars_active = await repo.list_active(currency=Currency.STARS)

        assert usdt_active == (usdt,)
        assert stars_active == ()

    @pytest.mark.asyncio
    async def test_list_active_filters_by_status(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`RESERVED|CLAIMED|REFUNDED`-лоты исключаются из выдачи."""
        repo = _make_repo(uow)
        async with uow:
            active = await repo.add(lot=_fresh_lot())
            to_reserve = await repo.add(
                lot=_fresh_lot(amount_native=2_000_000),
            )
            to_refund = await repo.add(
                lot=_fresh_lot(amount_native=3_000_000),
            )
            assert to_reserve.id is not None
            assert to_refund.id is not None
            await repo.update_status(
                lot_id=to_reserve.id,
                new_status=PrizeLotStatus.RESERVED,
            )
            await repo.update_status(
                lot_id=to_refund.id,
                new_status=PrizeLotStatus.REFUNDED,
            )

        async with uow:
            result = await repo.list_active(currency=Currency.USDT_DECIMAL)

        assert result == (active,)

    @pytest.mark.asyncio
    async def test_list_active_orders_by_id_asc(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            first = await repo.add(lot=_fresh_lot(amount_native=1_000_000))
            second = await repo.add(lot=_fresh_lot(amount_native=2_000_000))
            third = await repo.add(lot=_fresh_lot(amount_native=3_000_000))

        async with uow:
            result = await repo.list_active(currency=Currency.USDT_DECIMAL)

        assert [lot.id for lot in result] == [first.id, second.id, third.id]


# --------------------------------------------------------------------------- #
# update_status — машина состояний
# --------------------------------------------------------------------------- #


class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_active_to_reserved_then_to_claimed(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            saved = await repo.add(lot=_fresh_lot())
            assert saved.id is not None

            reserved = await repo.update_status(
                lot_id=saved.id,
                new_status=PrizeLotStatus.RESERVED,
            )
            assert reserved.status is PrizeLotStatus.RESERVED
            assert reserved.claimed_at is None

            claimed_at = NOW + timedelta(minutes=5)
            claimed = await repo.update_status(
                lot_id=saved.id,
                new_status=PrizeLotStatus.CLAIMED,
                claimed_at=claimed_at,
            )
            assert claimed.status is PrizeLotStatus.CLAIMED
            assert claimed.claimed_at == claimed_at

    @pytest.mark.asyncio
    async def test_active_to_refunded(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            saved = await repo.add(lot=_fresh_lot())
            assert saved.id is not None
            refunded = await repo.update_status(
                lot_id=saved.id,
                new_status=PrizeLotStatus.REFUNDED,
            )
        assert refunded.status is PrizeLotStatus.REFUNDED
        assert refunded.claimed_at is None

    @pytest.mark.asyncio
    async def test_reserved_to_refunded(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            saved = await repo.add(lot=_fresh_lot())
            assert saved.id is not None
            await repo.update_status(
                lot_id=saved.id,
                new_status=PrizeLotStatus.RESERVED,
            )
            refunded = await repo.update_status(
                lot_id=saved.id,
                new_status=PrizeLotStatus.REFUNDED,
            )
        assert refunded.status is PrizeLotStatus.REFUNDED

    @pytest.mark.asyncio
    async def test_double_reserve_raises_transition_error(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Race-condition: второй `ACTIVE → RESERVED` падает с `PrizeLotStatusTransitionError`."""
        repo = _make_repo(uow)
        async with uow:
            saved = await repo.add(lot=_fresh_lot())
            assert saved.id is not None
            await repo.update_status(
                lot_id=saved.id,
                new_status=PrizeLotStatus.RESERVED,
            )
            with pytest.raises(PrizeLotStatusTransitionError) as exc_info:
                await repo.update_status(
                    lot_id=saved.id,
                    new_status=PrizeLotStatus.RESERVED,
                )
        assert exc_info.value.lot_id == saved.id
        assert exc_info.value.from_status is PrizeLotStatus.RESERVED
        assert exc_info.value.to_status is PrizeLotStatus.RESERVED

    @pytest.mark.asyncio
    async def test_claim_without_reservation_raises_transition_error(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`ACTIVE → CLAIMED` напрямую запрещён."""
        repo = _make_repo(uow)
        async with uow:
            saved = await repo.add(lot=_fresh_lot())
            assert saved.id is not None
            with pytest.raises(PrizeLotStatusTransitionError) as exc_info:
                await repo.update_status(
                    lot_id=saved.id,
                    new_status=PrizeLotStatus.CLAIMED,
                    claimed_at=NOW,
                )
        assert exc_info.value.lot_id == saved.id
        assert exc_info.value.from_status is PrizeLotStatus.ACTIVE
        assert exc_info.value.to_status is PrizeLotStatus.CLAIMED

    @pytest.mark.asyncio
    async def test_claim_terminal_lot_raises_transition_error(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """После `REFUNDED` (terminal) — никакие переходы не разрешены."""
        repo = _make_repo(uow)
        async with uow:
            saved = await repo.add(lot=_fresh_lot())
            assert saved.id is not None
            await repo.update_status(
                lot_id=saved.id,
                new_status=PrizeLotStatus.REFUNDED,
            )
            with pytest.raises(PrizeLotStatusTransitionError) as exc_info:
                await repo.update_status(
                    lot_id=saved.id,
                    new_status=PrizeLotStatus.REFUNDED,
                )
        assert exc_info.value.from_status is PrizeLotStatus.REFUNDED

    @pytest.mark.asyncio
    async def test_update_missing_lot_raises_not_found(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            with pytest.raises(PrizeLotNotFoundError) as exc_info:
                await repo.update_status(
                    lot_id=999_999,
                    new_status=PrizeLotStatus.RESERVED,
                )
        assert exc_info.value.lot_id == 999_999

    @pytest.mark.asyncio
    async def test_update_to_active_raises_value_error(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            saved = await repo.add(lot=_fresh_lot())
            assert saved.id is not None
            with pytest.raises(ValueError, match="ACTIVE is not a valid target"):
                await repo.update_status(
                    lot_id=saved.id,
                    new_status=PrizeLotStatus.ACTIVE,
                )

    @pytest.mark.asyncio
    async def test_claim_requires_claimed_at(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            saved = await repo.add(lot=_fresh_lot())
            assert saved.id is not None
            await repo.update_status(
                lot_id=saved.id,
                new_status=PrizeLotStatus.RESERVED,
            )
            with pytest.raises(ValueError, match="claimed_at is required for CLAIMED"):
                await repo.update_status(
                    lot_id=saved.id,
                    new_status=PrizeLotStatus.CLAIMED,
                )

    @pytest.mark.asyncio
    async def test_non_claim_rejects_claimed_at(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            saved = await repo.add(lot=_fresh_lot())
            assert saved.id is not None
            with pytest.raises(ValueError, match="claimed_at must be None"):
                await repo.update_status(
                    lot_id=saved.id,
                    new_status=PrizeLotStatus.RESERVED,
                    claimed_at=NOW,
                )


# --------------------------------------------------------------------------- #
# DB-CHECK last-line-of-defense
# --------------------------------------------------------------------------- #


class TestDbInvariants:
    @pytest.mark.asyncio
    async def test_amount_native_zero_violates_check(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PrizeLotORM).values(
                        currency="usdt_decimal",
                        amount_native=Decimal(0),
                        fee_buffer_native=Decimal(0),
                        status="active",
                        created_at=NOW,
                        claimed_at=None,
                    ),
                )

    @pytest.mark.asyncio
    async def test_fee_buffer_negative_violates_check(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PrizeLotORM).values(
                        currency="usdt_decimal",
                        amount_native=Decimal(1_000_000),
                        fee_buffer_native=Decimal(-1),
                        status="active",
                        created_at=NOW,
                        claimed_at=None,
                    ),
                )

    @pytest.mark.asyncio
    async def test_amount_not_greater_than_fee_violates_check(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PrizeLotORM).values(
                        currency="usdt_decimal",
                        amount_native=Decimal(100),
                        fee_buffer_native=Decimal(100),
                        status="active",
                        created_at=NOW,
                        claimed_at=None,
                    ),
                )

    @pytest.mark.asyncio
    async def test_unknown_currency_violates_check(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PrizeLotORM).values(
                        currency="btc",
                        amount_native=Decimal(1_000_000),
                        fee_buffer_native=Decimal(100_000),
                        status="active",
                        created_at=NOW,
                        claimed_at=None,
                    ),
                )

    @pytest.mark.asyncio
    async def test_unknown_status_violates_check(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PrizeLotORM).values(
                        currency="usdt_decimal",
                        amount_native=Decimal(1_000_000),
                        fee_buffer_native=Decimal(100_000),
                        status="frozen",
                        created_at=NOW,
                        claimed_at=None,
                    ),
                )

    @pytest.mark.asyncio
    async def test_claimed_without_claimed_at_violates_check(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`status='claimed' AND claimed_at IS NULL` запрещено."""
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PrizeLotORM).values(
                        currency="usdt_decimal",
                        amount_native=Decimal(1_000_000),
                        fee_buffer_native=Decimal(100_000),
                        status="claimed",
                        created_at=NOW,
                        claimed_at=None,
                    ),
                )

    @pytest.mark.asyncio
    async def test_non_claimed_with_claimed_at_violates_check(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`status!='claimed' AND claimed_at IS NOT NULL` запрещено."""
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PrizeLotORM).values(
                        currency="usdt_decimal",
                        amount_native=Decimal(1_000_000),
                        fee_buffer_native=Decimal(100_000),
                        status="active",
                        created_at=NOW,
                        claimed_at=NOW,
                    ),
                )
