"""Тесты `StarsPayload`-VO и `InvalidStarsPayloadError` (Спринт 4.1-D, шаг D.8.a).

Покрывают:

* `__post_init__`-invariant-ы `StarsPayload`: типы полей, формат
  `idempotency_seed` (`[A-Za-z0-9_-]{16,32}`), non-empty `pack_value`.
* frozen + slots-инвариант VO (нельзя мутировать; нет `__dict__`).
* hashable / equality по полям.
* `InvalidStarsPayloadError`: атрибуты `reason` / `payload_len`,
  наследование от `MonetizationDomainError` / `DomainError`,
  безопасная строковая репрезентация (`payload_len` в `str(err)`,
  но без самого payload-а).
"""

from __future__ import annotations

import dataclasses

import pytest

from pipirik_wars.domain.monetization import (
    InvalidStarsPayloadError,
    MonetizationDomainError,
    StarsPayload,
)
from pipirik_wars.shared.errors import DomainError


class TestStarsPayloadPostInit:
    """`__post_init__` сторожит invariant-ы pack_value / idempotency_seed."""

    @pytest.mark.parametrize(
        ("pack_value", "seed"),
        [
            ("single", "a" * 16),
            ("pack_10", "Aa0_-Bb1Cc2Dd3Ee"),
            ("single", "x" * 32),
            ("any_future_pack", "0123456789abcdef0123456789ABCDEF"),
        ],
    )
    def test_well_formed_payload_ok(self, pack_value: str, seed: str) -> None:
        payload = StarsPayload(pack_value=pack_value, idempotency_seed=seed)
        assert payload.pack_value == pack_value
        assert payload.idempotency_seed == seed

    def test_empty_pack_value_raises(self) -> None:
        with pytest.raises(ValueError, match="pack_value must be non-empty"):
            StarsPayload(pack_value="", idempotency_seed="a" * 16)

    @pytest.mark.parametrize("bad", [123, 1.5, b"single", None, object()])
    def test_non_str_pack_value_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="pack_value must be str"):
            StarsPayload(
                pack_value=bad,  # type: ignore[arg-type]
                idempotency_seed="a" * 16,
            )

    @pytest.mark.parametrize("bad", [123, 1.5, b"abc", None, object()])
    def test_non_str_idempotency_seed_raises(self, bad: object) -> None:
        with pytest.raises(TypeError, match="idempotency_seed must be str"):
            StarsPayload(
                pack_value="single",
                idempotency_seed=bad,  # type: ignore[arg-type]
            )

    @pytest.mark.parametrize(
        "bad_seed",
        [
            "",  # пустой
            "a" * 15,  # < 16
            "a" * 33,  # > 32
            "with space__not_ok",
            "tab\tinside_seed_x",
            "with/slash_not_ok",
            "with:colon_not_ok",
            "with.dot_not_ok",
            "юникод_не_допустим",
            "emoji-😀-not-allowed",
            "DROP TABLE payments",
        ],
    )
    def test_malformed_idempotency_seed_raises(self, bad_seed: str) -> None:
        with pytest.raises(ValueError, match=r"idempotency_seed must match"):
            StarsPayload(pack_value="single", idempotency_seed=bad_seed)


class TestStarsPayloadImmutability:
    """frozen + slots → нет `__dict__`, неизменяемость, hashability."""

    def test_payload_is_frozen_for_pack_value(self) -> None:
        payload = StarsPayload(pack_value="single", idempotency_seed="a" * 16)
        with pytest.raises(dataclasses.FrozenInstanceError):
            payload.pack_value = "pack_10"

    def test_payload_is_frozen_for_idempotency_seed(self) -> None:
        payload = StarsPayload(pack_value="single", idempotency_seed="a" * 16)
        with pytest.raises(dataclasses.FrozenInstanceError):
            payload.idempotency_seed = "b" * 16

    def test_payload_has_no_dict_due_to_slots(self) -> None:
        payload = StarsPayload(pack_value="single", idempotency_seed="a" * 16)
        # slots=True → нет `__dict__` (нулевой overhead) и набор
        # разрешённых атрибутов ограничен `__slots__`.
        assert not hasattr(payload, "__dict__")
        assert set(StarsPayload.__slots__) == {"pack_value", "idempotency_seed"}

    def test_payloads_with_same_values_compare_equal(self) -> None:
        a = StarsPayload(pack_value="single", idempotency_seed="abcd" * 4)
        b = StarsPayload(pack_value="single", idempotency_seed="abcd" * 4)
        assert a == b
        assert hash(a) == hash(b)

    def test_payloads_with_different_pack_compare_unequal(self) -> None:
        a = StarsPayload(pack_value="single", idempotency_seed="abcd" * 4)
        b = StarsPayload(pack_value="pack_10", idempotency_seed="abcd" * 4)
        assert a != b

    def test_payloads_with_different_seed_compare_unequal(self) -> None:
        a = StarsPayload(pack_value="single", idempotency_seed="abcd" * 4)
        b = StarsPayload(pack_value="single", idempotency_seed="efgh" * 4)
        assert a != b


class TestInvalidStarsPayloadError:
    """`InvalidStarsPayloadError` — машинно-читаемая ошибка верификации."""

    def test_attributes_exposed(self) -> None:
        err = InvalidStarsPayloadError(reason="hmac_mismatch", payload_len=42)
        assert err.reason == "hmac_mismatch"
        assert err.payload_len == 42

    def test_str_includes_reason_and_len_but_not_payload(self) -> None:
        err = InvalidStarsPayloadError(reason="malformed", payload_len=128)
        text = str(err)
        assert "malformed" in text
        assert "128" in text
        # Самого payload-а в repr-е быть не должно — это инвариант
        # безопасности (никаких HMAC-байт в logs).
        assert "raw" not in text

    def test_inherits_from_monetization_and_domain_error(self) -> None:
        err = InvalidStarsPayloadError(reason="empty", payload_len=0)
        assert isinstance(err, MonetizationDomainError)
        assert isinstance(err, DomainError)

    @pytest.mark.parametrize(
        "reason",
        [
            "empty",
            "too_long",
            "malformed",
            "bad_pack",
            "bad_seed",
            "bad_hmac",
            "hmac_mismatch",
        ],
    )
    def test_all_documented_reasons_constructible(self, reason: str) -> None:
        err = InvalidStarsPayloadError(reason=reason, payload_len=0)
        assert err.reason == reason

    def test_keyword_only_constructor(self) -> None:
        # Sanity-check: позиционные аргументы запрещены, чтобы не
        # перепутать `reason` и `payload_len`.
        with pytest.raises(TypeError):
            InvalidStarsPayloadError("malformed", 10)
