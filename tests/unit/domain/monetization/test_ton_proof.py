"""Тесты `TonProof`-VO и `TonConnectVerificationError`-таксономии (Спринт 4.1-F, шаг F.2).

Покрывают:

* `__post_init__`-invariant-ы `TonProof`: типы полей, форматы (base64-
  signature 64 байта; hex-pubkey 64 hex-сим / 32 байта; raw-address
  `workchain:hex64`; host-like domain; ASCII-payload; positive timestamp;
  optional base64 state_init).
* frozen + slots-инвариант VO (нельзя мутировать; нет `__dict__`).
* hashable / equality по полям.
* `TonConnectVerificationError`-таксономия: base + 6 sub-class-ов
  (Malformed / Expired / DomainMismatch / SignatureInvalid /
  AddressMismatch / Replayed). Каждая сохраняет машинно-читаемые
  attribute-ы; sensitive-байты (signature/canonical-message) в
  exception-ах **не** хранятся.
"""

from __future__ import annotations

import base64
import dataclasses

import pytest

from pipirik_wars.domain.monetization import (
    MonetizationDomainError,
    TonConnectVerificationError,
    TonProof,
    TonProofAddressMismatchError,
    TonProofDomainMismatchError,
    TonProofExpiredError,
    TonProofMalformedError,
    TonProofReplayedError,
    TonProofSignatureInvalidError,
)
from pipirik_wars.shared.errors import DomainError

# Валидные «болванки» для аттрибутов, чтобы не дублировать в каждом тесте.
_VALID_SIG_B64 = base64.b64encode(b"\x00" * 64).decode("ascii")
_VALID_PUBKEY_HEX = "ab" * 32  # 64 hex-сим = 32 байта
_VALID_ADDRESS = "0:" + "ab" * 32
_VALID_TIMESTAMP = 1_700_000_000
_VALID_DOMAIN = "pipirik.example.com"
_VALID_PAYLOAD = "server-nonce-abcd1234"
_VALID_STATE_INIT_B64 = base64.b64encode(b"\xde\xad\xbe\xef" * 8).decode("ascii")


def _valid_proof_kwargs() -> dict[str, object]:
    return {
        "timestamp": _VALID_TIMESTAMP,
        "domain_value": _VALID_DOMAIN,
        "payload": _VALID_PAYLOAD,
        "signature_b64": _VALID_SIG_B64,
        "public_key_hex": _VALID_PUBKEY_HEX,
        "address": _VALID_ADDRESS,
    }


class TestTonProofPostInitHappyPath:
    """Корректный proof — конструктор не бросает."""

    def test_minimal_proof_ok(self) -> None:
        proof = TonProof(**_valid_proof_kwargs())  # type: ignore[arg-type]
        assert proof.timestamp == _VALID_TIMESTAMP
        assert proof.domain_value == _VALID_DOMAIN
        assert proof.payload == _VALID_PAYLOAD
        assert proof.signature_b64 == _VALID_SIG_B64
        assert proof.public_key_hex == _VALID_PUBKEY_HEX
        assert proof.address == _VALID_ADDRESS
        assert proof.state_init_b64 is None

    def test_proof_with_state_init_ok(self) -> None:
        proof = TonProof(
            **_valid_proof_kwargs(),  # type: ignore[arg-type]
            state_init_b64=_VALID_STATE_INIT_B64,
        )
        assert proof.state_init_b64 == _VALID_STATE_INIT_B64

    @pytest.mark.parametrize(
        "address",
        [
            "0:" + "ab" * 32,
            "-1:" + "01" * 32,
            "1:" + "FF" * 32,
            "-100:" + "0a" * 32,
        ],
    )
    def test_raw_address_formats_accepted(self, address: str) -> None:
        proof = TonProof(
            **{**_valid_proof_kwargs(), "address": address},  # type: ignore[arg-type]
        )
        assert proof.address == address

    @pytest.mark.parametrize(
        "domain_value",
        [
            "pipirik.example.com",
            "localhost",
            "localhost:8080",
            "test.example.com:8443",
            "a",
            "host-with-dashes.example.com",
        ],
    )
    def test_host_like_domain_accepted(self, domain_value: str) -> None:
        proof = TonProof(
            **{**_valid_proof_kwargs(), "domain_value": domain_value},  # type: ignore[arg-type]
        )
        assert proof.domain_value == domain_value


class TestTonProofTimestampInvariants:
    """timestamp — int > 0."""

    @pytest.mark.parametrize("bad", [1.0, "1700000000", None, True, False, object()])
    def test_non_int_timestamp_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="timestamp must be int"):
            TonProof(**{**_valid_proof_kwargs(), "timestamp": bad})  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", [0, -1, -1_700_000_000])
    def test_non_positive_timestamp_raises(self, bad: int) -> None:
        with pytest.raises(ValueError, match="timestamp must be > 0"):
            TonProof(**{**_valid_proof_kwargs(), "timestamp": bad})  # type: ignore[arg-type]


class TestTonProofDomainInvariants:
    """domain_value — utf8-host-like-строка, [1, 253] символов."""

    @pytest.mark.parametrize("bad", [123, None, b"host.com", object(), True])
    def test_non_str_domain_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="domain_value must be str"):
            TonProof(**{**_valid_proof_kwargs(), "domain_value": bad})  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "host with space",
            "host\twith\ttab",
            "юникод-host.com",
            "host\n.com",
            "a" * 254,  # > 253
        ],
    )
    def test_invalid_domain_format_raises(self, bad: str) -> None:
        with pytest.raises(ValueError, match="domain_value must match"):
            TonProof(**{**_valid_proof_kwargs(), "domain_value": bad})  # type: ignore[arg-type]


class TestTonProofPayloadInvariants:
    """payload — ASCII-printable, [1, 512] символов."""

    @pytest.mark.parametrize("bad", [123, None, b"payload", object(), True])
    def test_non_str_payload_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="payload must be str"):
            TonProof(**{**_valid_proof_kwargs(), "payload": bad})  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "a" * 513,
            "юникод_в_payload",
            "payload\nwith\nnewlines",
            "tab\there",
            "non-ascii-\x01",
        ],
    )
    def test_invalid_payload_format_raises(self, bad: str) -> None:
        with pytest.raises(ValueError, match="payload must match"):
            TonProof(**{**_valid_proof_kwargs(), "payload": bad})  # type: ignore[arg-type]


class TestTonProofSignatureInvariants:
    """signature_b64 — base64 → ровно 64 байта."""

    @pytest.mark.parametrize("bad", [123, None, b"sig", object()])
    def test_non_str_signature_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="signature_b64 must be str"):
            TonProof(**{**_valid_proof_kwargs(), "signature_b64": bad})  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "bad",
        [
            "!!!not-base64!!!",
            "abc",  # некратный 4 base64
            "юникод_не_base64",
        ],
    )
    def test_non_base64_signature_raises(self, bad: str) -> None:
        with pytest.raises(ValueError, match="signature_b64 must be valid base64"):
            TonProof(
                **{**_valid_proof_kwargs(), "signature_b64": bad},  # type: ignore[arg-type]
            )

    @pytest.mark.parametrize(
        "n_bytes",
        [0, 32, 63, 65, 128],
    )
    def test_wrong_signature_length_raises(self, n_bytes: int) -> None:
        sig = base64.b64encode(b"\x00" * n_bytes).decode("ascii")
        with pytest.raises(
            ValueError,
            match=r"signature_b64 must decode to 64 bytes",
        ):
            TonProof(**{**_valid_proof_kwargs(), "signature_b64": sig})  # type: ignore[arg-type]


class TestTonProofPublicKeyInvariants:
    """public_key_hex — 64 hex-символа (32 байта Ed25519)."""

    @pytest.mark.parametrize("bad", [123, None, b"pk", object()])
    def test_non_str_pubkey_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="public_key_hex must be str"):
            TonProof(**{**_valid_proof_kwargs(), "public_key_hex": bad})  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "ab" * 31,
            "ab" * 33,
            "g" * 64,  # не-hex символы
            "z" * 64,
            "0123456789ABCDEFG" + "0" * 47,  # не-hex
        ],
    )
    def test_invalid_pubkey_format_raises(self, bad: str) -> None:
        with pytest.raises(ValueError, match="public_key_hex must be"):
            TonProof(
                **{**_valid_proof_kwargs(), "public_key_hex": bad},  # type: ignore[arg-type]
            )


class TestTonProofAddressInvariants:
    """address — только raw-формат `workchain:hex64`."""

    @pytest.mark.parametrize("bad", [123, None, b"addr", object()])
    def test_non_str_address_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="address must be str"):
            TonProof(**{**_valid_proof_kwargs(), "address": bad})  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "EQAbcdefABCDEF0123456789ABCDEF0123456789ABCDEF__",  # user-friendly (запрещён)
            "0:" + "ab" * 31,  # короткий hash
            "0:" + "ab" * 33,  # длинный hash
            "0:" + "zz" * 32,  # не-hex
            "abc:" + "ab" * 32,  # нечисловой workchain
            "0-ab" * 32,  # нет двоеточия
        ],
    )
    def test_invalid_address_format_raises(self, bad: str) -> None:
        with pytest.raises(ValueError, match="address must be in raw form"):
            TonProof(**{**_valid_proof_kwargs(), "address": bad})  # type: ignore[arg-type]


class TestTonProofStateInitInvariants:
    """state_init_b64 — None или валидный base64."""

    def test_none_state_init_ok(self) -> None:
        proof = TonProof(**_valid_proof_kwargs(), state_init_b64=None)  # type: ignore[arg-type]
        assert proof.state_init_b64 is None

    @pytest.mark.parametrize("bad", [123, b"state", object(), True])
    def test_non_str_state_init_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="state_init_b64 must be str"):
            TonProof(
                **_valid_proof_kwargs(),  # type: ignore[arg-type]
                state_init_b64=bad,  # type: ignore[arg-type]
            )

    @pytest.mark.parametrize(
        "bad",
        [
            "!!!not-base64!!!",
            "abc",  # некратный 4
            "юникод",
        ],
    )
    def test_invalid_base64_state_init_raises(self, bad: str) -> None:
        with pytest.raises(ValueError, match="state_init_b64 must be valid base64"):
            TonProof(
                **_valid_proof_kwargs(),  # type: ignore[arg-type]
                state_init_b64=bad,
            )


class TestTonProofImmutability:
    """frozen + slots → нет `__dict__`, неизменяемость, hashability."""

    def test_proof_is_frozen(self) -> None:
        proof = TonProof(**_valid_proof_kwargs())  # type: ignore[arg-type]
        with pytest.raises(dataclasses.FrozenInstanceError):
            proof.timestamp = 1_800_000_000

    def test_proof_has_no_dict_due_to_slots(self) -> None:
        proof = TonProof(**_valid_proof_kwargs())  # type: ignore[arg-type]
        assert not hasattr(proof, "__dict__")
        assert set(TonProof.__slots__) == {
            "timestamp",
            "domain_value",
            "payload",
            "signature_b64",
            "public_key_hex",
            "address",
            "state_init_b64",
        }

    def test_proofs_with_same_values_compare_equal(self) -> None:
        a = TonProof(**_valid_proof_kwargs())  # type: ignore[arg-type]
        b = TonProof(**_valid_proof_kwargs())  # type: ignore[arg-type]
        assert a == b
        assert hash(a) == hash(b)

    def test_proofs_with_different_payload_compare_unequal(self) -> None:
        a = TonProof(**_valid_proof_kwargs())  # type: ignore[arg-type]
        b = TonProof(
            **{**_valid_proof_kwargs(), "payload": "different-nonce-9876"},  # type: ignore[arg-type]
        )
        assert a != b


# ---------------------------------------------------------------------------
# TonConnectVerificationError taxonomy
# ---------------------------------------------------------------------------


class TestTonConnectVerificationErrorBase:
    """`TonConnectVerificationError` — base, все sub-class-ы наследуют."""

    def test_all_subclasses_inherit_from_base(self) -> None:
        subclasses: list[type[TonConnectVerificationError]] = [
            TonProofMalformedError,
            TonProofExpiredError,
            TonProofDomainMismatchError,
            TonProofSignatureInvalidError,
            TonProofAddressMismatchError,
            TonProofReplayedError,
        ]
        for cls in subclasses:
            assert issubclass(cls, TonConnectVerificationError)
            assert issubclass(cls, MonetizationDomainError)
            assert issubclass(cls, DomainError)


class TestTonProofMalformedError:
    def test_attributes_exposed(self) -> None:
        err = TonProofMalformedError(reason="json_parse", raw_len=512)
        assert err.reason == "json_parse"
        assert err.raw_len == 512

    def test_str_includes_reason_and_len(self) -> None:
        err = TonProofMalformedError(reason="missing_field", raw_len=64)
        text = str(err)
        assert "missing_field" in text
        assert "64" in text

    @pytest.mark.parametrize(
        "reason",
        [
            "json_parse",
            "missing_field",
            "type_mismatch",
            "bad_signature_length",
            "bad_pubkey_length",
            "bad_address_format",
            "bad_timestamp",
            "bad_domain",
            "bad_payload",
            "bad_state_init",
        ],
    )
    def test_documented_reasons_constructible(self, reason: str) -> None:
        err = TonProofMalformedError(reason=reason, raw_len=0)
        assert err.reason == reason

    def test_keyword_only_constructor(self) -> None:
        with pytest.raises(TypeError):
            TonProofMalformedError("json_parse", 0)


class TestTonProofExpiredError:
    def test_attributes_exposed(self) -> None:
        err = TonProofExpiredError(
            proof_timestamp=1_700_000_000,
            now_timestamp=1_700_000_700,
            max_age_seconds=600,
        )
        assert err.proof_timestamp == 1_700_000_000
        assert err.now_timestamp == 1_700_000_700
        assert err.max_age_seconds == 600

    def test_str_contains_diagnostic_fields(self) -> None:
        err = TonProofExpiredError(
            proof_timestamp=1_700_000_000,
            now_timestamp=1_700_000_700,
            max_age_seconds=600,
        )
        text = str(err)
        assert "1700000000" in text
        assert "1700000700" in text
        assert "600" in text


class TestTonProofDomainMismatchError:
    def test_attributes_exposed(self) -> None:
        err = TonProofDomainMismatchError(
            actual_domain="malicious.com",
            allowed_domains=("pipirik.example.com",),
        )
        assert err.actual_domain == "malicious.com"
        assert err.allowed_domains == ("pipirik.example.com",)

    def test_str_lists_both_actual_and_allowed(self) -> None:
        err = TonProofDomainMismatchError(
            actual_domain="malicious.com",
            allowed_domains=("pipirik.example.com", "staging.example.com"),
        )
        text = str(err)
        assert "malicious.com" in text
        assert "pipirik.example.com" in text
        assert "staging.example.com" in text


class TestTonProofSignatureInvalidError:
    def test_attributes_exposed(self) -> None:
        err = TonProofSignatureInvalidError(public_key_hex=_VALID_PUBKEY_HEX)
        assert err.public_key_hex == _VALID_PUBKEY_HEX

    def test_no_signature_bytes_stored_in_attributes(self) -> None:
        # Безопасность: подпись/canonical-message **не** хранятся в exception-е.
        err = TonProofSignatureInvalidError(public_key_hex=_VALID_PUBKEY_HEX)
        # Только pubkey_hex как контекст для forensics.
        public_attrs = {a for a in dir(err) if not a.startswith("_")}
        assert "signature" not in public_attrs
        assert "canonical_message" not in public_attrs
        assert "raw_proof" not in public_attrs


class TestTonProofAddressMismatchError:
    def test_attributes_exposed(self) -> None:
        actual = "0:" + "ab" * 32
        expected = "0:" + "cd" * 32
        err = TonProofAddressMismatchError(
            actual_address=actual,
            expected_address=expected,
        )
        assert err.actual_address == actual
        assert err.expected_address == expected

    def test_str_contains_both_addresses(self) -> None:
        actual = "0:" + "ab" * 32
        expected = "0:" + "cd" * 32
        err = TonProofAddressMismatchError(
            actual_address=actual,
            expected_address=expected,
        )
        text = str(err)
        assert actual in text
        assert expected in text


class TestTonProofReplayedError:
    def test_attributes_exposed(self) -> None:
        err = TonProofReplayedError(scope="link_wallet:42:ton_nano")
        assert err.scope == "link_wallet:42:ton_nano"

    def test_str_contains_scope(self) -> None:
        err = TonProofReplayedError(scope="link_wallet:42:ton_nano")
        text = str(err)
        assert "link_wallet:42:ton_nano" in text
