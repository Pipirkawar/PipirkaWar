"""Unit-тесты ``RefundLot`` (Спринт 4.1-E / Шаг E.8).

Покрытие:

* RBAC-flow: неактивный/неизвестный админ → ``AuthorizationError``;
  активный, но недостаточная роль → ``AdminAuthorizationDeniedError`` +
  запись ``ADMIN_AUTHORIZATION_DENIED`` в admin-аудите.
* Валидация: ``lot_id <= 0`` / пустой ``reason`` → ``ValueError``.
* Lot-resolution: несуществующий ``lot_id`` → ``PrizeLotNotFoundError``.
* Happy-path: ``ACTIVE → REFUNDED``: ``update_status``, ``apply_increment``,
  player-audit ``PRIZE_LOT_REFUNDED`` + admin-audit ``ADMIN_REFUND_LOT``.
* Happy-path: ``RESERVED → REFUNDED``: симметрично, ``prev_status=reserved``.
* Идемпотентность: ``REFUNDED → REFUNDED`` — no-op (без mutation, без audit),
  ``pool_after_native`` = текущий баланс.
* Terminal-block: ``CLAIMED`` → ``PrizeLotStatusTransitionError`` (домен).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.monetization import (
    RefundLot,
    RefundLotInput,
)
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditSource,
    AdminAuthorizationDeniedError,
    AdminRole,
)
from pipirik_wars.domain.monetization.entities import (
    PrizeLot,
    PrizeLotStatus,
    PrizePool,
)
from pipirik_wars.domain.monetization.errors import (
    PrizeLotNotFoundError,
    PrizeLotStatusTransitionError,
)
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    FeeBufferAmount,
    StarsPoolBalance,
    TonNanoAmount,
    UsdtDecimalAmount,
)
from pipirik_wars.domain.shared.ports import AuditAction, AuditSource
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll, FakeAdminAuthzDenyAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.audit import FakeAuditLogger
from tests.fakes.clock import FakeClock
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
) -> tuple[
    RefundLot,
    FakeAdminRepository,
    FakePrizeLotRepository,
    FakePrizePoolRepository,
    FakeAuditLogger,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    lots = FakePrizeLotRepository()
    pool_repo = pool or FakePrizePoolRepository()
    audit = FakeAuditLogger()
    admin_audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    return (
        RefundLot(
            uow=uow,
            admins=admins,
            prize_lot_repository=lots,
            prize_pool_repository=pool_repo,
            audit=audit,
            admin_audit=admin_audit,
            clock=FakeClock(_NOW),
            authz=authz or FakeAdminAuthzAllowAll(),
        ),
        admins,
        lots,
        pool_repo,
        audit,
        admin_audit,
        uow,
    )


async def _seed_lot(
    lots: FakePrizeLotRepository,
    *,
    status: PrizeLotStatus,
    currency: Currency = Currency.USDT_DECIMAL,
    amount_native: int = 5_000_000,
    fee_buffer_native: int = 500_000,
) -> PrizeLot:
    """Создать лот в указанном `status` через `add(...)` + последовательные
    `update_status(...)`-переходы (имитирует production-flow)."""
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
        reserved = await lots.update_status(
            lot_id=stored.id,
            new_status=PrizeLotStatus.RESERVED,
            reserved_at=_LOT_RESERVED,
        )
        return await lots.update_status(
            lot_id=reserved.id,  # type: ignore[arg-type]
            new_status=PrizeLotStatus.CLAIMED,
            claimed_at=_NOW,
        )
    if status is PrizeLotStatus.REFUNDED:
        return await lots.update_status(
            lot_id=stored.id,
            new_status=PrizeLotStatus.REFUNDED,
        )
    raise AssertionError(f"unsupported seed status: {status!r}")


@pytest.mark.asyncio
class TestRefundLotAuthorization:
    async def test_unknown_actor_raises(self) -> None:
        uc, _admins, lots, pool, audit, admin_audit, _uow = _build()
        lot = await _seed_lot(lots, status=PrizeLotStatus.ACTIVE)
        assert lot.id is not None

        with pytest.raises(AuthorizationError):
            await uc.execute(
                RefundLotInput(actor_tg_id=99, lot_id=lot.id, reason="audit"),
            )

        assert audit.entries == []
        assert admin_audit.entries == []
        assert pool.calls == []

    async def test_inactive_admin_raises(self) -> None:
        uc, admins, lots, pool, audit, admin_audit, _uow = _build()
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, is_active=False)
        lot = await _seed_lot(lots, status=PrizeLotStatus.ACTIVE)
        assert lot.id is not None

        with pytest.raises(AuthorizationError):
            await uc.execute(
                RefundLotInput(actor_tg_id=99, lot_id=lot.id, reason="audit"),
            )

        assert audit.entries == []
        assert admin_audit.entries == []
        assert pool.calls == []

    async def test_rbac_denied_writes_admin_audit_and_raises(self) -> None:
        uc, admins, lots, pool, audit, admin_audit, _uow = _build(
            authz=FakeAdminAuthzDenyAll(),
        )
        admins.seed(tg_id=99, role=AdminRole.SUPPORT, admin_id=7)
        lot = await _seed_lot(lots, status=PrizeLotStatus.ACTIVE)
        assert lot.id is not None

        with pytest.raises(AdminAuthorizationDeniedError):
            await uc.execute(
                RefundLotInput(actor_tg_id=99, lot_id=lot.id, reason="audit"),
            )

        assert audit.entries == []
        assert len(admin_audit.entries) == 1
        denied = admin_audit.entries[0]
        assert denied.admin_id == 7
        assert denied.action is AdminAuditAction.ADMIN_AUTHORIZATION_DENIED
        assert denied.target_kind == "prize_lot"
        assert denied.target_id == str(lot.id)
        assert pool.calls == []


@pytest.mark.asyncio
class TestRefundLotValidation:
    async def test_non_positive_lot_id_rejected(self) -> None:
        uc, admins, _lots, _pool, _audit, _admin_audit, _uow = _build()
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN)

        with pytest.raises(ValueError, match="lot_id must be a positive int"):
            await uc.execute(
                RefundLotInput(actor_tg_id=99, lot_id=0, reason="audit"),
            )
        with pytest.raises(ValueError, match="lot_id must be a positive int"):
            await uc.execute(
                RefundLotInput(actor_tg_id=99, lot_id=-1, reason="audit"),
            )

    async def test_empty_reason_rejected(self) -> None:
        uc, admins, lots, _pool, _audit, _admin_audit, _uow = _build()
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN)
        lot = await _seed_lot(lots, status=PrizeLotStatus.ACTIVE)
        assert lot.id is not None

        with pytest.raises(ValueError, match="reason must be a non-empty"):
            await uc.execute(
                RefundLotInput(actor_tg_id=99, lot_id=lot.id, reason=""),
            )
        with pytest.raises(ValueError, match="reason must be a non-empty"):
            await uc.execute(
                RefundLotInput(actor_tg_id=99, lot_id=lot.id, reason="   "),
            )

    async def test_lot_not_found_raises(self) -> None:
        uc, admins, _lots, pool, audit, admin_audit, _uow = _build()
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, admin_id=7)

        with pytest.raises(PrizeLotNotFoundError):
            await uc.execute(
                RefundLotInput(actor_tg_id=99, lot_id=12345, reason="audit"),
            )

        assert audit.entries == []
        assert admin_audit.entries == []
        assert pool.calls == []


@pytest.mark.asyncio
class TestRefundLotHappyPath:
    async def test_active_lot_refunded_to_pool(self) -> None:
        # pre-fill pool to verify increment is +amount_native (gross)
        pool_repo = FakePrizePoolRepository(
            state=PrizePool(
                stars=StarsPoolBalance(0),
                ton_nano=TonNanoAmount(0),
                usdt_decimal=UsdtDecimalAmount(10_000_000),
            ),
        )
        uc, admins, lots, pool, audit, admin_audit, uow = _build(pool=pool_repo)
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, admin_id=7)
        lot = await _seed_lot(
            lots,
            status=PrizeLotStatus.ACTIVE,
            currency=Currency.USDT_DECIMAL,
            amount_native=5_000_000,
            fee_buffer_native=500_000,
        )
        assert lot.id is not None

        out = await uc.execute(
            RefundLotInput(
                actor_tg_id=99,
                lot_id=lot.id,
                reason="manual rollback for incident #42",
                tg_chat_id=-1001,
            ),
        )

        assert out.lot_id == lot.id
        assert out.was_already_refunded is False
        assert out.pool_after_native == 15_000_000  # 10M + 5M (gross)

        # lot moved to REFUNDED
        stored = await lots.get_by_id(lot_id=lot.id)
        assert stored is not None
        assert stored.status is PrizeLotStatus.REFUNDED

        # pool increment was +amount_native (gross)
        assert len(pool.calls) == 1
        assert pool.calls[0].currency is Currency.USDT_DECIMAL
        assert pool.calls[0].amount_native == 5_000_000

        # player-side audit
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action is AuditAction.PRIZE_LOT_REFUNDED
        assert a.source is AuditSource.ADMIN_REFUND
        assert a.actor_id == 7
        assert a.target_kind == "prize_lot"
        assert a.target_id == f"{lot.id}:refund"
        assert a.idempotency_key == f"admin_refund_lot:{lot.id}"
        assert a.occurred_at == _NOW
        assert a.before is None
        assert a.after == {
            "lot_id": lot.id,
            "currency": "usdt_decimal",
            "amount_native": 5_000_000,
            "fee_buffer_native": 500_000,
            "prev_status": "active",
            "pool_after_native": 15_000_000,
            "reason": "admin",
            "admin_id": 7,
            "reason_detail": "manual rollback for incident #42",
        }

        # admin-side audit
        assert len(admin_audit.entries) == 1
        ad = admin_audit.entries[0]
        assert ad.admin_id == 7
        assert ad.action is AdminAuditAction.ADMIN_REFUND_LOT
        assert ad.target_kind == "prize_lot"
        assert ad.target_id == str(lot.id)
        assert ad.source is AdminAuditSource.BOT
        assert ad.tg_chat_id == -1001
        assert ad.reason == "manual rollback for incident #42"
        assert ad.before == {
            "status": "active",
            "currency": "usdt_decimal",
            "amount_native": 5_000_000,
            "fee_buffer_native": 500_000,
        }
        assert ad.after == {
            "status": "refunded",
            "currency": "usdt_decimal",
            "amount_native": 5_000_000,
            "pool_after_native": 15_000_000,
        }
        assert ad.occurred_at == _NOW

        # single transaction
        assert uow.commits == 1
        assert uow.rollbacks == 0

    async def test_reserved_lot_refunded_records_prev_status_reserved(
        self,
    ) -> None:
        uc, admins, lots, pool, audit, admin_audit, _uow = _build()
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, admin_id=7)
        lot = await _seed_lot(
            lots,
            status=PrizeLotStatus.RESERVED,
            currency=Currency.TON_NANO,
            amount_native=2_000_000_000,
            fee_buffer_native=100_000_000,
        )
        assert lot.id is not None

        out = await uc.execute(
            RefundLotInput(
                actor_tg_id=99,
                lot_id=lot.id,
                reason="stuck reserve > 48h",
            ),
        )

        assert out.was_already_refunded is False
        assert out.pool_after_native == 2_000_000_000

        stored = await lots.get_by_id(lot_id=lot.id)
        assert stored is not None
        assert stored.status is PrizeLotStatus.REFUNDED

        a = audit.entries[0]
        assert a.after is not None
        assert a.after["prev_status"] == "reserved"
        assert a.after["currency"] == "ton_nano"

        ad = admin_audit.entries[0]
        assert ad.before == {
            "status": "reserved",
            "currency": "ton_nano",
            "amount_native": 2_000_000_000,
            "fee_buffer_native": 100_000_000,
        }
        assert ad.after == {
            "status": "refunded",
            "currency": "ton_nano",
            "amount_native": 2_000_000_000,
            "pool_after_native": 2_000_000_000,
        }
        assert pool.calls[0].currency is Currency.TON_NANO

    async def test_reason_is_trimmed(self) -> None:
        uc, admins, lots, _pool, audit, admin_audit, _uow = _build()
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, admin_id=7)
        lot = await _seed_lot(lots, status=PrizeLotStatus.ACTIVE)
        assert lot.id is not None

        await uc.execute(
            RefundLotInput(
                actor_tg_id=99,
                lot_id=lot.id,
                reason="   trimmed   ",
            ),
        )

        assert audit.entries[0].reason == "trimmed"
        assert admin_audit.entries[0].reason == "trimmed"


@pytest.mark.asyncio
class TestRefundLotIdempotency:
    async def test_already_refunded_is_pure_no_op(self) -> None:
        pool_repo = FakePrizePoolRepository(
            state=PrizePool(
                stars=StarsPoolBalance(0),
                ton_nano=TonNanoAmount(0),
                usdt_decimal=UsdtDecimalAmount(15_000_000),
            ),
        )
        uc, admins, lots, pool, audit, admin_audit, uow = _build(pool=pool_repo)
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, admin_id=7)
        lot = await _seed_lot(lots, status=PrizeLotStatus.REFUNDED)
        assert lot.id is not None

        out = await uc.execute(
            RefundLotInput(
                actor_tg_id=99,
                lot_id=lot.id,
                reason="duplicate retry",
            ),
        )

        assert out.was_already_refunded is True
        assert out.pool_after_native == 15_000_000

        # status preserved
        stored = await lots.get_by_id(lot_id=lot.id)
        assert stored is not None
        assert stored.status is PrizeLotStatus.REFUNDED

        # no apply_increment, no audit entries
        assert pool.calls == []
        assert audit.entries == []
        assert admin_audit.entries == []

        # UoW was opened (read-only), but no audit was written
        assert uow.commits == 1
        assert uow.rollbacks == 0


@pytest.mark.asyncio
class TestRefundLotTerminalBlock:
    async def test_claimed_lot_rejects_with_status_transition_error(
        self,
    ) -> None:
        uc, admins, lots, pool, audit, admin_audit, _uow = _build()
        admins.seed(tg_id=99, role=AdminRole.SUPER_ADMIN, admin_id=7)
        lot = await _seed_lot(lots, status=PrizeLotStatus.CLAIMED)
        assert lot.id is not None

        with pytest.raises(PrizeLotStatusTransitionError) as excinfo:
            await uc.execute(
                RefundLotInput(
                    actor_tg_id=99,
                    lot_id=lot.id,
                    reason="trying to refund a paid lot",
                ),
            )
        assert excinfo.value.from_status is PrizeLotStatus.CLAIMED
        assert excinfo.value.to_status is PrizeLotStatus.REFUNDED

        # nothing committed
        assert pool.calls == []
        assert audit.entries == []
        assert admin_audit.entries == []
