"""Unit-тесты ``GetPrizePoolStatus`` (Спринт 4.1-E / Шаг E.9).

Покрытие:

* RBAC-flow: неактивный/неизвестный админ → ``AuthorizationError``;
  активный, но недостаточная роль → ``AdminAuthorizationDeniedError`` +
  запись ``ADMIN_AUTHORIZATION_DENIED`` в admin-аудите.
* Happy-path empty: пустой пул + нет лотов + не frozen — корректный
  Stars/TON/USDT снимок c balance=0, counts=0; admin-audit
  ``ADMIN_PRIZE_POOL_VIEWED`` записан.
* Happy-path populated: пул с балансами + смесь лотов разных
  статусов/валют → корректные счётчики per (currency, status).
* Freeze: если ``payout_freeze`` активен, ``output.freeze.is_frozen`` и
  payload audit отражают это.
* Audit non-idempotent: повторный вызов → 2 audit-записи (read-only +
  каждый просмотр должен быть в trail-е).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.monetization import (
    GetPrizePoolStatus,
    GetPrizePoolStatusInput,
)
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditSource,
    AdminAuthorizationDeniedError,
    AdminRole,
)
from pipirik_wars.domain.monetization.entities import (
    PayoutFreeze,
    PrizeLot,
    PrizeLotStatus,
    PrizePool,
)
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    FeeBufferAmount,
    StarsPoolBalance,
    TonNanoAmount,
    UsdtDecimalAmount,
)
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll, FakeAdminAuthzDenyAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clock import FakeClock
from tests.fakes.payout_freeze_repo import FakePayoutFreezeRepository
from tests.fakes.prize_lot_repo import FakePrizeLotRepository
from tests.fakes.prize_pool_repo import FakePrizePoolRepository
from tests.fakes.uow import FakeUnitOfWork

_NOW = datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC)
_LOT_CREATED = datetime(2026, 5, 10, 9, 0, 0, tzinfo=UTC)
_LOT_RESERVED = datetime(2026, 5, 11, 9, 0, 0, tzinfo=UTC)


def _build(
    *,
    authz: FakeAdminAuthzAllowAll | FakeAdminAuthzDenyAll | None = None,
    pool: FakePrizePoolRepository | None = None,
    freeze: FakePayoutFreezeRepository | None = None,
) -> tuple[
    GetPrizePoolStatus,
    FakeAdminRepository,
    FakePrizeLotRepository,
    FakePrizePoolRepository,
    FakePayoutFreezeRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    lots = FakePrizeLotRepository()
    pool_repo = pool or FakePrizePoolRepository()
    freeze_repo = freeze or FakePayoutFreezeRepository()
    admin_audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    return (
        GetPrizePoolStatus(
            uow=uow,
            admins=admins,
            prize_pool_repository=pool_repo,
            prize_lot_repository=lots,
            payout_freeze_repo=freeze_repo,
            admin_audit=admin_audit,
            clock=FakeClock(_NOW),
            authz=authz or FakeAdminAuthzAllowAll(),
        ),
        admins,
        lots,
        pool_repo,
        freeze_repo,
        admin_audit,
        uow,
    )


async def _seed_lot(
    lots: FakePrizeLotRepository,
    *,
    status: PrizeLotStatus,
    currency: Currency,
    amount_native: int = 1_000_000,
    fee_buffer_native: int = 100_000,
) -> PrizeLot:
    fresh = PrizeLot.freshly_generated(
        currency=currency,
        amount_native=amount_native,
        fee_buffer_native=FeeBufferAmount(fee_buffer_native),
        created_at=_LOT_CREATED,
    )
    stored = await lots.add(lot=fresh)
    assert stored.id is not None
    if status is PrizeLotStatus.ACTIVE:
        return stored
    if status is PrizeLotStatus.RESERVED:
        return await lots.update_status(
            lot_id=stored.id,
            new_status=PrizeLotStatus.RESERVED,
            reserved_at=_LOT_RESERVED,
        )
    if status is PrizeLotStatus.CLAIMED:
        await lots.update_status(
            lot_id=stored.id,
            new_status=PrizeLotStatus.RESERVED,
            reserved_at=_LOT_RESERVED,
        )
        return await lots.update_status(
            lot_id=stored.id,
            new_status=PrizeLotStatus.CLAIMED,
            claimed_at=_NOW,
        )
    if status is PrizeLotStatus.REFUNDED:
        return await lots.update_status(
            lot_id=stored.id,
            new_status=PrizeLotStatus.REFUNDED,
        )
    raise AssertionError(f"unsupported status: {status!r}")


@pytest.mark.asyncio
class TestGetPrizePoolStatusAuthorization:
    async def test_unknown_actor_raises(self) -> None:
        uc, _admins, _lots, _pool, _freeze, admin_audit, _uow = _build()
        with pytest.raises(AuthorizationError):
            await uc.execute(GetPrizePoolStatusInput(actor_tg_id=99))
        assert admin_audit.entries == []

    async def test_inactive_admin_raises(self) -> None:
        uc, admins, _lots, _pool, _freeze, admin_audit, _uow = _build()
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, is_active=False)
        with pytest.raises(AuthorizationError):
            await uc.execute(GetPrizePoolStatusInput(actor_tg_id=99))
        assert admin_audit.entries == []

    async def test_rbac_denied_writes_audit_and_raises(self) -> None:
        uc, admins, _lots, _pool, _freeze, admin_audit, _uow = _build(
            authz=FakeAdminAuthzDenyAll(),
        )
        admins.seed(tg_id=99, role=AdminRole.SUPPORT, admin_id=7)

        with pytest.raises(AdminAuthorizationDeniedError):
            await uc.execute(
                GetPrizePoolStatusInput(actor_tg_id=99, tg_chat_id=-1001),
            )

        assert len(admin_audit.entries) == 1
        denied = admin_audit.entries[0]
        assert denied.admin_id == 7
        assert denied.action is AdminAuditAction.ADMIN_AUTHORIZATION_DENIED
        assert denied.target_kind == "prize_pool"
        assert denied.target_id == "all"


@pytest.mark.asyncio
class TestGetPrizePoolStatusHappyPath:
    async def test_empty_pool_snapshot(self) -> None:
        uc, admins, _lots, _pool, _freeze, admin_audit, uow = _build()
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, admin_id=7)

        out = await uc.execute(
            GetPrizePoolStatusInput(actor_tg_id=99, tg_chat_id=-1001),
        )

        # Stars, TON, USDT — все нулевые.
        currencies = [row.currency for row in out.per_currency]
        assert currencies == [
            Currency.STARS,
            Currency.TON_NANO,
            Currency.USDT_DECIMAL,
        ]
        for row in out.per_currency:
            assert row.balance_native == 0
            assert row.active_lots == 0
            assert row.reserved_lots == 0
            assert row.claimed_lots == 0
            assert row.refunded_lots == 0

        assert out.freeze.is_frozen is False
        assert out.freeze.frozen_by_admin_id is None

        # admin-audit
        assert len(admin_audit.entries) == 1
        e = admin_audit.entries[0]
        assert e.admin_id == 7
        assert e.action is AdminAuditAction.ADMIN_PRIZE_POOL_VIEWED
        assert e.target_kind == "prize_pool"
        assert e.target_id == "all"
        assert e.source is AdminAuditSource.BOT
        assert e.tg_chat_id == -1001
        assert e.before is None
        assert e.after == {
            "per_currency": [
                {
                    "currency": "stars",
                    "balance_native": 0,
                    "active_lots": 0,
                    "reserved_lots": 0,
                    "claimed_lots": 0,
                    "refunded_lots": 0,
                },
                {
                    "currency": "ton_nano",
                    "balance_native": 0,
                    "active_lots": 0,
                    "reserved_lots": 0,
                    "claimed_lots": 0,
                    "refunded_lots": 0,
                },
                {
                    "currency": "usdt_decimal",
                    "balance_native": 0,
                    "active_lots": 0,
                    "reserved_lots": 0,
                    "claimed_lots": 0,
                    "refunded_lots": 0,
                },
            ],
            "is_frozen": False,
            "frozen_by_admin_id": None,
        }
        assert e.idempotency_key is None
        assert e.occurred_at == _NOW

        assert uow.commits == 1

    async def test_populated_pool_with_mixed_lots(self) -> None:
        pool_repo = FakePrizePoolRepository(
            state=PrizePool(
                stars=StarsPoolBalance(50),
                ton_nano=TonNanoAmount(2_000_000_000),
                usdt_decimal=UsdtDecimalAmount(15_000_000),
            ),
        )
        uc, admins, lots, _pool, _freeze, admin_audit, _uow = _build(
            pool=pool_repo,
        )
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, admin_id=7)

        # USDT: 2 ACTIVE + 1 RESERVED + 1 CLAIMED + 1 REFUNDED
        await _seed_lot(lots, status=PrizeLotStatus.ACTIVE, currency=Currency.USDT_DECIMAL)
        await _seed_lot(lots, status=PrizeLotStatus.ACTIVE, currency=Currency.USDT_DECIMAL)
        await _seed_lot(lots, status=PrizeLotStatus.RESERVED, currency=Currency.USDT_DECIMAL)
        await _seed_lot(lots, status=PrizeLotStatus.CLAIMED, currency=Currency.USDT_DECIMAL)
        await _seed_lot(lots, status=PrizeLotStatus.REFUNDED, currency=Currency.USDT_DECIMAL)

        # TON: 3 ACTIVE
        for _ in range(3):
            await _seed_lot(
                lots,
                status=PrizeLotStatus.ACTIVE,
                currency=Currency.TON_NANO,
                amount_native=500_000_000,
                fee_buffer_native=50_000_000,
            )

        out = await uc.execute(GetPrizePoolStatusInput(actor_tg_id=99))

        rows = {row.currency: row for row in out.per_currency}
        assert rows[Currency.STARS].balance_native == 50
        assert rows[Currency.STARS].active_lots == 0
        assert rows[Currency.TON_NANO].balance_native == 2_000_000_000
        assert rows[Currency.TON_NANO].active_lots == 3
        assert rows[Currency.TON_NANO].reserved_lots == 0
        assert rows[Currency.TON_NANO].claimed_lots == 0
        assert rows[Currency.TON_NANO].refunded_lots == 0
        assert rows[Currency.USDT_DECIMAL].balance_native == 15_000_000
        assert rows[Currency.USDT_DECIMAL].active_lots == 2
        assert rows[Currency.USDT_DECIMAL].reserved_lots == 1
        assert rows[Currency.USDT_DECIMAL].claimed_lots == 1
        assert rows[Currency.USDT_DECIMAL].refunded_lots == 1

        # one audit record
        assert len(admin_audit.entries) == 1
        after = admin_audit.entries[0].after
        assert after is not None
        per_currency_dump = after["per_currency"]
        assert isinstance(per_currency_dump, list)
        usdt = next(
            c
            for c in per_currency_dump
            if isinstance(c, dict) and c.get("currency") == "usdt_decimal"
        )
        assert usdt["active_lots"] == 2
        assert usdt["reserved_lots"] == 1
        assert usdt["claimed_lots"] == 1
        assert usdt["refunded_lots"] == 1


@pytest.mark.asyncio
class TestGetPrizePoolStatusFreeze:
    async def test_frozen_state_is_reflected_in_output_and_audit(self) -> None:
        freeze_repo = FakePayoutFreezeRepository(
            state=PayoutFreeze.frozen(
                admin_id=42,
                at=datetime(2026, 5, 1, 0, 0, tzinfo=UTC),
                reason="suspected abuse",
            ),
        )
        uc, admins, _lots, _pool, _freeze, admin_audit, _uow = _build(
            freeze=freeze_repo,
        )
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, admin_id=7)

        out = await uc.execute(GetPrizePoolStatusInput(actor_tg_id=99))

        assert out.freeze.is_frozen is True
        assert out.freeze.frozen_by_admin_id == 42
        assert out.freeze.reason == "suspected abuse"

        after = admin_audit.entries[0].after
        assert after is not None
        assert after["is_frozen"] is True
        assert after["frozen_by_admin_id"] == 42


@pytest.mark.asyncio
class TestGetPrizePoolStatusAuditPerCall:
    async def test_repeated_calls_record_separate_audit_entries(self) -> None:
        uc, admins, _lots, _pool, _freeze, admin_audit, _uow = _build()
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, admin_id=7)

        await uc.execute(GetPrizePoolStatusInput(actor_tg_id=99))
        await uc.execute(GetPrizePoolStatusInput(actor_tg_id=99))
        await uc.execute(GetPrizePoolStatusInput(actor_tg_id=99))

        # каждый просмотр — отдельная audit-запись (read-only audit-trail).
        assert len(admin_audit.entries) == 3
        for entry in admin_audit.entries:
            assert entry.action is AdminAuditAction.ADMIN_PRIZE_POOL_VIEWED
