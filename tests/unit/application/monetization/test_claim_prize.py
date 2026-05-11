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
    Currency,
    FeeBufferAmount,
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
    def use_case(
        self,
        lot_repo: FakePrizeLotRepository,
        wallet_repo: FakeWalletRepository,
        payout_adapter: FakePayoutAdapter,
        pool_repo: FakePrizePoolRepository,
        audit: FakeAuditLogger,
        clock: FakeClock,
    ) -> ClaimPrize:
        return ClaimPrize(
            prize_lot_repository=lot_repo,
            prize_pool_repository=pool_repo,
            wallet_repository=wallet_repo,
            payout_adapter=payout_adapter,
            audit_logger=audit,
            clock=clock,
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
        )
        with pytest.raises(ValueError, match="anti-fraud"):
            await uc.execute(
                ClaimPrizeCommand(
                    player_id=42,
                    lot_id=1,
                    recipient_address="0:" + "bb" * 32,
                )
            )
