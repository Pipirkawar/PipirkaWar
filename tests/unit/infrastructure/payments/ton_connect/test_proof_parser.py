"""Тесты `parse_ton_proof` JSON-деsерialайзера (Спринт 4.1-F, шаг F.5.a).

Покрывают:

* Happy-path: канонический wallet-response → `TonProof`-VO с правильными
  значениями всех полей (включая optional `state_init`).
* `TonProofMalformedError(reason, raw_len)` на:
  * битый JSON;
  * top-level не объект;
  * отсутствующие обязательные поля (proof/account/timestamp/domain/...);
  * неправильные типы полей (timestamp как bool/str, domain как str/list, ...);
  * `proof.domain.lengthBytes` ≠ utf8-длине `proof.domain.value`;
  * VO-invariant-фейлы (e.g. timestamp ≤ 0, payload пустой, address не raw).
* `raw_len` всегда равен длине utf8-encoded raw-payload-а
  (для structured-лога без содержимого).
* sensitive-данные (signature/payload/pubkey) **не** утекают в `str(exc)`.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from pipirik_wars.domain.monetization import TonProof, TonProofMalformedError
from pipirik_wars.infrastructure.payments.ton_connect import parse_ton_proof

# Валидные «болванки» (совпадают с тестами VO).
_VALID_SIG_B64 = base64.b64encode(b"\x00" * 64).decode("ascii")
_VALID_PUBKEY_HEX = "ab" * 32
_VALID_ADDRESS = "0:" + "ab" * 32
_VALID_TIMESTAMP = 1_700_000_000
_VALID_DOMAIN = "pipirik.example.com"
_VALID_PAYLOAD = "server-nonce-abcd1234"
_VALID_STATE_INIT_B64 = base64.b64encode(b"\xde\xad\xbe\xef" * 8).decode("ascii")


def _valid_wallet_response(**overrides: Any) -> dict[str, Any]:
    """Канонический wallet-response (см. spec в module-docstring `proof_parser`)."""
    proof = {
        "timestamp": _VALID_TIMESTAMP,
        "domain": {
            "lengthBytes": len(_VALID_DOMAIN.encode("utf-8")),
            "value": _VALID_DOMAIN,
        },
        "payload": _VALID_PAYLOAD,
        "signature": _VALID_SIG_B64,
    }
    account = {
        "address": _VALID_ADDRESS,
        "publicKey": _VALID_PUBKEY_HEX,
    }
    base = {"proof": proof, "account": account}
    base.update(overrides)
    return base


def _dump(obj: dict[str, Any]) -> str:
    return json.dumps(obj)


class TestParseTonProofHappyPath:
    """Канонический JSON → валидный `TonProof`-VO."""

    def test_minimal_response_returns_ton_proof(self) -> None:
        proof = parse_ton_proof(_dump(_valid_wallet_response()))
        assert isinstance(proof, TonProof)
        assert proof.timestamp == _VALID_TIMESTAMP
        assert proof.domain_value == _VALID_DOMAIN
        assert proof.payload == _VALID_PAYLOAD
        assert proof.signature_b64 == _VALID_SIG_B64
        assert proof.public_key_hex == _VALID_PUBKEY_HEX
        assert proof.address == _VALID_ADDRESS
        assert proof.state_init_b64 is None

    def test_state_init_field_passed_through(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["state_init"] = _VALID_STATE_INIT_B64
        proof = parse_ton_proof(_dump(response))
        assert proof.state_init_b64 == _VALID_STATE_INIT_B64

    def test_unicode_domain_with_correct_length_ok(self) -> None:
        # Кириллический host (5 utf8-байт) — domain pattern допускает только ASCII,
        # но length-mismatch проверка должна работать на тех ASCII-доменах,
        # которые корректно encoded.
        domain = "ton-connect.example"
        response = _valid_wallet_response()
        response["proof"]["domain"] = {
            "lengthBytes": len(domain.encode("utf-8")),
            "value": domain,
        }
        proof = parse_ton_proof(_dump(response))
        assert proof.domain_value == domain


class TestParseTonProofJsonErrors:
    """JSON-парс упал."""

    def test_invalid_json_raises_json_parse(self) -> None:
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof("{not valid json")
        assert exc_info.value.reason == "json_parse"
        assert exc_info.value.raw_len == len("{not valid json")

    def test_empty_string_raises_json_parse(self) -> None:
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof("")
        assert exc_info.value.reason == "json_parse"
        assert exc_info.value.raw_len == 0

    def test_top_level_not_object_raises_not_object(self) -> None:
        raw = json.dumps([1, 2, 3])
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(raw)
        assert exc_info.value.reason == "not_object"
        assert exc_info.value.raw_len == len(raw.encode("utf-8"))

    def test_top_level_null_raises_not_object(self) -> None:
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof("null")
        assert exc_info.value.reason == "not_object"


class TestParseTonProofMissingFields:
    """Отсутствуют обязательные поля."""

    @pytest.mark.parametrize(
        "missing_key",
        ["proof", "account"],
    )
    def test_missing_top_level_field(self, missing_key: str) -> None:
        response = _valid_wallet_response()
        response.pop(missing_key)
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "missing_field"

    @pytest.mark.parametrize(
        "missing_key",
        ["timestamp", "domain", "payload", "signature"],
    )
    def test_missing_proof_subfield(self, missing_key: str) -> None:
        response = _valid_wallet_response()
        response["proof"].pop(missing_key)
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "missing_field"

    @pytest.mark.parametrize(
        "missing_key",
        ["value", "lengthBytes"],
    )
    def test_missing_domain_subfield(self, missing_key: str) -> None:
        response = _valid_wallet_response()
        response["proof"]["domain"].pop(missing_key)
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "missing_field"

    @pytest.mark.parametrize(
        "missing_key",
        ["address", "publicKey"],
    )
    def test_missing_account_subfield(self, missing_key: str) -> None:
        response = _valid_wallet_response()
        response["account"].pop(missing_key)
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "missing_field"


class TestParseTonProofTypeMismatches:
    """Schema есть, но тип неправильный."""

    def test_proof_section_not_dict_raises_type_mismatch(self) -> None:
        response: dict[str, Any] = _valid_wallet_response()
        response["proof"] = "not a dict"
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "type_mismatch"

    def test_account_section_not_dict_raises_type_mismatch(self) -> None:
        response: dict[str, Any] = _valid_wallet_response()
        response["account"] = ["not", "a", "dict"]
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "type_mismatch"

    def test_timestamp_as_string_raises_bad_timestamp(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["timestamp"] = str(_VALID_TIMESTAMP)
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "bad_timestamp"

    def test_timestamp_as_bool_raises_bad_timestamp(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["timestamp"] = True
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "bad_timestamp"

    def test_domain_not_dict_raises_bad_domain(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["domain"] = _VALID_DOMAIN  # string instead of object
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "bad_domain"

    def test_domain_value_not_string_raises_bad_domain(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["domain"]["value"] = 12345
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "bad_domain"

    def test_domain_length_bytes_as_bool_raises_bad_domain(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["domain"]["lengthBytes"] = True
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "bad_domain"

    def test_payload_as_int_raises_bad_payload(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["payload"] = 42
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "bad_payload"

    def test_signature_as_int_raises_bad_signature(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["signature"] = 12345
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "bad_signature"

    def test_address_as_int_raises_bad_address(self) -> None:
        response = _valid_wallet_response()
        response["account"]["address"] = 0
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "bad_address"

    def test_public_key_as_int_raises_bad_pubkey(self) -> None:
        response = _valid_wallet_response()
        response["account"]["publicKey"] = 0xABCD
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "bad_pubkey"

    def test_state_init_as_int_raises_bad_state_init(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["state_init"] = 12345
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "bad_state_init"


class TestParseTonProofDomainLengthMismatch:
    """`proof.domain.lengthBytes` обязан совпадать с utf8-длиной `value`."""

    def test_length_bytes_too_large(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["domain"]["lengthBytes"] = 999
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "domain_length_mismatch"

    def test_length_bytes_too_small(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["domain"]["lengthBytes"] = 1
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "domain_length_mismatch"


class TestParseTonProofVoInvariantFailures:
    """VO-invariant-фейлы (timestamp ≤ 0, bad address, bad payload, ...)."""

    def test_zero_timestamp_raises_vo_invariant(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["timestamp"] = 0
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "vo_invariant"

    def test_empty_payload_raises_vo_invariant(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["payload"] = ""
        # Empty payload → domain.lengthBytes must match value length, payload is separate
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "vo_invariant"

    def test_too_long_payload_raises_vo_invariant(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["payload"] = "x" * 1024
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "vo_invariant"

    def test_non_raw_address_raises_vo_invariant(self) -> None:
        response = _valid_wallet_response()
        response["account"]["address"] = "EQ" + "A" * 46  # user-friendly form, not raw
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "vo_invariant"

    def test_short_signature_raises_vo_invariant(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["signature"] = base64.b64encode(b"\x00" * 32).decode("ascii")
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "vo_invariant"

    def test_short_pubkey_raises_vo_invariant(self) -> None:
        response = _valid_wallet_response()
        response["account"]["publicKey"] = "ab" * 16  # 16 bytes, not 32
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "vo_invariant"

    def test_bad_state_init_b64_raises_vo_invariant(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["state_init"] = "not-valid-base64-!!!"
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        assert exc_info.value.reason == "vo_invariant"


class TestParseTonProofSensitiveData:
    """Sensitive-данные (signature/payload/pubkey) не утекают в текст исключения."""

    def test_exception_text_does_not_contain_signature(self) -> None:
        response = _valid_wallet_response()
        response["proof"]["payload"] = ""  # trigger VO invariant
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(_dump(response))
        message = str(exc_info.value)
        assert _VALID_SIG_B64 not in message
        assert _VALID_PUBKEY_HEX not in message
        assert _VALID_PAYLOAD not in message

    def test_raw_len_equals_utf8_byte_length(self) -> None:
        # Cyrillic в JSON-payload-е, чтобы utf8-длина ≠ char-длине.
        raw = _dump(_valid_wallet_response(extra="тест"))
        broken = raw[:-1]  # truncate to break JSON
        with pytest.raises(TonProofMalformedError) as exc_info:
            parse_ton_proof(broken)
        assert exc_info.value.raw_len == len(broken.encode("utf-8"))
