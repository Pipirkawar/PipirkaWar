"""Тесты use-case ``ClaimPrize`` (Спринт 4.1-D, ГДД §12.6.4).

Покрывают:
* happy-path: ``RESERVED → CLAIMED`` при ``actual_fee <= fee_buffer``;
* fee-overflow: ``RESERVED → REFUNDED`` + ``pool.apply_increment`` при
  ``actual_fee > fee_buffer``;
* error-paths: лот не найден, лот не RESERVED, кошелёк не привязан,
  anti-fraud address mismatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.monetization.claim_prize import (
    ClaimPrize,
    ClaimPrizeCommand,
)
from pipirik_wars.domain.monetization import (
    ClaimPrizeOverLimitError,
    ClaimPrizePayoutsFrozenError,
    Currency,
    FeeBufferAmount,
    PayoutLimitOverLimit,
    PrizeLot,
    PrizeLotNotFoundError,
    PrizeLotStatus,
    PrizeLotStatusTransitionError,
    Wallet,
    WalletNotLinkedError,
)
from pipirik_wars.domain.monetization.ports import PayoutResult
from tests.fakes.audit import FakeAuditLogger
from tests.fakes.clock import FakeClock
from tests.fakes.payout_freeze_repo import FakePayoutFreezeRepository
from tests.fakes.payout_limit_checker import FakePayoutLimitChecker
from tests.fakes.prize_lot_repo import FakePrizeLotRepository
from tests.fakes.prize_pool_repo import FakePrizePoolRepository

_NOW = datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC)
_VALID_ADDR = "0:" + "a1" * 32


@dataclass
class FakeWalletRepository:
    """In-memory ``IWalletRepository``."""

    _storage: dict[tuple[int, Currency], Wallet]

    def __init__(self) -> None:
        self._storage = {}

    async def add_or_replace(self, *, wallet: Wallet) -> Wallet:
        self._storage[(wallet.player_id, wallet.currency)] = wallet
        return wallet

    async def get_by_player_and_currency(
        self,
        *,
        player_id: int,
        currency: Currency,
    ) -> Wallet | None:
        return self._storage.get((player_id, currency))


@dataclass
class FakePayoutAdapter:
    """In-memory ``ITonPayoutAdapter``."""

    result: PayoutResult

    async def payout(
        self,
        *,
        currency: Currency,
        amount_native: int,
        recipient_address: str,
    ) -> PayoutResult:
        return self.result


def _make_reserved_lot(
    *,
    lot_id: int = 1,
    currency: Currency = Currency.TON_NANO,
    amount_native: int = 1_000_000_000,
    fee_buffer: int = 5_000_000,
) -> PrizeLot:
    return PrizeLot(
        id=lot_id,
        currency=currency,
        amount_native=amount_native,
        fee_buffer_native=FeeBufferAmount(fee_buffer),
        status=PrizeLotStatus.RESERVED,
        created_at=_NOW,
        reserved_at=_NOW,
        claimed_at=None,
    )


def _make_wallet(
    *,
    player_id: int = 42,
    currency: Currency = Currency.TON_NANO,
    address: str = _VALID_ADDR,
) -> Wallet:
    return Wallet(
        player_id=player_id,
        address=address,
        currency=currency,
        linked_at=_NOW,
    )


class TestClaimPrizeHappyPath:
    """``actual_fee <= fee_buffer`` → ``CLAIMED``."""

    @pytest.fixture()
    def lot_repo(self) -> FakePrizeLotRepository:
        repo = FakePrizeLotRepository()
        lot = _make_reserved_lot()
        repo._storage[1] = lot
        return repo

    @pytest.fixture()
    def wallet_repo(self) -> FakeWalletRepository:
        repo = FakeWalletRepository()
        repo._storage[(42, Currency.TON_NANO)] = _make_wallet()
        return repo

    @pytest.fixture()
    def payout_adapter(self) -> FakePayoutAdapter:
        return FakePayoutAdapter(
            result=PayoutResult(tx_hash="abc123", actual_fee_native=3_000_000),
        )

    @pytest.fixture()
    def audit(self) -> FakeAuditLogger:
        return FakeAuditLogger()

    @pytest.fixture()
    def clock(self) -> FakeClock:
        return FakeClock(_NOW)

    @pytest.fixture()
    def pool_repo(self) -> FakePrizePoolRepository:
        return FakePrizePoolRepository()

    @pytest.fixture()
    def freeze_repo(self) -> FakePayoutFreezeRepository:
        return FakePayoutFreezeRepository()

    @pytest.fixture()
    def limit_checker(self) -> FakePayoutLimitChecker:
        return FakePayoutLimitChecker()

    @pytest.fixture()
    def use_case(
        self,
        lot_repo: FakePrizeLotRepository,
        wallet_repo: FakeWalletRepository,
        payout_adapter: FakePayoutAdapter,
        pool_repo: FakePrizePoolRepository,
        audit: FakeAuditLogger,
        clock: FakeClock,
        freeze_repo: FakePayoutFreezeRepository,
        limit_checker: FakePayoutLimitChecker,
    ) -> ClaimPrize:
        return ClaimPrize(
            prize_lot_repository=lot_repo,
            prize_pool_repository=pool_repo,
            wallet_repository=wallet_repo,
            payout_adapter=payout_adapter,
            audit_logger=audit,
            clock=clock,
            payout_freeze_repository=freeze_repo,
            payout_limit_checker=limit_checker,
        )

    @pytest.mark.asyncio()
    async def test_happy_path_claimed(
        self,
        use_case: ClaimPrize,
        lot_repo: FakePrizeLotRepository,
        audit: FakeAuditLogger,
    ) -> None:
        cmd = ClaimPrizeCommand(
            player_id=42,
            lot_id=1,
            recipient_address=_VALID_ADDR,
        )
        result = await use_case.execute(cmd)

        assert result.claimed is True
        assert result.refunded is False
        assert result.payout is not None
        assert result.payout.tx_hash == "abc123"
        assert result.lot_id == 1

        stored = lot_repo._storage[1]
        assert stored.status is PrizeLotStatus.CLAIMED

        assert len(audit.entries) == 1
        assert audit.entries[0].source.value == "prize_lot_claimed"


class TestClaimPrizeFeeOverflow:
    """``actual_fee > fee_buffer`` → ``REFUNDED`` + pool increment."""

    @pytest.mark.asyncio()
    async def test_fee_overflow_refunds_to_pool(self) -> None:
        lot = _make_reserved_lot(fee_buffer=5_000_000)
        lot_repo = FakePrizeLotRepository()
        lot_repo._storage[1] = lot

        wallet_repo = FakeWalletRepository()
        wallet_repo._storage[(42, Currency.TON_NANO)] = _make_wallet()

        payout_adapter = FakePayoutAdapter(
            result=PayoutResult(tx_hash="xyz", actual_fee_native=10_000_000),
        )
        pool_repo = FakePrizePoolRepository()
        audit = FakeAuditLogger()
        clock = FakeClock(_NOW)

        uc = ClaimPrize(
            prize_lot_repository=lot_repo,
            prize_pool_repository=pool_repo,
            wallet_repository=wallet_repo,
            payout_adapter=payout_adapter,
            audit_logger=audit,
            clock=clock,
            payout_freeze_repository=FakePayoutFreezeRepository(),
            payout_limit_checker=FakePayoutLimitChecker(),
        )
        result = await uc.execute(
            ClaimPrizeCommand(
                player_id=42,
                lot_id=1,
                recipient_address=_VALID_ADDR,
            )
        )

        assert result.claimed is False
        assert result.refunded is True
        assert result.payout is None

        stored = lot_repo._storage[1]
        assert stored.status is PrizeLotStatus.REFUNDED

        assert len(pool_repo.calls) == 1
        call = pool_repo.calls[0]
        assert call.currency is Currency.TON_NANO
        assert call.amount_native == lot.amount_native

        assert len(audit.entries) == 1
        assert audit.entries[0].source.value == "prize_lot_refunded"


class TestClaimPrizeErrors:
    """Error paths."""

    @pytest.mark.asyncio()
    async def test_lot_not_found(self) -> None:
        lot_repo = FakePrizeLotRepository()
        wallet_repo = FakeWalletRepository()
        payout = FakePayoutAdapter(result=PayoutResult(tx_hash="", actual_fee_native=0))
        pool = FakePrizePoolRepository()
        audit = FakeAuditLogger()
        clock = FakeClock(_NOW)

        uc = ClaimPrize(
            prize_lot_repository=lot_repo,
            prize_pool_repository=pool,
            wallet_repository=wallet_repo,
            payout_adapter=payout,
            audit_logger=audit,
            clock=clock,
            payout_freeze_repository=FakePayoutFreezeRepository(),
            payout_limit_checker=FakePayoutLimitChecker(),
        )
        with pytest.raises(PrizeLotNotFoundError):
            await uc.execute(
                ClaimPrizeCommand(player_id=42, lot_id=999, recipient_address=_VALID_ADDR)
            )

    @pytest.mark.asyncio()
    async def test_lot_not_reserved(self) -> None:
        lot_repo = FakePrizeLotRepository()
        active_lot = PrizeLot(
            id=1,
            currency=Currency.TON_NANO,
            amount_native=1_000_000_000,
            fee_buffer_native=FeeBufferAmount(5_000_000),
            status=PrizeLotStatus.ACTIVE,
            created_at=_NOW,
        )
        lot_repo._storage[1] = active_lot

        wallet_repo = FakeWalletRepository()
        payout = FakePayoutAdapter(result=PayoutResult(tx_hash="", actual_fee_native=0))
        pool = FakePrizePoolRepository()
        audit = FakeAuditLogger()
        clock = FakeClock(_NOW)

        uc = ClaimPrize(
            prize_lot_repository=lot_repo,
            prize_pool_repository=pool,
            wallet_repository=wallet_repo,
            payout_adapter=payout,
            audit_logger=audit,
            clock=clock,
            payout_freeze_repository=FakePayoutFreezeRepository(),
            payout_limit_checker=FakePayoutLimitChecker(),
        )
        with pytest.raises(PrizeLotStatusTransitionError):
            await uc.execute(
                ClaimPrizeCommand(player_id=42, lot_id=1, recipient_address=_VALID_ADDR)
            )

    @pytest.mark.asyncio()
    async def test_wallet_not_linked(self) -> None:
        lot_repo = FakePrizeLotRepository()
        lot_repo._storage[1] = _make_reserved_lot()

        wallet_repo = FakeWalletRepository()
        payout = FakePayoutAdapter(result=PayoutResult(tx_hash="", actual_fee_native=0))
        pool = FakePrizePoolRepository()
        audit = FakeAuditLogger()
        clock = FakeClock(_NOW)

        uc = ClaimPrize(
            prize_lot_repository=lot_repo,
            prize_pool_repository=pool,
            wallet_repository=wallet_repo,
            payout_adapter=payout,
            audit_logger=audit,
            clock=clock,
            payout_freeze_repository=FakePayoutFreezeRepository(),
            payout_limit_checker=FakePayoutLimitChecker(),
        )
        with pytest.raises(WalletNotLinkedError):
            await uc.execute(
                ClaimPrizeCommand(player_id=42, lot_id=1, recipient_address=_VALID_ADDR)
            )

    @pytest.mark.asyncio()
    async def test_address_mismatch(self) -> None:
        lot_repo = FakePrizeLotRepository()
        lot_repo._storage[1] = _make_reserved_lot()

        wallet_repo = FakeWalletRepository()
        wallet_repo._storage[(42, Currency.TON_NANO)] = _make_wallet()

        payout = FakePayoutAdapter(result=PayoutResult(tx_hash="", actual_fee_native=0))
        pool = FakePrizePoolRepository()
        audit = FakeAuditLogger()
        clock = FakeClock(_NOW)

        uc = ClaimPrize(
            prize_lot_repository=lot_repo,
            prize_pool_repository=pool,
            wallet_repository=wallet_repo,
            payout_adapter=payout,
            audit_logger=audit,
            clock=clock,
            payout_freeze_repository=FakePayoutFreezeRepository(),
            payout_limit_checker=FakePayoutLimitChecker(),
        )
        with pytest.raises(ValueError, match="anti-fraud"):
            await uc.execute(
                ClaimPrizeCommand(
                    player_id=42,
                    lot_id=1,
                    recipient_address="0:" + "bb" * 32,
                )
            )


def _build_use_case(
    *,
    lot_repo: FakePrizeLotRepository,
    wallet_repo: FakeWalletRepository,
    freeze_repo: FakePayoutFreezeRepository | None = None,
    limit_checker: FakePayoutLimitChecker | None = None,
    payout_adapter: FakePayoutAdapter | None = None,
    pool_repo: FakePrizePoolRepository | None = None,
    audit: FakeAuditLogger | None = None,
) -> tuple[
    ClaimPrize,
    FakePayoutFreezeRepository,
    FakePayoutLimitChecker,
    FakeAuditLogger,
    FakePayoutAdapter,
]:
    freeze_repo = freeze_repo if freeze_repo is not None else FakePayoutFreezeRepository()
    limit_checker = limit_checker if limit_checker is not None else FakePayoutLimitChecker()
    payout_adapter = (
        payout_adapter
        if payout_adapter is not None
        else FakePayoutAdapter(
            result=PayoutResult(tx_hash="ok", actual_fee_native=1_000_000),
        )
    )
    pool_repo = pool_repo if pool_repo is not None else FakePrizePoolRepository()
    audit = audit if audit is not None else FakeAuditLogger()
    uc = ClaimPrize(
        prize_lot_repository=lot_repo,
        prize_pool_repository=pool_repo,
        wallet_repository=wallet_repo,
        payout_adapter=payout_adapter,
        audit_logger=audit,
        clock=FakeClock(_NOW),
        payout_freeze_repository=freeze_repo,
        payout_limit_checker=limit_checker,
    )
    return uc, freeze_repo, limit_checker, audit, payout_adapter


class TestClaimPrizeFreezeCheck:
    """E.10: freeze-check перед попыткой выплаты."""

    @pytest.mark.asyncio()
    async def test_frozen_raises_before_payout(self) -> None:
        """При is_frozen=True — ClaimPrizePayoutsFrozenError, payout не вызывается."""
        lot_repo = FakePrizeLotRepository()
        lot_repo._storage[1] = _make_reserved_lot()
        wallet_repo = FakeWalletRepository()
        wallet_repo._storage[(42, Currency.TON_NANO)] = _make_wallet()

        freeze_repo = FakePayoutFreezeRepository()
        await freeze_repo.set_frozen(
            admin_id=7,
            at=_NOW,
            reason="suspicious activity detected",
        )

        uc, _, limit_checker, audit, _ = _build_use_case(
            lot_repo=lot_repo,
            wallet_repo=wallet_repo,
            freeze_repo=freeze_repo,
        )

        with pytest.raises(ClaimPrizePayoutsFrozenError) as exc_info:
            await uc.execute(
                ClaimPrizeCommand(
                    player_id=42,
                    lot_id=1,
                    recipient_address=_VALID_ADDR,
                ),
            )

        assert exc_info.value.lot_id == 1
        assert exc_info.value.reason == "suspicious activity detected"
        assert lot_repo._storage[1].status is PrizeLotStatus.RESERVED
        assert len(audit.entries) == 0
        assert len(limit_checker.calls) == 0

    @pytest.mark.asyncio()
    async def test_unfrozen_proceeds_to_payout(self) -> None:
        """is_frozen=False (дефолт) — нормальный flow, claimed."""
        lot_repo = FakePrizeLotRepository()
        lot_repo._storage[1] = _make_reserved_lot()
        wallet_repo = FakeWalletRepository()
        wallet_repo._storage[(42, Currency.TON_NANO)] = _make_wallet()

        uc, freeze_repo, _, _, _ = _build_use_case(
            lot_repo=lot_repo,
            wallet_repo=wallet_repo,
        )

        result = await uc.execute(
            ClaimPrizeCommand(
                player_id=42,
                lot_id=1,
                recipient_address=_VALID_ADDR,
            ),
        )

        assert result.claimed is True
        assert freeze_repo.get_state_calls == 1


class TestClaimPrizeOverLimitCheck:
    """E.10: payout-limit-check перед попыткой выплаты."""

    @pytest.mark.asyncio()
    async def test_over_limit_raises_before_payout(self) -> None:
        """OverLimit → ClaimPrizeOverLimitError, payout не вызывается."""
        lot_repo = FakePrizeLotRepository()
        lot_repo._storage[1] = _make_reserved_lot()
        wallet_repo = FakeWalletRepository()
        wallet_repo._storage[(42, Currency.TON_NANO)] = _make_wallet()

        retry_after = datetime(2026, 6, 11, tzinfo=UTC)
        limit_checker = FakePayoutLimitChecker(
            per_key={
                (42, Currency.TON_NANO): PayoutLimitOverLimit(
                    retry_after=retry_after,
                    exceeded_by_native=5_000_000,
                ),
            },
        )

        uc, _, _, audit, payout_adapter = _build_use_case(
            lot_repo=lot_repo,
            wallet_repo=wallet_repo,
            limit_checker=limit_checker,
        )

        with pytest.raises(ClaimPrizeOverLimitError) as exc_info:
            await uc.execute(
                ClaimPrizeCommand(
                    player_id=42,
                    lot_id=1,
                    recipient_address=_VALID_ADDR,
                ),
            )

        assert exc_info.value.lot_id == 1
        assert exc_info.value.player_id == 42
        assert exc_info.value.retry_after == retry_after
        assert exc_info.value.exceeded_by_native == 5_000_000
        assert lot_repo._storage[1].status is PrizeLotStatus.RESERVED
        assert len(audit.entries) == 0

    @pytest.mark.asyncio()
    async def test_within_limit_proceeds_to_payout(self) -> None:
        """Within (дефолт) — нормальный flow, claimed."""
        lot_repo = FakePrizeLotRepository()
        lot_repo._storage[1] = _make_reserved_lot()
        wallet_repo = FakeWalletRepository()
        wallet_repo._storage[(42, Currency.TON_NANO)] = _make_wallet()

        uc, _, limit_checker, _, _ = _build_use_case(
            lot_repo=lot_repo,
            wallet_repo=wallet_repo,
        )

        result = await uc.execute(
            ClaimPrizeCommand(
                player_id=42,
                lot_id=1,
                recipient_address=_VALID_ADDR,
            ),
        )

        assert result.claimed is True
        assert len(limit_checker.calls) == 1
        call = limit_checker.calls[0]
        assert call.player_id == 42
        assert call.currency is Currency.TON_NANO
        assert call.amount_native == 1_000_000_000


class TestClaimPrizeCheckOrder:
    """E.10: freeze-check ДО payout-limit-check (frozen wins)."""

    @pytest.mark.asyncio()
    async def test_frozen_takes_precedence_over_over_limit(self) -> None:
        """Если frozen — limit-checker не вызывается."""
        lot_repo = FakePrizeLotRepository()
        lot_repo._storage[1] = _make_reserved_lot()
        wallet_repo = FakeWalletRepository()
        wallet_repo._storage[(42, Currency.TON_NANO)] = _make_wallet()

        freeze_repo = FakePayoutFreezeRepository()
        await freeze_repo.set_frozen(
            admin_id=7,
            at=_NOW,
            reason="freeze",
        )

        retry_after = datetime(2026, 6, 11, tzinfo=UTC)
        limit_checker = FakePayoutLimitChecker(
            per_key={
                (42, Currency.TON_NANO): PayoutLimitOverLimit(
                    retry_after=retry_after,
                    exceeded_by_native=1,
                ),
            },
        )

        uc, _, _, _, _ = _build_use_case(
            lot_repo=lot_repo,
            wallet_repo=wallet_repo,
            freeze_repo=freeze_repo,
            limit_checker=limit_checker,
        )

        with pytest.raises(ClaimPrizePayoutsFrozenError):
            await uc.execute(
                ClaimPrizeCommand(
                    player_id=42,
                    lot_id=1,
                    recipient_address=_VALID_ADDR,
                ),
            )

        assert len(limit_checker.calls) == 0
