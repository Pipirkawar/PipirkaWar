"""Unit-тесты `HmacTgStarsPayloadVerifier` (Спринт 4.1-D, шаг D.8.b).

Контракт:
* `serialize(...)` собирает строку формата
  ``<version>:<pack_value>:<seed>:<hmac_b64>`` (≤ `max_payload_bytes`),
  HMAC покрывает `version|pack_value|seed|amount|currency`.
* `verify(...)` — round-trip с `serialize(...)`. На любой failure
  возвращает `InvalidStarsPayloadError(reason, payload_len)` с
  правильным machine-readable `reason`.
* `hmac.compare_digest` (constant-time) — не тестируется напрямую,
  но проверяем, что подмена битов HMAC даёт `hmac_mismatch`.
* Golden-vector test — HMAC рассчитанный «вручную» через `hmac.new(...)`
  совпадает с тем, что выдаёт верификатор.
"""

from __future__ import annotations

import base64
import hmac as stdlib_hmac
from hashlib import sha256

import pytest
from pydantic import SecretStr

from pipirik_wars.domain.monetization.errors import InvalidStarsPayloadError
from pipirik_wars.domain.monetization.ports import ITgStarsPayloadVerifier
from pipirik_wars.domain.monetization.value_objects import Currency, StarsPayload
from pipirik_wars.infrastructure.payments.tg_stars.settings import TgStarsSettings
from pipirik_wars.infrastructure.payments.tg_stars.verifier import (
    HmacTgStarsPayloadVerifier,
)

_SECRET = "super-strong-32+byte-test-secret"
_PROVIDER_PAYMENT_ID = "tg_payment_charge_id_42"


def _make_verifier(
    *,
    secret: str = _SECRET,
    payload_version: str = "v1",
    max_payload_bytes: int = 128,
) -> HmacTgStarsPayloadVerifier:
    settings = TgStarsSettings(
        secret=SecretStr(secret),
        payload_version=payload_version,
        max_payload_bytes=max_payload_bytes,
    )
    return HmacTgStarsPayloadVerifier(settings)


def _expected_hmac_b64(
    *,
    secret: str,
    version: str,
    pack_value: str,
    idempotency_seed: str,
    amount_native: int,
    currency: Currency,
) -> str:
    """Эталонная HMAC-конструкция (для golden-vector-теста)."""
    context = b"\x00".join(
        [
            version.encode("ascii"),
            pack_value.encode("ascii"),
            idempotency_seed.encode("ascii"),
            str(amount_native).encode("ascii"),
            currency.value.encode("ascii"),
        ],
    )
    digest = stdlib_hmac.new(secret.encode("utf-8"), context, sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class TestSerializeFormat:
    def test_serialize_has_four_colon_separated_parts(self) -> None:
        verifier = _make_verifier()
        payload = verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        parts = payload.split(":")
        assert len(parts) == 4
        version, pack, seed, hmac_b64 = parts
        assert version == "v1"
        assert pack == "single"
        assert seed == "a" * 16
        assert len(hmac_b64) == 43  # base64url(32-byte HMAC) без паддинга

    def test_serialize_payload_fits_telegram_limit(self) -> None:
        # 128 байт — Telegram-лимит invoice_payload.
        verifier = _make_verifier()
        payload = verifier.serialize(
            pack_value="pack_10",
            idempotency_seed="A" * 32,  # макс. длина seed
            amount_native=10_000_000,
            currency=Currency.STARS,
        )
        assert len(payload.encode("ascii")) <= 128

    def test_serialize_uses_configured_version(self) -> None:
        verifier = _make_verifier(payload_version="v9")
        payload = verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=1,
            currency=Currency.STARS,
        )
        assert payload.startswith("v9:")


class TestSerializeHmacGolden:
    def test_serialize_hmac_matches_handcrafted_golden(self) -> None:
        verifier = _make_verifier()
        payload = verifier.serialize(
            pack_value="single",
            idempotency_seed="abcdefghijklmnop",  # 16 chars
            amount_native=50,
            currency=Currency.STARS,
        )
        _, _, _, actual_hmac_b64 = payload.split(":")
        expected = _expected_hmac_b64(
            secret=_SECRET,
            version="v1",
            pack_value="single",
            idempotency_seed="abcdefghijklmnop",
            amount_native=50,
            currency=Currency.STARS,
        )
        assert actual_hmac_b64 == expected

    def test_hmac_depends_on_amount(self) -> None:
        verifier = _make_verifier()
        a = verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        b = verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=51,  # +1
            currency=Currency.STARS,
        )
        # Только HMAC должен отличаться.
        assert a.split(":")[:3] == b.split(":")[:3]
        assert a.split(":")[3] != b.split(":")[3]

    def test_hmac_depends_on_currency(self) -> None:
        verifier = _make_verifier()
        a = verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        b = verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.TON_NANO,
        )
        assert a.split(":")[3] != b.split(":")[3]

    def test_hmac_depends_on_pack_value(self) -> None:
        verifier = _make_verifier()
        a = verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        b = verifier.serialize(
            pack_value="pack_10",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        assert a.split(":")[3] != b.split(":")[3]

    def test_hmac_depends_on_idempotency_seed(self) -> None:
        verifier = _make_verifier()
        a = verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        b = verifier.serialize(
            pack_value="single",
            idempotency_seed="b" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        assert a.split(":")[3] != b.split(":")[3]

    def test_hmac_depends_on_secret(self) -> None:
        v1 = _make_verifier(secret="secret-one-32+byte-test-secret-x")
        v2 = _make_verifier(secret="secret-two-32+byte-test-secret-y")
        a = v1.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        b = v2.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        assert a != b


class TestVerifyRoundTrip:
    def test_verify_returns_stars_payload_vo(self) -> None:
        verifier = _make_verifier()
        raw = verifier.serialize(
            pack_value="single",
            idempotency_seed="abcdefghijklmnop",
            amount_native=50,
            currency=Currency.STARS,
        )
        payload = verifier.verify(
            raw_payload=raw,
            provider_payment_id=_PROVIDER_PAYMENT_ID,
            amount_native=50,
            currency=Currency.STARS,
        )
        assert isinstance(payload, StarsPayload)
        assert payload.pack_value == "single"
        assert payload.idempotency_seed == "abcdefghijklmnop"

    def test_verify_accepts_both_pack_values(self) -> None:
        verifier = _make_verifier()
        for pack in ("single", "pack_10"):
            raw = verifier.serialize(
                pack_value=pack,
                idempotency_seed="a" * 16,
                amount_native=50,
                currency=Currency.STARS,
            )
            payload = verifier.verify(
                raw_payload=raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
            assert payload.pack_value == pack


class TestVerifyFailureModes:
    def _good_payload(
        self,
        verifier: HmacTgStarsPayloadVerifier,
    ) -> str:
        return verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )

    @pytest.mark.parametrize("raw", [None, ""])
    def test_empty_or_none_raw_payload_raises_empty(
        self,
        raw: str | None,
    ) -> None:
        verifier = _make_verifier()
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "empty"
        assert exc_info.value.payload_len == 0

    def test_too_long_payload_raises_too_long(self) -> None:
        verifier = _make_verifier(max_payload_bytes=32)
        long_payload = "x" * 64
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=long_payload,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "too_long"
        assert exc_info.value.payload_len == 64

    def test_empty_provider_payment_id_raises_bad_provider_id(self) -> None:
        verifier = _make_verifier()
        raw = self._good_payload(verifier)
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=raw,
                provider_payment_id="",
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "bad_provider_id"

    @pytest.mark.parametrize(
        "raw",
        [
            "no-colons-at-all",
            "only:two-parts",
            "three:parts:are:not:enough:either:six",
            "v1:single:seed",  # 3 части
        ],
    )
    def test_malformed_structure_raises_malformed(self, raw: str) -> None:
        verifier = _make_verifier()
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "malformed"

    def test_bad_version_raises_bad_version(self) -> None:
        verifier = _make_verifier(payload_version="v1")
        # Создаём payload в формате v2.
        v2_verifier = _make_verifier(payload_version="v2")
        raw_v2 = v2_verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=raw_v2,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "bad_version"

    def test_bad_hmac_not_base64_raises_bad_hmac(self) -> None:
        verifier = _make_verifier()
        # 43 символа, но не base64url (содержит `!`).
        raw = "v1:single:" + ("a" * 16) + ":" + ("!" * 43)
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "bad_hmac"

    def test_bad_hmac_wrong_length_raises_bad_hmac(self) -> None:
        verifier = _make_verifier()
        # Валидный base64, но декодируется в 3 байта (не 32).
        raw = "v1:single:" + ("a" * 16) + ":" + "AAAA"
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "bad_hmac"

    def test_empty_pack_value_raises_bad_pack(self) -> None:
        verifier = _make_verifier()
        # Делаем 4-part payload с пустым pack — HMAC не важен,
        # validation падает на VO раньше.
        raw = "v1::" + ("a" * 16) + ":" + ("A" * 43)
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "bad_pack"

    def test_bad_seed_format_raises_bad_seed(self) -> None:
        verifier = _make_verifier()
        # seed длиной 8 < 16 — VO режет на регексе.
        raw = "v1:single:short_x:" + ("A" * 43)
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "bad_seed"

    def test_tampered_hmac_raises_hmac_mismatch(self) -> None:
        verifier = _make_verifier()
        raw = self._good_payload(verifier)
        version, pack, seed, hmac_b64 = raw.split(":")
        # Меняем последний символ HMAC-а.
        tampered_hmac = hmac_b64[:-1] + ("A" if hmac_b64[-1] != "A" else "B")
        tampered_raw = ":".join([version, pack, seed, tampered_hmac])
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=tampered_raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "hmac_mismatch"

    def test_amount_mismatch_raises_hmac_mismatch(self) -> None:
        verifier = _make_verifier()
        raw = verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        # Клиент передаёт другой `amount_native` — HMAC не совпадёт.
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=999,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "hmac_mismatch"

    def test_currency_mismatch_raises_hmac_mismatch(self) -> None:
        verifier = _make_verifier()
        raw = verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        # Клиент передаёт другую currency — HMAC не совпадёт.
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.TON_NANO,
            )
        assert exc_info.value.reason == "hmac_mismatch"

    def test_different_secret_raises_hmac_mismatch(self) -> None:
        v_alice = _make_verifier(secret="alice-secret-32+byte-test-secret-x")
        v_bob = _make_verifier(secret="bob-secret-32+byte-test-secret-yyy")
        raw = v_alice.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            v_bob.verify(
                raw_payload=raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.reason == "hmac_mismatch"


class TestPortConformance:
    def test_implements_i_tg_stars_payload_verifier_protocol(self) -> None:
        verifier = _make_verifier()
        # `isinstance(..., Protocol)` работает на `@runtime_checkable`-
        # протоколах. Здесь — структурная проверка через приведение
        # к `ITgStarsPayloadVerifier`-аннотации.
        port: ITgStarsPayloadVerifier = verifier
        # Sanity: вызов через port-протокол — без ошибок типов.
        raw = verifier.serialize(
            pack_value="single",
            idempotency_seed="a" * 16,
            amount_native=50,
            currency=Currency.STARS,
        )
        result = port.verify(
            raw_payload=raw,
            provider_payment_id=_PROVIDER_PAYMENT_ID,
            amount_native=50,
            currency=Currency.STARS,
        )
        assert isinstance(result, StarsPayload)


class TestPayloadLenInError:
    def test_payload_len_reflects_raw_payload(self) -> None:
        verifier = _make_verifier()
        raw = "broken:payload"  # 14 chars
        with pytest.raises(InvalidStarsPayloadError) as exc_info:
            verifier.verify(
                raw_payload=raw,
                provider_payment_id=_PROVIDER_PAYMENT_ID,
                amount_native=50,
                currency=Currency.STARS,
            )
        assert exc_info.value.payload_len == 14
