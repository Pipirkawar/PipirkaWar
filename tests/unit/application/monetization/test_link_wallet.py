"""Тесты use-case ``LinkWallet`` (Спринт 4.1-D, ГДД §12.6.4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.monetization.link_wallet import (
    LinkWallet,
    LinkWalletCommand,
)
from pipirik_wars.domain.monetization import (
    Currency,
    Wallet,
    WalletAlreadyLinkedError,
)
from tests.fakes.audit import FakeAuditLogger
from tests.fakes.clock import FakeClock

_NOW = datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC)
_VALID_ADDR = "0:" + "a1" * 32
_OTHER_ADDR = "0:" + "b2" * 32


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
class FakeTonConnectVerifier:
    """In-memory ``ITonConnectVerifier``."""

    valid: bool = True

    async def verify(self, *, address: str, proof: str) -> bool:
        return self.valid


class TestLinkWalletHappyPath:
    """First-time link."""

    @pytest.mark.asyncio()
    async def test_first_link(self) -> None:
        wallet_repo = FakeWalletRepository()
        verifier = FakeTonConnectVerifier(valid=True)
        audit = FakeAuditLogger()
        clock = FakeClock(_NOW)

        uc = LinkWallet(
            wallet_repository=wallet_repo,
            ton_connect_verifier=verifier,
            audit_logger=audit,
            clock=clock,
        )
        result = await uc.execute(
            LinkWalletCommand(
                player_id=42,
                address=_VALID_ADDR,
                currency=Currency.TON_NANO,
                proof="test_proof",
            )
        )

        assert result.replaced is False
        assert result.wallet.player_id == 42
        assert result.wallet.address == _VALID_ADDR
        assert result.wallet.currency is Currency.TON_NANO

        assert len(audit.entries) == 1
        assert audit.entries[0].source.value == "wallet_linked"
        assert audit.entries[0].before is None

    @pytest.mark.asyncio()
    async def test_replace_existing_address(self) -> None:
        wallet_repo = FakeWalletRepository()
        wallet_repo._storage[(42, Currency.TON_NANO)] = Wallet(
            player_id=42,
            address=_VALID_ADDR,
            currency=Currency.TON_NANO,
            linked_at=_NOW,
        )
        verifier = FakeTonConnectVerifier(valid=True)
        audit = FakeAuditLogger()
        clock = FakeClock(_NOW)

        uc = LinkWallet(
            wallet_repository=wallet_repo,
            ton_connect_verifier=verifier,
            audit_logger=audit,
            clock=clock,
        )
        result = await uc.execute(
            LinkWalletCommand(
                player_id=42,
                address=_OTHER_ADDR,
                currency=Currency.TON_NANO,
                proof="test_proof",
            )
        )

        assert result.replaced is True
        assert result.wallet.address == _OTHER_ADDR
        assert audit.entries[0].before is not None


class TestLinkWalletErrors:
    """Error paths."""

    @pytest.mark.asyncio()
    async def test_proof_verification_fails(self) -> None:
        wallet_repo = FakeWalletRepository()
        verifier = FakeTonConnectVerifier(valid=False)
        audit = FakeAuditLogger()
        clock = FakeClock(_NOW)

        uc = LinkWallet(
            wallet_repository=wallet_repo,
            ton_connect_verifier=verifier,
            audit_logger=audit,
            clock=clock,
        )
        with pytest.raises(ValueError, match="proof verification failed"):
            await uc.execute(
                LinkWalletCommand(
                    player_id=42,
                    address=_VALID_ADDR,
                    currency=Currency.TON_NANO,
                    proof="bad_proof",
                )
            )

    @pytest.mark.asyncio()
    async def test_same_address_already_linked(self) -> None:
        wallet_repo = FakeWalletRepository()
        wallet_repo._storage[(42, Currency.TON_NANO)] = Wallet(
            player_id=42,
            address=_VALID_ADDR,
            currency=Currency.TON_NANO,
            linked_at=_NOW,
        )
        verifier = FakeTonConnectVerifier(valid=True)
        audit = FakeAuditLogger()
        clock = FakeClock(_NOW)

        uc = LinkWallet(
            wallet_repository=wallet_repo,
            ton_connect_verifier=verifier,
            audit_logger=audit,
            clock=clock,
        )
        with pytest.raises(WalletAlreadyLinkedError):
            await uc.execute(
                LinkWalletCommand(
                    player_id=42,
                    address=_VALID_ADDR,
                    currency=Currency.TON_NANO,
                    proof="proof",
                )
            )
