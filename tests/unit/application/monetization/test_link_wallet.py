"""Тесты use-case ``LinkWallet`` (Спринт 4.1-D, ГДД §12.6.4 + Спринт 4.1-F)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.monetization.link_wallet import (
    LinkWallet,
    LinkWalletCommand,
)
from pipirik_wars.domain.monetization import (
    Currency,
    TonProofReplayedError,
    Wallet,
    WalletAlreadyLinkedError,
)
from tests.fakes.audit import FakeAuditLogger
from tests.fakes.clock import FakeClock
from tests.fakes.nonce_store import FakeNonceStore

_NOW = datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC)
_VALID_ADDR = "0:" + "a1" * 32
_OTHER_ADDR = "0:" + "b2" * 32
_SCOPE_TON = f"link_wallet:42:{Currency.TON_NANO.value}"
_SCOPE_USDT = f"link_wallet:42:{Currency.USDT_DECIMAL.value}"
_NONCE = "test-nonce-32-chars-aaaaaaaaaaaaa"
_NONCE_OTHER = "test-nonce-32-chars-bbbbbbbbbbbbb"


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


def _build_use_case(
    *,
    wallet_repo: FakeWalletRepository | None = None,
    verifier_valid: bool = True,
    nonce_store: FakeNonceStore | None = None,
    clock_now: datetime = _NOW,
) -> tuple[LinkWallet, FakeWalletRepository, FakeAuditLogger, FakeNonceStore]:
    """DI-factory для теста."""
    wallet_repo = wallet_repo if wallet_repo is not None else FakeWalletRepository()
    nonce_store = nonce_store if nonce_store is not None else FakeNonceStore()
    audit = FakeAuditLogger()
    uc = LinkWallet(
        wallet_repository=wallet_repo,
        ton_connect_verifier=FakeTonConnectVerifier(valid=verifier_valid),
        nonce_store=nonce_store,
        audit_logger=audit,
        clock=FakeClock(clock_now),
    )
    return uc, wallet_repo, audit, nonce_store


class TestLinkWalletHappyPath:
    """First-time link."""

    @pytest.mark.asyncio()
    async def test_first_link(self) -> None:
        nonce_store = FakeNonceStore()
        await nonce_store.issue_nonce(
            scope=_SCOPE_TON,
            nonce=_NONCE,
            expires_at=_NOW + timedelta(minutes=5),
        )

        uc, _, audit, _ = _build_use_case(nonce_store=nonce_store)
        result = await uc.execute(
            LinkWalletCommand(
                player_id=42,
                address=_VALID_ADDR,
                currency=Currency.TON_NANO,
                proof="test_proof",
                scope=_SCOPE_TON,
                nonce=_NONCE,
            )
        )

        assert result.replaced is False
        assert result.wallet.player_id == 42
        assert result.wallet.address == _VALID_ADDR
        assert result.wallet.currency is Currency.TON_NANO

        assert len(audit.entries) == 1
        assert audit.entries[0].source.value == "wallet_linked"
        assert audit.entries[0].before is None
        assert nonce_store.is_consumed(scope=_SCOPE_TON, nonce=_NONCE)

    @pytest.mark.asyncio()
    async def test_replace_existing_address(self) -> None:
        wallet_repo = FakeWalletRepository()
        wallet_repo._storage[(42, Currency.TON_NANO)] = Wallet(
            player_id=42,
            address=_VALID_ADDR,
            currency=Currency.TON_NANO,
            linked_at=_NOW,
        )
        nonce_store = FakeNonceStore()
        await nonce_store.issue_nonce(
            scope=_SCOPE_TON,
            nonce=_NONCE,
            expires_at=_NOW + timedelta(minutes=5),
        )

        uc, _, audit, _ = _build_use_case(wallet_repo=wallet_repo, nonce_store=nonce_store)
        result = await uc.execute(
            LinkWalletCommand(
                player_id=42,
                address=_OTHER_ADDR,
                currency=Currency.TON_NANO,
                proof="test_proof",
                scope=_SCOPE_TON,
                nonce=_NONCE,
            )
        )

        assert result.replaced is True
        assert result.wallet.address == _OTHER_ADDR
        assert audit.entries[0].before is not None
        assert nonce_store.is_consumed(scope=_SCOPE_TON, nonce=_NONCE)


class TestLinkWalletErrors:
    """Error paths."""

    @pytest.mark.asyncio()
    async def test_proof_verification_fails(self) -> None:
        nonce_store = FakeNonceStore()
        await nonce_store.issue_nonce(
            scope=_SCOPE_TON,
            nonce=_NONCE,
            expires_at=_NOW + timedelta(minutes=5),
        )

        uc, _, _, _ = _build_use_case(verifier_valid=False, nonce_store=nonce_store)
        with pytest.raises(ValueError, match="proof verification failed"):
            await uc.execute(
                LinkWalletCommand(
                    player_id=42,
                    address=_VALID_ADDR,
                    currency=Currency.TON_NANO,
                    proof="bad_proof",
                    scope=_SCOPE_TON,
                    nonce=_NONCE,
                )
            )
        # Nonce НЕ должен быть consumed при провале verify (early-exit
        # до consume_nonce — это инвариант контракта).
        assert not nonce_store.is_consumed(scope=_SCOPE_TON, nonce=_NONCE)
        assert nonce_store.consume_calls == []

    @pytest.mark.asyncio()
    async def test_same_address_already_linked(self) -> None:
        wallet_repo = FakeWalletRepository()
        wallet_repo._storage[(42, Currency.TON_NANO)] = Wallet(
            player_id=42,
            address=_VALID_ADDR,
            currency=Currency.TON_NANO,
            linked_at=_NOW,
        )
        nonce_store = FakeNonceStore()
        await nonce_store.issue_nonce(
            scope=_SCOPE_TON,
            nonce=_NONCE,
            expires_at=_NOW + timedelta(minutes=5),
        )

        uc, _, _, _ = _build_use_case(wallet_repo=wallet_repo, nonce_store=nonce_store)
        with pytest.raises(WalletAlreadyLinkedError):
            await uc.execute(
                LinkWalletCommand(
                    player_id=42,
                    address=_VALID_ADDR,
                    currency=Currency.TON_NANO,
                    proof="proof",
                    scope=_SCOPE_TON,
                    nonce=_NONCE,
                )
            )


class TestLinkWalletNonceReplay:
    """F.4.b — anti-replay через ``INonceStore.consume_nonce``."""

    @pytest.mark.asyncio()
    async def test_unknown_nonce_raises_replayed(self) -> None:
        """Nonce, который никогда не был выдан → ``TonProofReplayedError``."""
        nonce_store = FakeNonceStore()
        # Никакого issue_nonce — store пуст.

        uc, _, audit, _ = _build_use_case(nonce_store=nonce_store)
        with pytest.raises(TonProofReplayedError) as exc_info:
            await uc.execute(
                LinkWalletCommand(
                    player_id=42,
                    address=_VALID_ADDR,
                    currency=Currency.TON_NANO,
                    proof="proof",
                    scope=_SCOPE_TON,
                    nonce=_NONCE,
                )
            )
        assert exc_info.value.scope == _SCOPE_TON
        # Wallet НЕ должен быть привязан, audit пустой.
        assert audit.entries == []

    @pytest.mark.asyncio()
    async def test_already_consumed_nonce_raises_replayed(self) -> None:
        """Второй вызов с тем же ``(scope, nonce)`` → ``TonProofReplayedError``."""
        nonce_store = FakeNonceStore()
        await nonce_store.issue_nonce(
            scope=_SCOPE_TON,
            nonce=_NONCE,
            expires_at=_NOW + timedelta(minutes=5),
        )

        uc, _, audit, _ = _build_use_case(nonce_store=nonce_store)
        # Первый вызов — успешный consume + link.
        await uc.execute(
            LinkWalletCommand(
                player_id=42,
                address=_VALID_ADDR,
                currency=Currency.TON_NANO,
                proof="proof",
                scope=_SCOPE_TON,
                nonce=_NONCE,
            )
        )

        # Второй вызов с тем же nonce — replay.
        with pytest.raises(TonProofReplayedError) as exc_info:
            await uc.execute(
                LinkWalletCommand(
                    player_id=42,
                    address=_OTHER_ADDR,
                    currency=Currency.TON_NANO,
                    proof="proof",
                    scope=_SCOPE_TON,
                    nonce=_NONCE,
                )
            )
        assert exc_info.value.scope == _SCOPE_TON
        # Audit — только одна запись (от первого успешного вызова).
        assert len(audit.entries) == 1

    @pytest.mark.asyncio()
    async def test_expired_nonce_raises_replayed(self) -> None:
        """Nonce, у которого ``expires_at <= now``, → ``TonProofReplayedError``."""
        nonce_store = FakeNonceStore()
        # Nonce истёк ровно в момент _NOW (граница `expires_at <= now`
        # — см. контракт ``INonceStore.consume_nonce``).
        await nonce_store.issue_nonce(
            scope=_SCOPE_TON,
            nonce=_NONCE,
            expires_at=_NOW - timedelta(seconds=1),
        )

        uc, _, _, _ = _build_use_case(nonce_store=nonce_store)
        with pytest.raises(TonProofReplayedError) as exc_info:
            await uc.execute(
                LinkWalletCommand(
                    player_id=42,
                    address=_VALID_ADDR,
                    currency=Currency.TON_NANO,
                    proof="proof",
                    scope=_SCOPE_TON,
                    nonce=_NONCE,
                )
            )
        assert exc_info.value.scope == _SCOPE_TON

    @pytest.mark.asyncio()
    async def test_wrong_scope_raises_replayed(self) -> None:
        """Nonce, выданный под другим scope-ом, → ``TonProofReplayedError``."""
        nonce_store = FakeNonceStore()
        # Выдан под USDT-scope, но команда приходит с TON-scope-ом.
        await nonce_store.issue_nonce(
            scope=_SCOPE_USDT,
            nonce=_NONCE,
            expires_at=_NOW + timedelta(minutes=5),
        )

        uc, _, _, _ = _build_use_case(nonce_store=nonce_store)
        with pytest.raises(TonProofReplayedError) as exc_info:
            await uc.execute(
                LinkWalletCommand(
                    player_id=42,
                    address=_VALID_ADDR,
                    currency=Currency.TON_NANO,
                    proof="proof",
                    scope=_SCOPE_TON,
                    nonce=_NONCE,
                )
            )
        assert exc_info.value.scope == _SCOPE_TON

    @pytest.mark.asyncio()
    async def test_consume_called_with_clock_now_after_verify(self) -> None:
        """``consume_nonce`` зовётся с ``now=clock.now()`` и **после** ``verify``."""
        nonce_store = FakeNonceStore()
        await nonce_store.issue_nonce(
            scope=_SCOPE_TON,
            nonce=_NONCE,
            expires_at=_NOW + timedelta(minutes=5),
        )

        uc, _, _, _ = _build_use_case(nonce_store=nonce_store)
        await uc.execute(
            LinkWalletCommand(
                player_id=42,
                address=_VALID_ADDR,
                currency=Currency.TON_NANO,
                proof="proof",
                scope=_SCOPE_TON,
                nonce=_NONCE,
            )
        )
        assert len(nonce_store.consume_calls) == 1
        call = nonce_store.consume_calls[0]
        assert call["scope"] == _SCOPE_TON
        assert call["nonce"] == _NONCE
        assert call["now"] == _NOW

    @pytest.mark.asyncio()
    async def test_different_nonce_same_scope_ok(self) -> None:
        """Два разных nonce-а под одним scope — оба consume-ятся независимо."""
        nonce_store = FakeNonceStore()
        await nonce_store.issue_nonce(
            scope=_SCOPE_TON,
            nonce=_NONCE,
            expires_at=_NOW + timedelta(minutes=5),
        )
        await nonce_store.issue_nonce(
            scope=_SCOPE_TON,
            nonce=_NONCE_OTHER,
            expires_at=_NOW + timedelta(minutes=5),
        )

        uc, _, audit, _ = _build_use_case(nonce_store=nonce_store)
        await uc.execute(
            LinkWalletCommand(
                player_id=42,
                address=_VALID_ADDR,
                currency=Currency.TON_NANO,
                proof="proof",
                scope=_SCOPE_TON,
                nonce=_NONCE,
            )
        )
        await uc.execute(
            LinkWalletCommand(
                player_id=42,
                address=_OTHER_ADDR,
                currency=Currency.TON_NANO,
                proof="proof",
                scope=_SCOPE_TON,
                nonce=_NONCE_OTHER,
            )
        )
        assert len(audit.entries) == 2
        assert nonce_store.is_consumed(scope=_SCOPE_TON, nonce=_NONCE)
        assert nonce_store.is_consumed(scope=_SCOPE_TON, nonce=_NONCE_OTHER)
