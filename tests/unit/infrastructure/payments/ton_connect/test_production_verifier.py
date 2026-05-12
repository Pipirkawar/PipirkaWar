"""Тесты `TonConnectProductionVerifier` (Спринт 4.1-F, шаг F.5.c).

Покрывают:

* Happy-path: реально подписанный (`nacl.signing.SigningKey`) proof
  верифицируется → `True`.
* Все fail-paths возвращают `False`:
  - `TonProofMalformedError` от `parse_ton_proof` (battty JSON);
  - `proof.address != expected` (address-mismatch);
  - timestamp слишком старый (expired);
  - timestamp слишком в будущем (future);
  - domain не в whitelist-е (phishing-replay);
  - signature не сходится (`BadSignatureError`);
  - tampered payload/timestamp после подписи (canonical-message-mismatch).
* `TonConnectProductionConfig`-инварианты в `__post_init__`.
* fail-closed: подпись с правильным ключом, но canonical-message
  построен по другому payload-у → `False`.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

import nacl.signing
import pytest

from pipirik_wars.domain.monetization import TonProof
from pipirik_wars.infrastructure.payments.ton_connect import (
    TonConnectProductionConfig,
    TonConnectProductionVerifier,
    build_canonical_message,
)
from tests.fakes import FakeClock

_DEFAULT_DOMAIN = "pipirik.example.com"
_DEFAULT_TIMESTAMP = 1_700_000_000
_DEFAULT_NOW = datetime.fromtimestamp(_DEFAULT_TIMESTAMP + 30, tz=UTC)
_DEFAULT_PAYLOAD = "server-nonce-zXcv1234"
_DEFAULT_ADDRESS = "0:" + "ab" * 32


def _make_config(
    *,
    domains: tuple[str, ...] = (_DEFAULT_DOMAIN,),
    max_age: int = 600,
    skew: int = 60,
) -> TonConnectProductionConfig:
    return TonConnectProductionConfig(
        allowed_domains=domains,
        max_age_seconds=max_age,
        clock_skew_seconds=skew,
    )


def _build_signed_proof(
    *,
    signing_key: nacl.signing.SigningKey,
    timestamp: int = _DEFAULT_TIMESTAMP,
    domain: str = _DEFAULT_DOMAIN,
    payload: str = _DEFAULT_PAYLOAD,
    address: str = _DEFAULT_ADDRESS,
) -> str:
    """Построить wallet-response JSON, корректно подписанный приватным ключом."""
    pubkey_hex = signing_key.verify_key.encode().hex()
    # Сначала сделать TonProof с placeholder-signature, чтобы получить canonical-bytes.
    placeholder_sig = base64.b64encode(b"\x00" * 64).decode("ascii")
    placeholder_proof = TonProof(
        timestamp=timestamp,
        domain_value=domain,
        payload=payload,
        signature_b64=placeholder_sig,
        public_key_hex=pubkey_hex,
        address=address,
    )
    canonical = build_canonical_message(placeholder_proof)
    signature_bytes = signing_key.sign(canonical).signature
    signature_b64 = base64.b64encode(signature_bytes).decode("ascii")

    response = {
        "proof": {
            "timestamp": timestamp,
            "domain": {
                "lengthBytes": len(domain.encode("utf-8")),
                "value": domain,
            },
            "payload": payload,
            "signature": signature_b64,
        },
        "account": {
            "address": address,
            "publicKey": pubkey_hex,
        },
    }
    return json.dumps(response)


# ---------------------------------------------------------------------------
# Config-инварианты
# ---------------------------------------------------------------------------


class TestTonConnectProductionConfigInvariants:
    def test_valid_config_ok(self) -> None:
        config = _make_config()
        assert config.allowed_domains == (_DEFAULT_DOMAIN,)
        assert config.max_age_seconds == 600
        assert config.clock_skew_seconds == 60

    def test_empty_domains_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            TonConnectProductionConfig(
                allowed_domains=(),
                max_age_seconds=600,
                clock_skew_seconds=60,
            )

    def test_empty_domain_string_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            TonConnectProductionConfig(
                allowed_domains=("",),
                max_age_seconds=600,
                clock_skew_seconds=60,
            )

    def test_zero_max_age_raises(self) -> None:
        with pytest.raises(ValueError, match="max_age_seconds"):
            TonConnectProductionConfig(
                allowed_domains=(_DEFAULT_DOMAIN,),
                max_age_seconds=0,
                clock_skew_seconds=60,
            )

    def test_negative_skew_raises(self) -> None:
        with pytest.raises(ValueError, match="clock_skew_seconds"):
            TonConnectProductionConfig(
                allowed_domains=(_DEFAULT_DOMAIN,),
                max_age_seconds=600,
                clock_skew_seconds=-1,
            )

    def test_bool_max_age_raises(self) -> None:
        with pytest.raises(TypeError, match="max_age_seconds"):
            TonConnectProductionConfig(
                allowed_domains=(_DEFAULT_DOMAIN,),
                max_age_seconds=True,
                clock_skew_seconds=60,
            )


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------


class TestVerifyHappyPath:
    @pytest.mark.asyncio
    async def test_correctly_signed_proof_returns_true(self) -> None:
        signing_key = nacl.signing.SigningKey.generate()
        proof = _build_signed_proof(signing_key=signing_key)
        verifier = TonConnectProductionVerifier(
            config=_make_config(),
            clock=FakeClock(_DEFAULT_NOW),
        )
        result = await verifier.verify(address=_DEFAULT_ADDRESS, proof=proof)
        assert result is True

    @pytest.mark.asyncio
    async def test_timestamp_at_max_age_boundary_ok(self) -> None:
        # proof.timestamp == now - max_age → ровно граница, должен пройти.
        signing_key = nacl.signing.SigningKey.generate()
        ts = _DEFAULT_TIMESTAMP
        proof = _build_signed_proof(signing_key=signing_key, timestamp=ts)
        verifier = TonConnectProductionVerifier(
            config=_make_config(max_age=30, skew=0),
            clock=FakeClock(datetime.fromtimestamp(ts + 30, tz=UTC)),
        )
        assert await verifier.verify(address=_DEFAULT_ADDRESS, proof=proof) is True

    @pytest.mark.asyncio
    async def test_multiple_allowed_domains_match_any(self) -> None:
        signing_key = nacl.signing.SigningKey.generate()
        proof = _build_signed_proof(signing_key=signing_key, domain="alt.example.com")
        verifier = TonConnectProductionVerifier(
            config=_make_config(domains=(_DEFAULT_DOMAIN, "alt.example.com")),
            clock=FakeClock(_DEFAULT_NOW),
        )
        assert await verifier.verify(address=_DEFAULT_ADDRESS, proof=proof) is True


# ---------------------------------------------------------------------------
# Fail-paths
# ---------------------------------------------------------------------------


class TestVerifyFailPaths:
    @pytest.mark.asyncio
    async def test_malformed_proof_returns_false(self) -> None:
        verifier = TonConnectProductionVerifier(
            config=_make_config(),
            clock=FakeClock(_DEFAULT_NOW),
        )
        assert await verifier.verify(address=_DEFAULT_ADDRESS, proof="{bad json") is False

    @pytest.mark.asyncio
    async def test_address_mismatch_returns_false(self) -> None:
        signing_key = nacl.signing.SigningKey.generate()
        proof = _build_signed_proof(signing_key=signing_key)
        verifier = TonConnectProductionVerifier(
            config=_make_config(),
            clock=FakeClock(_DEFAULT_NOW),
        )
        other_address = "0:" + "cd" * 32
        assert await verifier.verify(address=other_address, proof=proof) is False

    @pytest.mark.asyncio
    async def test_expired_timestamp_returns_false(self) -> None:
        signing_key = nacl.signing.SigningKey.generate()
        proof = _build_signed_proof(signing_key=signing_key, timestamp=_DEFAULT_TIMESTAMP)
        verifier = TonConnectProductionVerifier(
            config=_make_config(max_age=10, skew=0),
            # now = timestamp + 100 — на 100с старее лимита 10с.
            clock=FakeClock(datetime.fromtimestamp(_DEFAULT_TIMESTAMP + 100, tz=UTC)),
        )
        assert await verifier.verify(address=_DEFAULT_ADDRESS, proof=proof) is False

    @pytest.mark.asyncio
    async def test_future_timestamp_returns_false(self) -> None:
        signing_key = nacl.signing.SigningKey.generate()
        # proof.timestamp намного больше now+skew.
        proof = _build_signed_proof(
            signing_key=signing_key,
            timestamp=_DEFAULT_TIMESTAMP + 1000,
        )
        verifier = TonConnectProductionVerifier(
            config=_make_config(max_age=600, skew=10),
            clock=FakeClock(datetime.fromtimestamp(_DEFAULT_TIMESTAMP, tz=UTC)),
        )
        assert await verifier.verify(address=_DEFAULT_ADDRESS, proof=proof) is False

    @pytest.mark.asyncio
    async def test_domain_not_allowed_returns_false(self) -> None:
        signing_key = nacl.signing.SigningKey.generate()
        proof = _build_signed_proof(signing_key=signing_key, domain="evil.example.com")
        verifier = TonConnectProductionVerifier(
            config=_make_config(domains=(_DEFAULT_DOMAIN,)),
            clock=FakeClock(_DEFAULT_NOW),
        )
        assert await verifier.verify(address=_DEFAULT_ADDRESS, proof=proof) is False

    @pytest.mark.asyncio
    async def test_signature_signed_by_wrong_key_returns_false(self) -> None:
        # Подписываем правильным ключом, но в response подменяем publicKey
        # на чужой ключ → подпись не сойдётся.
        signing_key_real = nacl.signing.SigningKey.generate()
        signing_key_other = nacl.signing.SigningKey.generate()
        proof_raw = _build_signed_proof(signing_key=signing_key_real)
        parsed: dict[str, Any] = json.loads(proof_raw)
        parsed["account"]["publicKey"] = signing_key_other.verify_key.encode().hex()
        tampered = json.dumps(parsed)
        verifier = TonConnectProductionVerifier(
            config=_make_config(),
            clock=FakeClock(_DEFAULT_NOW),
        )
        assert await verifier.verify(address=_DEFAULT_ADDRESS, proof=tampered) is False

    @pytest.mark.asyncio
    async def test_tampered_payload_after_signing_returns_false(self) -> None:
        signing_key = nacl.signing.SigningKey.generate()
        proof_raw = _build_signed_proof(signing_key=signing_key, payload="real-payload")
        parsed: dict[str, Any] = json.loads(proof_raw)
        # Меняем payload после подписи — canonical-message теперь другой.
        parsed["proof"]["payload"] = "tampered-payload"
        tampered = json.dumps(parsed)
        verifier = TonConnectProductionVerifier(
            config=_make_config(),
            clock=FakeClock(_DEFAULT_NOW),
        )
        assert await verifier.verify(address=_DEFAULT_ADDRESS, proof=tampered) is False

    @pytest.mark.asyncio
    async def test_tampered_timestamp_after_signing_returns_false(self) -> None:
        signing_key = nacl.signing.SigningKey.generate()
        proof_raw = _build_signed_proof(signing_key=signing_key)
        parsed: dict[str, Any] = json.loads(proof_raw)
        parsed["proof"]["timestamp"] = _DEFAULT_TIMESTAMP + 5
        tampered = json.dumps(parsed)
        verifier = TonConnectProductionVerifier(
            config=_make_config(),
            clock=FakeClock(_DEFAULT_NOW),
        )
        assert await verifier.verify(address=_DEFAULT_ADDRESS, proof=tampered) is False
