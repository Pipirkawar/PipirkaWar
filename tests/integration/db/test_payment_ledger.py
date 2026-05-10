"""Integration-тесты `SqlAlchemyPaymentLedger` (Спринт 4.1-A, A.5).

Покрытие:

* round-trip `charge → SELECT` для STARS / TON_NANO / USDT_DECIMAL;
* идемпотентность `charge(...)` — повторный вызов с тем же
  `(player_id, idempotency_key)` и теми же `(currency, amount_native)`
  возвращает существующую строку без побочных эффектов и без
  `IntegrityError`;
* антифрод: повторный вызов с тем же `(player_id, idempotency_key)`,
  но другой `(currency | amount_native)`-парой — `IdempotencyConflictError`;
* разные игроки могут использовать одинаковые `idempotency_key`
  (UNIQUE — на паре `(player_id, idempotency_key)`, не на
  `idempotency_key` в одиночку);
* `get_by_idempotency_key` — возвращает сохранённый платёж или `None`;
* DB-CHECK-инварианты ловят прямой INSERT с rогон-данными
  (last-line-of-defense): bad-currency / bad-status / amount<1 /
  CONFIRMED без provider_payment_id / PENDING с confirmed_at.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.monetization.entities import PaymentStatus
from pipirik_wars.domain.monetization.errors import IdempotencyConflictError
from pipirik_wars.domain.monetization.value_objects import Currency, IdempotencyKey
from pipirik_wars.domain.player import Player
from pipirik_wars.infrastructure.db.models import PaymentORM
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyPaymentLedger,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

NOW = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


def _make_ledger(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyPaymentLedger:
    return SqlAlchemyPaymentLedger(uow=uow)


class TestSqlAlchemyPaymentLedgerRoundTrip:
    @pytest.mark.asyncio
    async def test_charge_stars_persists_and_returns_payment(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """STARS-charge → строка с правильными полями + возвращённый VO."""
        player = await _seed_player(uow, tg_id=10001)
        assert player.id is not None
        ledger = _make_ledger(uow)

        async with uow:
            payment = await ledger.charge(
                player_id=player.id,
                currency=Currency.STARS,
                amount_native=1,
                idempotency_key=IdempotencyKey("paid_roulette:10001:msg-1"),
                status=PaymentStatus.CONFIRMED,
                occurred_at=NOW,
                provider_payment_id="tg-charge-001",
                payload=MappingProxyType({"pack": "single", "n_spins": "1"}),
            )

        assert payment.player_id == player.id
        assert payment.currency is Currency.STARS
        assert payment.amount_native == 1
        assert payment.idempotency_key.value == "paid_roulette:10001:msg-1"
        assert payment.status is PaymentStatus.CONFIRMED
        assert payment.created_at.replace(tzinfo=UTC) == NOW
        assert payment.confirmed_at is not None
        assert payment.confirmed_at.replace(tzinfo=UTC) == NOW
        assert payment.provider_payment_id == "tg-charge-001"
        assert dict(payment.payload) == {"pack": "single", "n_spins": "1"}

        async with uow:
            stmt = select(
                PaymentORM.currency,
                PaymentORM.amount_native,
                PaymentORM.status,
                PaymentORM.provider_payment_id,
            ).where(PaymentORM.player_id == player.id)
            row = (await uow.session.execute(stmt)).one()
        assert row.currency == "stars"
        assert int(row.amount_native) == 1
        assert row.status == "confirmed"
        assert row.provider_payment_id == "tg-charge-001"

    @pytest.mark.asyncio
    async def test_charge_pending_status_persists_with_null_confirmed_at(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`PENDING` → `confirmed_at IS NULL` и `provider_payment_id` опционален."""
        player = await _seed_player(uow, tg_id=10002)
        assert player.id is not None
        ledger = _make_ledger(uow)

        async with uow:
            payment = await ledger.charge(
                player_id=player.id,
                currency=Currency.STARS,
                amount_native=9,
                idempotency_key=IdempotencyKey("paid_roulette:10002:pending"),
                status=PaymentStatus.PENDING,
                occurred_at=NOW,
                provider_payment_id=None,
                payload=None,
            )

        assert payment.status is PaymentStatus.PENDING
        assert payment.confirmed_at is None
        assert payment.provider_payment_id is None
        assert dict(payment.payload) == {}

    @pytest.mark.asyncio
    async def test_charge_ton_nano_persists_large_amount(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """TON_NANO с большим int (10^11) сохраняется без потери точности."""
        player = await _seed_player(uow, tg_id=10003)
        assert player.id is not None
        ledger = _make_ledger(uow)

        big_amount = 100_000_000_000  # 100 TON в нано-юнитах
        async with uow:
            payment = await ledger.charge(
                player_id=player.id,
                currency=Currency.TON_NANO,
                amount_native=big_amount,
                idempotency_key=IdempotencyKey("paid_roulette:10003:ton-1"),
                status=PaymentStatus.CONFIRMED,
                occurred_at=NOW,
                provider_payment_id="ton-tx-hash-001",
            )

        assert payment.currency is Currency.TON_NANO
        assert payment.amount_native == big_amount

        async with uow:
            stmt = select(PaymentORM.amount_native).where(
                PaymentORM.player_id == player.id,
            )
            stored = (await uow.session.execute(stmt)).scalar_one()
        assert int(stored) == big_amount


class TestSqlAlchemyPaymentLedgerIdempotency:
    @pytest.mark.asyncio
    async def test_charge_twice_with_same_key_creates_one_row(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Honest retry: `charge(...)` + `charge(...)` с тем же ключом → одна строка."""
        player = await _seed_player(uow, tg_id=20001)
        assert player.id is not None
        ledger = _make_ledger(uow)
        key = IdempotencyKey("paid_roulette:20001:dup")

        async with uow:
            first = await ledger.charge(
                player_id=player.id,
                currency=Currency.STARS,
                amount_native=1,
                idempotency_key=key,
                status=PaymentStatus.CONFIRMED,
                occurred_at=NOW,
                provider_payment_id="tg-charge-dup",
            )
        async with uow:
            second = await ledger.charge(
                player_id=player.id,
                currency=Currency.STARS,
                amount_native=1,
                idempotency_key=key,
                status=PaymentStatus.CONFIRMED,
                occurred_at=NOW,
                provider_payment_id="tg-charge-dup",
            )

        # Возвращаемая запись — та же.
        assert first == second

        async with uow:
            count_stmt = (
                select(func.count())
                .select_from(PaymentORM)
                .where(PaymentORM.player_id == player.id)
            )
            count = (await uow.session.execute(count_stmt)).scalar_one()
        assert count == 1

    @pytest.mark.asyncio
    async def test_charge_with_same_key_but_different_amount_raises_conflict(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Антифрод: тот же ключ, но другая сумма → `IdempotencyConflictError`."""
        player = await _seed_player(uow, tg_id=20002)
        assert player.id is not None
        ledger = _make_ledger(uow)
        key = IdempotencyKey("paid_roulette:20002:conflict")

        async with uow:
            await ledger.charge(
                player_id=player.id,
                currency=Currency.STARS,
                amount_native=1,
                idempotency_key=key,
                status=PaymentStatus.CONFIRMED,
                occurred_at=NOW,
                provider_payment_id="tg-charge-1",
            )
        async with uow:
            with pytest.raises(IdempotencyConflictError) as exc_info:
                await ledger.charge(
                    player_id=player.id,
                    currency=Currency.STARS,
                    amount_native=9,  # ← другая сумма
                    idempotency_key=key,
                    status=PaymentStatus.CONFIRMED,
                    occurred_at=LATER,
                    provider_payment_id="tg-charge-2",
                )
        err = exc_info.value
        assert err.idempotency_key == "paid_roulette:20002:conflict"
        assert err.existing_amount_native == 1
        assert err.attempted_amount_native == 9

    @pytest.mark.asyncio
    async def test_charge_with_same_key_but_different_currency_raises_conflict(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Антифрод: тот же ключ, но другая валюта → `IdempotencyConflictError`."""
        player = await _seed_player(uow, tg_id=20003)
        assert player.id is not None
        ledger = _make_ledger(uow)
        key = IdempotencyKey("paid_roulette:20003:cur-conflict")

        async with uow:
            await ledger.charge(
                player_id=player.id,
                currency=Currency.STARS,
                amount_native=1,
                idempotency_key=key,
                status=PaymentStatus.CONFIRMED,
                occurred_at=NOW,
                provider_payment_id="tg-charge-1",
            )
        async with uow:
            with pytest.raises(IdempotencyConflictError):
                await ledger.charge(
                    player_id=player.id,
                    currency=Currency.TON_NANO,  # ← другая валюта
                    amount_native=1,
                    idempotency_key=key,
                    status=PaymentStatus.CONFIRMED,
                    occurred_at=LATER,
                    provider_payment_id="ton-tx-hash",
                )


class TestSqlAlchemyPaymentLedgerIsolation:
    @pytest.mark.asyncio
    async def test_two_players_can_share_idempotency_key(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Уникальность — на паре `(player_id, idempotency_key)`, разные игроки могут совпадать."""
        alice = await _seed_player(uow, tg_id=30001)
        bob = await _seed_player(uow, tg_id=30002)
        assert alice.id is not None
        assert bob.id is not None
        ledger = _make_ledger(uow)
        shared_key = IdempotencyKey("paid_roulette:shared")

        async with uow:
            alice_payment = await ledger.charge(
                player_id=alice.id,
                currency=Currency.STARS,
                amount_native=1,
                idempotency_key=shared_key,
                status=PaymentStatus.CONFIRMED,
                occurred_at=NOW,
                provider_payment_id="tg-alice",
            )
        async with uow:
            bob_payment = await ledger.charge(
                player_id=bob.id,
                currency=Currency.STARS,
                amount_native=9,
                idempotency_key=shared_key,
                status=PaymentStatus.CONFIRMED,
                occurred_at=LATER,
                provider_payment_id="tg-bob",
            )

        assert alice_payment.player_id == alice.id
        assert bob_payment.player_id == bob.id
        assert alice_payment.amount_native == 1
        assert bob_payment.amount_native == 9


class TestSqlAlchemyPaymentLedgerGetByIdempotencyKey:
    @pytest.mark.asyncio
    async def test_get_by_idempotency_key_returns_none_if_not_seen(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Несуществующий ключ → `None`."""
        ledger = _make_ledger(uow)
        async with uow:
            result = await ledger.get_by_idempotency_key(
                idempotency_key=IdempotencyKey("does-not-exist"),
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_idempotency_key_returns_stored_payment(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Существующий ключ → сохранённый `Payment`-VO."""
        player = await _seed_player(uow, tg_id=40001)
        assert player.id is not None
        ledger = _make_ledger(uow)
        key = IdempotencyKey("paid_roulette:40001:lookup")

        async with uow:
            inserted = await ledger.charge(
                player_id=player.id,
                currency=Currency.STARS,
                amount_native=9,
                idempotency_key=key,
                status=PaymentStatus.CONFIRMED,
                occurred_at=NOW,
                provider_payment_id="tg-charge-lookup",
                payload=MappingProxyType({"pack": "pack_10", "n_spins": "10"}),
            )

        async with uow:
            looked_up = await ledger.get_by_idempotency_key(idempotency_key=key)

        assert looked_up is not None
        assert looked_up == inserted
        assert dict(looked_up.payload) == {"pack": "pack_10", "n_spins": "10"}


class TestSqlAlchemyPaymentLedgerDbInvariants:
    """DB-CHECK-инварианты как last-line-of-defense (защита от прямых SQL-правок)."""

    @pytest.mark.asyncio
    async def test_db_rejects_invalid_currency(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=50001)
        assert player.id is not None

        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PaymentORM).values(
                        player_id=player.id,
                        currency="rubles",  # ← вне whitelist
                        amount_native=Decimal(1),
                        idempotency_key="bad-currency",
                        status="pending",
                        provider_payment_id=None,
                        payload={},
                        created_at=NOW,
                        confirmed_at=None,
                    ),
                )

    @pytest.mark.asyncio
    async def test_db_rejects_invalid_status(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=50002)
        assert player.id is not None

        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PaymentORM).values(
                        player_id=player.id,
                        currency="stars",
                        amount_native=Decimal(1),
                        idempotency_key="bad-status",
                        status="awaiting_review",  # ← вне whitelist
                        provider_payment_id=None,
                        payload={},
                        created_at=NOW,
                        confirmed_at=None,
                    ),
                )

    @pytest.mark.asyncio
    async def test_db_rejects_zero_amount(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=50003)
        assert player.id is not None

        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PaymentORM).values(
                        player_id=player.id,
                        currency="stars",
                        amount_native=Decimal(0),  # ← amount_native >= 1 нарушено
                        idempotency_key="bad-amount",
                        status="pending",
                        provider_payment_id=None,
                        payload={},
                        created_at=NOW,
                        confirmed_at=None,
                    ),
                )

    @pytest.mark.asyncio
    async def test_db_rejects_confirmed_without_provider_payment_id(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=50004)
        assert player.id is not None

        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PaymentORM).values(
                        player_id=player.id,
                        currency="stars",
                        amount_native=Decimal(1),
                        idempotency_key="bad-confirmed",
                        status="confirmed",
                        provider_payment_id=None,  # ← CONFIRMED без id нарушает CHECK
                        payload={},
                        created_at=NOW,
                        confirmed_at=NOW,
                    ),
                )

    @pytest.mark.asyncio
    async def test_db_rejects_pending_with_confirmed_at(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=50005)
        assert player.id is not None

        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(PaymentORM).values(
                        player_id=player.id,
                        currency="stars",
                        amount_native=Decimal(1),
                        idempotency_key="bad-pending",
                        status="pending",
                        provider_payment_id=None,
                        payload={},
                        created_at=NOW,
                        confirmed_at=NOW,  # ← PENDING с заполненным confirmed_at нарушает CHECK
                    ),
                )
