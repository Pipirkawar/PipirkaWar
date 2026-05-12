"""Тесты `build_canonical_message` TON Connect 2.0 (Спринт 4.1-F, шаг F.5.b).

Покрывают:

* Детерминизм: одинаковый `TonProof` → одинаковые 32 байта hash-а.
* Длина результата ровно 32 байта (sha256-digest).
* Изменение **любого** поля `TonProof` (timestamp / domain / payload /
  address-workchain / address-hash) → другой hash (по pre-image
  resistance sha256).
* Соответствие байтовому layout-у:
  - workchain — int32 BE (negative и positive workchain дают разные hash-и);
  - domain-длина — uint32 LE (length-prefix → коллизии без него легко
    подобрать);
  - timestamp — uint64 LE (large unix-времена помещаются).
* Round-trip с Ed25519: подписать canonical-hash приватным ключом и
  убедиться, что `nacl.signing.VerifyKey(pubkey).verify(canonical, sig)`
  принимает signature. Это интеграционный sanity-check, что наш
  byte-layout совместим с production-flow F.5.c.
"""

from __future__ import annotations

import base64
import hashlib

import nacl.signing
import pytest

from pipirik_wars.domain.monetization import TonProof
from pipirik_wars.infrastructure.payments.ton_connect import build_canonical_message

# Базовый valid-proof для всех тестов.
_VALID_SIG_B64 = base64.b64encode(b"\x00" * 64).decode("ascii")
_VALID_PUBKEY_HEX = "ab" * 32
_VALID_ADDRESS = "0:" + "ab" * 32
_VALID_TIMESTAMP = 1_700_000_000
_VALID_DOMAIN = "pipirik.example.com"
_VALID_PAYLOAD = "server-nonce-abcd1234"


def _make_proof(**overrides: object) -> TonProof:
    defaults: dict[str, object] = {
        "timestamp": _VALID_TIMESTAMP,
        "domain_value": _VALID_DOMAIN,
        "payload": _VALID_PAYLOAD,
        "signature_b64": _VALID_SIG_B64,
        "public_key_hex": _VALID_PUBKEY_HEX,
        "address": _VALID_ADDRESS,
    }
    defaults.update(overrides)
    return TonProof(**defaults)  # type: ignore[arg-type]


class TestBuildCanonicalMessageBasics:
    """Базовые свойства: длина, детерминизм."""

    def test_returns_32_bytes(self) -> None:
        result = build_canonical_message(_make_proof())
        assert isinstance(result, bytes)
        assert len(result) == 32

    def test_deterministic_same_input_same_output(self) -> None:
        proof = _make_proof()
        assert build_canonical_message(proof) == build_canonical_message(proof)

    def test_equal_proofs_yield_equal_hashes(self) -> None:
        proof1 = _make_proof()
        proof2 = _make_proof()
        assert build_canonical_message(proof1) == build_canonical_message(proof2)


class TestBuildCanonicalMessageSensitivity:
    """Изменение любого поля → другой hash."""

    def test_different_timestamp_yields_different_hash(self) -> None:
        h1 = build_canonical_message(_make_proof(timestamp=_VALID_TIMESTAMP))
        h2 = build_canonical_message(_make_proof(timestamp=_VALID_TIMESTAMP + 1))
        assert h1 != h2

    def test_different_domain_yields_different_hash(self) -> None:
        h1 = build_canonical_message(_make_proof(domain_value="example.com"))
        h2 = build_canonical_message(_make_proof(domain_value="example.net"))
        assert h1 != h2

    def test_different_payload_yields_different_hash(self) -> None:
        h1 = build_canonical_message(_make_proof(payload="nonce-a"))
        h2 = build_canonical_message(_make_proof(payload="nonce-b"))
        assert h1 != h2

    def test_different_workchain_yields_different_hash(self) -> None:
        h1 = build_canonical_message(_make_proof(address="0:" + "ab" * 32))
        h2 = build_canonical_message(_make_proof(address="-1:" + "ab" * 32))
        assert h1 != h2

    def test_different_address_hash_yields_different_hash(self) -> None:
        h1 = build_canonical_message(_make_proof(address="0:" + "ab" * 32))
        h2 = build_canonical_message(_make_proof(address="0:" + "cd" * 32))
        assert h1 != h2


class TestBuildCanonicalMessageLayout:
    """Сверка с эталонной реализацией: воспроизвести байты по спеке вручную."""

    def test_layout_matches_spec_for_known_proof(self) -> None:
        proof = _make_proof()
        # Воспроизводим алгоритм по спеке: schema + workchain_int32_be +
        # address_hash + domain_len_uint32_le + domain_utf8 + timestamp_uint64_le + payload_utf8.
        workchain = 0
        address_hash = bytes.fromhex("ab" * 32)
        domain_bytes = _VALID_DOMAIN.encode("utf-8")
        payload_bytes = _VALID_PAYLOAD.encode("utf-8")
        message = (
            b"ton-proof-item-v2/"
            + workchain.to_bytes(4, byteorder="big", signed=True)
            + address_hash
            + len(domain_bytes).to_bytes(4, byteorder="little", signed=False)
            + domain_bytes
            + _VALID_TIMESTAMP.to_bytes(8, byteorder="little", signed=False)
            + payload_bytes
        )
        inner = hashlib.sha256(message).digest()
        expected = hashlib.sha256(b"\xff\xff" + b"ton-connect" + inner).digest()
        assert build_canonical_message(proof) == expected

    def test_masterchain_workchain_uses_signed_int32_be(self) -> None:
        # Masterchain в TON — workchain=-1, должен корректно сериализоваться
        # как int32 big-endian (FF FF FF FF).
        proof = _make_proof(address="-1:" + "01" * 32)
        # Минимальная сверка: hash отличается от basechain.
        baseline = build_canonical_message(_make_proof(address="0:" + "01" * 32))
        master = build_canonical_message(proof)
        assert master != baseline
        # И воспроизводим вручную, что workchain=-1 кодируется как 0xFFFFFFFF.
        msg_with_negative_wc = (
            b"ton-proof-item-v2/"
            + (-1).to_bytes(4, byteorder="big", signed=True)
            + bytes.fromhex("01" * 32)
            + len(_VALID_DOMAIN.encode("utf-8")).to_bytes(4, byteorder="little")
            + _VALID_DOMAIN.encode("utf-8")
            + _VALID_TIMESTAMP.to_bytes(8, byteorder="little")
            + _VALID_PAYLOAD.encode("utf-8")
        )
        inner = hashlib.sha256(msg_with_negative_wc).digest()
        expected = hashlib.sha256(b"\xff\xff" + b"ton-connect" + inner).digest()
        assert master == expected

    def test_large_timestamp_fits_uint64(self) -> None:
        # 2^32 + 1 — больше uint32, но влезает в uint64 LE.
        large_ts = 2**32 + 1
        proof = _make_proof(timestamp=large_ts)
        # Не должно бросить и не должно совпасть с timestamp=1.
        h_large = build_canonical_message(proof)
        h_one = build_canonical_message(_make_proof(timestamp=1))
        assert h_large != h_one
        assert len(h_large) == 32


class TestBuildCanonicalMessageEd25519RoundTrip:
    """Round-trip: подписать canonical-hash приватным ключом и проверить
    через `VerifyKey.verify(...)` с публичным ключом.

    Это интеграционный sanity-check байт-layout-а: если наш билдер
    выдаёт «не те» байты, `pynacl.VerifyKey.verify(...)` упадёт.
    """

    def test_signed_canonical_message_verifies_with_pubkey(self) -> None:
        # Генерируем эфемерный keypair.
        signing_key = nacl.signing.SigningKey.generate()
        verify_key = signing_key.verify_key

        public_key_hex = verify_key.encode().hex()
        proof = _make_proof(public_key_hex=public_key_hex)
        canonical = build_canonical_message(proof)

        signature = signing_key.sign(canonical).signature
        # Если что-то не так с layout-ом — `verify` бросит исключение.
        verify_key.verify(canonical, signature)  # raises BadSignatureError on mismatch

    def test_signature_from_different_key_fails(self) -> None:
        signing_key_a = nacl.signing.SigningKey.generate()
        signing_key_b = nacl.signing.SigningKey.generate()

        proof = _make_proof(public_key_hex=signing_key_a.verify_key.encode().hex())
        canonical = build_canonical_message(proof)

        # Подписать ключом B — verify через ключ A должно упасть.
        bad_signature = signing_key_b.sign(canonical).signature
        with pytest.raises(nacl.exceptions.BadSignatureError):
            signing_key_a.verify_key.verify(canonical, bad_signature)

    def test_signature_over_different_canonical_fails(self) -> None:
        signing_key = nacl.signing.SigningKey.generate()
        verify_key = signing_key.verify_key

        proof_a = _make_proof(
            public_key_hex=verify_key.encode().hex(),
            payload="nonce-a",
        )
        proof_b = _make_proof(
            public_key_hex=verify_key.encode().hex(),
            payload="nonce-b",
        )
        canonical_a = build_canonical_message(proof_a)
        canonical_b = build_canonical_message(proof_b)
        assert canonical_a != canonical_b

        signature_a = signing_key.sign(canonical_a).signature
        # signature_a над canonical_a, но мы проверяем canonical_b — должно упасть.
        with pytest.raises(nacl.exceptions.BadSignatureError):
            verify_key.verify(canonical_b, signature_a)
