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
                reserved_at=NOW,
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

            reserved_at = NOW + timedelta(seconds=42)
            reserved = await repo.update_status(
                lot_id=saved.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=reserved_at,
            )
            assert reserved.status is PrizeLotStatus.RESERVED
            assert reserved.reserved_at == reserved_at
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
                reserved_at=NOW,
            )
            refunded = await repo.update_status(
                lot_id=saved.id,
                new_status=PrizeLotStatus.REFUNDED,
            )
        assert refunded.status is PrizeLotStatus.REFUNDED
        # `reserved_at` сохранён после RESERVED → REFUNDED (нужно для аудита)
        assert refunded.reserved_at == NOW

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
                reserved_at=NOW,
            )
            with pytest.raises(PrizeLotStatusTransitionError) as exc_info:
                await repo.update_status(
                    lot_id=saved.id,
                    new_status=PrizeLotStatus.RESERVED,
                    reserved_at=NOW,
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
                    reserved_at=NOW,
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
                reserved_at=NOW,
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
                    reserved_at=NOW,
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

    @pytest.mark.asyncio
    async def test_active_with_reserved_at_violates_check(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """D.9.b: `status='active' AND reserved_at IS NOT NULL` запрещено."""
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PrizeLotORM).values(
                        currency="usdt_decimal",
                        amount_native=Decimal(1_000_000),
                        fee_buffer_native=Decimal(100_000),
                        status="active",
                        created_at=NOW,
                        reserved_at=NOW,
                        claimed_at=None,
                    ),
                )

    @pytest.mark.asyncio
    async def test_reserved_without_reserved_at_violates_check(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """D.9.b: `status='reserved' AND reserved_at IS NULL` запрещено."""
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PrizeLotORM).values(
                        currency="usdt_decimal",
                        amount_native=Decimal(1_000_000),
                        fee_buffer_native=Decimal(100_000),
                        status="reserved",
                        created_at=NOW,
                        reserved_at=None,
                        claimed_at=None,
                    ),
                )


# --------------------------------------------------------------------------- #
# list_expired_reserved(...) — refund-cron-обход (D.9.b)
# --------------------------------------------------------------------------- #


class TestListExpiredReserved:
    """`IPrizeLotRepository.list_expired_reserved(...)` (D.9.b).

    Используется expire-cron-ом `ExpireReservedPrizeLots` (D.9.c) для
    обнаружения RESERVED-лотов с истёкшим TTL и возврата их в пул.
    """

    @pytest.mark.asyncio
    async def test_empty_when_no_reserved_lots(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            # есть ACTIVE и REFUNDED — но нет RESERVED
            await repo.add(lot=_fresh_lot())
            refunded = await repo.add(lot=_fresh_lot(amount_native=2_000_000))
            assert refunded.id is not None
            await repo.update_status(
                lot_id=refunded.id,
                new_status=PrizeLotStatus.REFUNDED,
            )

        async with uow:
            result = await repo.list_expired_reserved(
                currency=Currency.USDT_DECIMAL,
                expired_before=NOW + timedelta(hours=1),
            )
        assert result == ()

    @pytest.mark.asyncio
    async def test_returns_only_expired_reserved_lots(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Возвращает только лоты с `reserved_at <= expired_before`."""
        repo = _make_repo(uow)
        cutoff = NOW + timedelta(hours=2)
        async with uow:
            stale = await repo.add(lot=_fresh_lot(amount_native=1_000_000))
            fresh = await repo.add(lot=_fresh_lot(amount_native=2_000_000))
            assert stale.id is not None
            assert fresh.id is not None
            # stale зарезервирован задолго до cutoff
            await repo.update_status(
                lot_id=stale.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=NOW,
            )
            # fresh зарезервирован после cutoff — не должен попасть в выдачу
            await repo.update_status(
                lot_id=fresh.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=cutoff + timedelta(seconds=1),
            )

        async with uow:
            result = await repo.list_expired_reserved(
                currency=Currency.USDT_DECIMAL,
                expired_before=cutoff,
            )
        assert [lot.id for lot in result] == [stale.id]

    @pytest.mark.asyncio
    async def test_filters_by_currency(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Возвращает лоты только запрошенной `currency`."""
        repo = _make_repo(uow)
        async with uow:
            usdt = await repo.add(lot=_fresh_lot(currency=Currency.USDT_DECIMAL))
            ton = await repo.add(
                lot=_fresh_lot(
                    currency=Currency.TON_NANO,
                    amount_native=2_000_000_000,
                    fee_buffer_native=10_000_000,
                )
            )
            assert usdt.id is not None
            assert ton.id is not None
            await repo.update_status(
                lot_id=usdt.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=NOW,
            )
            await repo.update_status(
                lot_id=ton.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=NOW,
            )

        cutoff = NOW + timedelta(hours=1)
        async with uow:
            usdt_result = await repo.list_expired_reserved(
                currency=Currency.USDT_DECIMAL,
                expired_before=cutoff,
            )
            ton_result = await repo.list_expired_reserved(
                currency=Currency.TON_NANO,
                expired_before=cutoff,
            )
        assert [lot.id for lot in usdt_result] == [usdt.id]
        assert [lot.id for lot in ton_result] == [ton.id]

    @pytest.mark.asyncio
    async def test_excludes_non_reserved_statuses(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`ACTIVE` / `CLAIMED` / `REFUNDED` исключены даже при `reserved_at <= cutoff`."""
        repo = _make_repo(uow)
        async with uow:
            active = await repo.add(lot=_fresh_lot(amount_native=1_000_000))
            claimed_lot = await repo.add(lot=_fresh_lot(amount_native=2_000_000))
            refunded = await repo.add(lot=_fresh_lot(amount_native=3_000_000))
            reserved = await repo.add(lot=_fresh_lot(amount_native=4_000_000))
            assert active.id is not None
            assert claimed_lot.id is not None
            assert refunded.id is not None
            assert reserved.id is not None
            # claimed: ACTIVE → RESERVED → CLAIMED (reserved_at сохранён)
            await repo.update_status(
                lot_id=claimed_lot.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=NOW,
            )
            await repo.update_status(
                lot_id=claimed_lot.id,
                new_status=PrizeLotStatus.CLAIMED,
                claimed_at=NOW + timedelta(minutes=5),
            )
            # refunded: ACTIVE → REFUNDED (reserved_at=None)
            await repo.update_status(
                lot_id=refunded.id,
                new_status=PrizeLotStatus.REFUNDED,
            )
            # reserved
            await repo.update_status(
                lot_id=reserved.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=NOW,
            )

        async with uow:
            result = await repo.list_expired_reserved(
                currency=Currency.USDT_DECIMAL,
                expired_before=NOW + timedelta(hours=1),
            )
        assert [lot.id for lot in result] == [reserved.id]

    @pytest.mark.asyncio
    async def test_orders_by_reserved_at_ascending(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Лоты сортируются по `reserved_at ASC` (самые старые вперёд)."""
        repo = _make_repo(uow)
        async with uow:
            first = await repo.add(lot=_fresh_lot(amount_native=1_000_000))
            second = await repo.add(lot=_fresh_lot(amount_native=2_000_000))
            third = await repo.add(lot=_fresh_lot(amount_native=3_000_000))
            assert first.id is not None
            assert second.id is not None
            assert third.id is not None
            # Намеренно резервируем в обратном порядке
            await repo.update_status(
                lot_id=third.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=NOW + timedelta(minutes=30),
            )
            await repo.update_status(
                lot_id=first.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=NOW,
            )
            await repo.update_status(
                lot_id=second.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=NOW + timedelta(minutes=15),
            )

        async with uow:
            result = await repo.list_expired_reserved(
                currency=Currency.USDT_DECIMAL,
                expired_before=NOW + timedelta(hours=1),
            )
        assert [lot.id for lot in result] == [first.id, second.id, third.id]

    @pytest.mark.asyncio
    async def test_limit_truncates_result(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`limit` обрезает результат после сортировки."""
        repo = _make_repo(uow)
        async with uow:
            lots: list[PrizeLot] = []
            for i in range(5):
                lot = await repo.add(
                    lot=_fresh_lot(amount_native=1_000_000 + i),
                )
                assert lot.id is not None
                lots.append(lot)
                await repo.update_status(
                    lot_id=lot.id,
                    new_status=PrizeLotStatus.RESERVED,
                    reserved_at=NOW + timedelta(minutes=i),
                )

        async with uow:
            result = await repo.list_expired_reserved(
                currency=Currency.USDT_DECIMAL,
                expired_before=NOW + timedelta(hours=1),
                limit=2,
            )
        assert [lot.id for lot in result] == [lots[0].id, lots[1].id]

    @pytest.mark.asyncio
    async def test_inclusive_cutoff_boundary(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`reserved_at == expired_before` включается в выдачу (`<=` cutoff)."""
        repo = _make_repo(uow)
        cutoff = NOW + timedelta(hours=1)
        async with uow:
            lot = await repo.add(lot=_fresh_lot())
            assert lot.id is not None
            await repo.update_status(
                lot_id=lot.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=cutoff,
            )

        async with uow:
            result = await repo.list_expired_reserved(
                currency=Currency.USDT_DECIMAL,
                expired_before=cutoff,
            )
        assert [lot.id for lot in result] == [lot.id]


# --------------------------------------------------------------------------- #
# count_by_status(currency, status) — Спринт 4.1-E, E.9
# --------------------------------------------------------------------------- #


class TestCountByStatus:
    @pytest.mark.asyncio
    async def test_empty_table_returns_zero(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            for status in (
                PrizeLotStatus.ACTIVE,
                PrizeLotStatus.RESERVED,
                PrizeLotStatus.CLAIMED,
                PrizeLotStatus.REFUNDED,
            ):
                for currency in (
                    Currency.STARS,
                    Currency.TON_NANO,
                    Currency.USDT_DECIMAL,
                ):
                    assert (
                        await repo.count_by_status(
                            currency=currency,
                            status=status,
                        )
                        == 0
                    )

    @pytest.mark.asyncio
    async def test_counts_match_mixed_population(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = _make_repo(uow)
        async with uow:
            # 2 ACTIVE USDT
            await repo.add(lot=_fresh_lot(currency=Currency.USDT_DECIMAL))
            await repo.add(lot=_fresh_lot(currency=Currency.USDT_DECIMAL))
            # 1 ACTIVE TON
            await repo.add(
                lot=_fresh_lot(
                    currency=Currency.TON_NANO,
                    amount_native=500_000_000,
                    fee_buffer_native=50_000_000,
                ),
            )
            # 1 RESERVED USDT
            reserved = await repo.add(lot=_fresh_lot(currency=Currency.USDT_DECIMAL))
            assert reserved.id is not None
            await repo.update_status(
                lot_id=reserved.id,
                new_status=PrizeLotStatus.RESERVED,
                reserved_at=NOW,
            )
            # 1 REFUNDED USDT
            refunded = await repo.add(lot=_fresh_lot(currency=Currency.USDT_DECIMAL))
            assert refunded.id is not None
            await repo.update_status(
                lot_id=refunded.id,
                new_status=PrizeLotStatus.REFUNDED,
            )

        async with uow:
            assert (
                await repo.count_by_status(
                    currency=Currency.USDT_DECIMAL,
                    status=PrizeLotStatus.ACTIVE,
                )
                == 2
            )
            assert (
                await repo.count_by_status(
                    currency=Currency.USDT_DECIMAL,
                    status=PrizeLotStatus.RESERVED,
                )
                == 1
            )
            assert (
                await repo.count_by_status(
                    currency=Currency.USDT_DECIMAL,
                    status=PrizeLotStatus.REFUNDED,
                )
                == 1
            )
            assert (
                await repo.count_by_status(
                    currency=Currency.USDT_DECIMAL,
                    status=PrizeLotStatus.CLAIMED,
                )
                == 0
            )
            assert (
                await repo.count_by_status(
                    currency=Currency.TON_NANO,
                    status=PrizeLotStatus.ACTIVE,
                )
                == 1
            )
            assert (
                await repo.count_by_status(
                    currency=Currency.STARS,
                    status=PrizeLotStatus.ACTIVE,
                )
                == 0
            )
