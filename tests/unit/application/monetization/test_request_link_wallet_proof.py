"""Тесты use-case ``RequestLinkWalletProof`` (Спринт 4.1-F, шаг F.4.a)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from pipirik_wars.application.monetization import (
    RequestLinkWalletProof,
    RequestLinkWalletProofCommand,
    RequestLinkWalletProofConfig,
)
from pipirik_wars.domain.monetization import Currency
from tests.fakes import FakeClock, FakeNonceStore

_NOW = datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC)
_VALID_ADDR = "0:" + "a1" * 32
_DOMAIN = "pipirik.example.com"


def _make_use_case(
    *,
    nonce_sequence: list[str] | None = None,
    ttl_seconds: int = 300,
    domain: str = _DOMAIN,
) -> tuple[RequestLinkWalletProof, FakeNonceStore, FakeClock]:
    nonces = iter(nonce_sequence) if nonce_sequence is not None else None

    def _gen() -> str:
        if nonces is not None:
            return next(nonces)
        # auto-counter, чтобы избежать ValueError на double-issue
        return f"nonce-{next(_AUTOCOUNTER)}"

    nonce_store = FakeNonceStore()
    clock = FakeClock(_NOW)
    uc = RequestLinkWalletProof(
        nonce_store=nonce_store,
        clock=clock,
        config=RequestLinkWalletProofConfig(
            canonical_domain=domain,
            nonce_ttl_seconds=ttl_seconds,
        ),
        nonce_generator=_gen,
    )
    return uc, nonce_store, clock


_AUTOCOUNTER = count(1)


class TestRequestLinkWalletProofHappyPath:
    @pytest.mark.asyncio()
    async def test_happy_path_ton_nano(self) -> None:
        uc, store, _ = _make_use_case(nonce_sequence=["abc123def456"])
        result = await uc.execute(
            RequestLinkWalletProofCommand(
                player_id=42,
                address=_VALID_ADDR,
                currency=Currency.TON_NANO,
            ),
        )
        assert result.nonce == "abc123def456"
        assert result.domain == _DOMAIN
        assert result.scope == "link_wallet:42:ton_nano"
        assert result.expires_at == _NOW + timedelta(seconds=300)
        # Записан в store
        assert store.is_known(scope="link_wallet:42:ton_nano", nonce="abc123def456")
        assert not store.is_consumed(
            scope="link_wallet:42:ton_nano",
            nonce="abc123def456",
        )

    @pytest.mark.asyncio()
    async def test_happy_path_usdt_decimal(self) -> None:
        uc, store, _ = _make_use_case(nonce_sequence=["xyz789"])
        result = await uc.execute(
            RequestLinkWalletProofCommand(
                player_id=99,
                address=_VALID_ADDR,
                currency=Currency.USDT_DECIMAL,
            ),
        )
        assert result.scope == "link_wallet:99:usdt_decimal"
        assert result.nonce == "xyz789"
        assert store.is_known(scope="link_wallet:99:usdt_decimal", nonce="xyz789")

    @pytest.mark.asyncio()
    async def test_custom_ttl_respected(self) -> None:
        uc, _, _ = _make_use_case(
            nonce_sequence=["n1"],
            ttl_seconds=600,
        )
        result = await uc.execute(
            RequestLinkWalletProofCommand(
                player_id=1,
                address=_VALID_ADDR,
                currency=Currency.TON_NANO,
            ),
        )
        assert result.expires_at == _NOW + timedelta(seconds=600)

    @pytest.mark.asyncio()
    async def test_two_calls_use_different_nonces(self) -> None:
        uc, store, _ = _make_use_case(nonce_sequence=["nonce-A", "nonce-B"])
        r1 = await uc.execute(
            RequestLinkWalletProofCommand(
                player_id=1,
                address=_VALID_ADDR,
                currency=Currency.TON_NANO,
            ),
        )
        r2 = await uc.execute(
            RequestLinkWalletProofCommand(
                player_id=2,
                address=_VALID_ADDR,
                currency=Currency.TON_NANO,
            ),
        )
        assert r1.nonce == "nonce-A"
        assert r2.nonce == "nonce-B"
        assert r1.scope != r2.scope
        assert store.is_known(scope="link_wallet:1:ton_nano", nonce="nonce-A")
        assert store.is_known(scope="link_wallet:2:ton_nano", nonce="nonce-B")


class TestRequestLinkWalletProofValidation:
    @pytest.mark.asyncio()
    async def test_player_id_zero_rejected(self) -> None:
        uc, _, _ = _make_use_case()
        with pytest.raises(ValueError, match="player_id must be > 0"):
            await uc.execute(
                RequestLinkWalletProofCommand(
                    player_id=0,
                    address=_VALID_ADDR,
                    currency=Currency.TON_NANO,
                ),
            )

    @pytest.mark.asyncio()
    async def test_player_id_negative_rejected(self) -> None:
        uc, _, _ = _make_use_case()
        with pytest.raises(ValueError, match="player_id must be > 0"):
            await uc.execute(
                RequestLinkWalletProofCommand(
                    player_id=-1,
                    address=_VALID_ADDR,
                    currency=Currency.TON_NANO,
                ),
            )

    @pytest.mark.asyncio()
    async def test_currency_stars_rejected(self) -> None:
        uc, _, _ = _make_use_case()
        with pytest.raises(ValueError, match="STARS not supported"):
            await uc.execute(
                RequestLinkWalletProofCommand(
                    player_id=42,
                    address=_VALID_ADDR,
                    currency=Currency.STARS,
                ),
            )

    @pytest.mark.asyncio()
    async def test_empty_address_rejected(self) -> None:
        uc, _, _ = _make_use_case()
        with pytest.raises(ValueError, match="address must be non-empty"):
            await uc.execute(
                RequestLinkWalletProofCommand(
                    player_id=42,
                    address="",
                    currency=Currency.TON_NANO,
                ),
            )


class TestRequestLinkWalletProofConfig:
    def test_default_ttl_300_seconds(self) -> None:
        cfg = RequestLinkWalletProofConfig(canonical_domain="d.example.com")
        assert cfg.nonce_ttl_seconds == 300

    def test_empty_domain_rejected(self) -> None:
        with pytest.raises(ValueError, match="canonical_domain"):
            RequestLinkWalletProofConfig(canonical_domain="")

    def test_non_str_domain_rejected(self) -> None:
        with pytest.raises(ValueError, match="canonical_domain"):
            RequestLinkWalletProofConfig(canonical_domain=42)  # type: ignore[arg-type]

    def test_zero_ttl_rejected(self) -> None:
        with pytest.raises(ValueError, match="nonce_ttl_seconds"):
            RequestLinkWalletProofConfig(
                canonical_domain="d.example.com",
                nonce_ttl_seconds=0,
            )

    def test_negative_ttl_rejected(self) -> None:
        with pytest.raises(ValueError, match="nonce_ttl_seconds"):
            RequestLinkWalletProofConfig(
                canonical_domain="d.example.com",
                nonce_ttl_seconds=-1,
            )

    def test_bool_ttl_rejected(self) -> None:
        # bool — подкласс int в Python, явно отвергаем
        with pytest.raises(ValueError, match="nonce_ttl_seconds"):
            RequestLinkWalletProofConfig(
                canonical_domain="d.example.com",
                nonce_ttl_seconds=True,
            )


class TestRequestLinkWalletProofDefaultNonceGenerator:
    @pytest.mark.asyncio()
    async def test_default_generator_produces_url_safe_string(self) -> None:
        # Без явного nonce_generator используется secrets.token_urlsafe(24).
        nonce_store = FakeNonceStore()
        clock = FakeClock(_NOW)
        uc = RequestLinkWalletProof(
            nonce_store=nonce_store,
            clock=clock,
            config=RequestLinkWalletProofConfig(canonical_domain=_DOMAIN),
        )
        result = await uc.execute(
            RequestLinkWalletProofCommand(
                player_id=42,
                address=_VALID_ADDR,
                currency=Currency.TON_NANO,
            ),
        )
        # secrets.token_urlsafe(24) → ровно 32 символа URL-safe base64 (no padding).
        assert len(result.nonce) == 32
        # Только URL-safe-символы [A-Za-z0-9_-].
        assert all(c.isalnum() or c in "-_" for c in result.nonce)
