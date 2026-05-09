"""Тесты VO `RouletteOutcome` + `RouletteSpin` (Спринт 3.5-A/B).

Покрывают invariant-проверки `__post_init__` и неизменяемость VO.
Сам machine-id-enum `RouletteOutcomeKind` не тестируется отдельно —
он тривиальный StrEnum, его значения проверяются интеграционным
тестом `tests/integration/test_balance_yaml.py` (через парсинг
`config/balance.yaml::roulette.free.outcomes`).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.roulette import RouletteOutcome, RouletteSpin
from pipirik_wars.domain.roulette.entities import RouletteOutcomeKind


class TestRouletteOutcomePostInit:
    """`__post_init__` сторожит invariant `kind ↔ length_cm`."""

    def test_length_kind_with_length_cm_ok(self) -> None:
        outcome = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42)
        assert outcome.kind is RouletteOutcomeKind.LENGTH
        assert outcome.length_cm == 42

    def test_length_kind_without_length_cm_raises(self) -> None:
        with pytest.raises(ValueError, match="requires length_cm"):
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH)

    def test_length_kind_with_zero_length_cm_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 1"):
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=0)

    def test_length_kind_with_negative_length_cm_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 1"):
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=-5)

    @pytest.mark.parametrize(
        "kind",
        [
            RouletteOutcomeKind.ITEM,
            RouletteOutcomeKind.SCROLL_REGULAR,
            RouletteOutcomeKind.SCROLL_BLESSED,
            RouletteOutcomeKind.CRYPTO_LOT,
        ],
    )
    def test_non_length_kind_without_length_cm_ok(
        self,
        kind: RouletteOutcomeKind,
    ) -> None:
        outcome = RouletteOutcome(kind=kind)
        assert outcome.kind is kind
        assert outcome.length_cm is None

    @pytest.mark.parametrize(
        "kind",
        [
            RouletteOutcomeKind.ITEM,
            RouletteOutcomeKind.SCROLL_REGULAR,
            RouletteOutcomeKind.SCROLL_BLESSED,
            RouletteOutcomeKind.CRYPTO_LOT,
        ],
    )
    def test_non_length_kind_with_length_cm_raises(
        self,
        kind: RouletteOutcomeKind,
    ) -> None:
        with pytest.raises(ValueError, match="must have length_cm=None"):
            RouletteOutcome(kind=kind, length_cm=10)


class TestRouletteOutcomeImmutability:
    """frozen-VO нельзя мутировать."""

    def test_outcome_is_frozen(self) -> None:
        outcome = RouletteOutcome(kind=RouletteOutcomeKind.ITEM)
        with pytest.raises(dataclasses.FrozenInstanceError):
            outcome.length_cm = 5

    def test_outcomes_with_same_fields_compare_equal(self) -> None:
        a = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42)
        b = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42)
        assert a == b
        assert hash(a) == hash(b)

    def test_outcomes_with_different_fields_compare_unequal(self) -> None:
        a = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42)
        b = RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=43)
        assert a != b


_FIXED_TS = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)


class TestRouletteSpinPostInit:
    """`__post_init__` сторожит обязательные доменные инварианты записи."""

    def test_valid_length_spin_ok(self) -> None:
        spin = RouletteSpin(
            player_id=42,
            occurred_at=_FIXED_TS,
            outcome=RouletteOutcome(
                kind=RouletteOutcomeKind.LENGTH,
                length_cm=87,
            ),
            idempotency_key="roulette_free:42:msg-101",
        )
        assert spin.player_id == 42
        assert spin.occurred_at == _FIXED_TS
        assert spin.kind is RouletteOutcomeKind.LENGTH
        assert spin.length_cm == 87
        assert spin.idempotency_key == "roulette_free:42:msg-101"

    def test_valid_non_length_spin_ok(self) -> None:
        spin = RouletteSpin(
            player_id=7,
            occurred_at=_FIXED_TS,
            outcome=RouletteOutcome(kind=RouletteOutcomeKind.SCROLL_BLESSED),
            idempotency_key="roulette_free:7:msg-99",
        )
        assert spin.kind is RouletteOutcomeKind.SCROLL_BLESSED
        assert spin.length_cm is None

    @pytest.mark.parametrize("bad_player_id", [0, -1, -42])
    def test_non_positive_player_id_raises(self, bad_player_id: int) -> None:
        with pytest.raises(ValueError, match="player_id must be > 0"):
            RouletteSpin(
                player_id=bad_player_id,
                occurred_at=_FIXED_TS,
                outcome=RouletteOutcome(kind=RouletteOutcomeKind.ITEM),
                idempotency_key="x",
            )

    def test_naive_datetime_raises(self) -> None:
        naive_ts = datetime(2026, 5, 10, 12, 0, 0)
        with pytest.raises(ValueError, match="must be timezone-aware"):
            RouletteSpin(
                player_id=42,
                occurred_at=naive_ts,
                outcome=RouletteOutcome(kind=RouletteOutcomeKind.ITEM),
                idempotency_key="x",
            )

    def test_empty_idempotency_key_raises(self) -> None:
        with pytest.raises(ValueError, match="idempotency_key"):
            RouletteSpin(
                player_id=42,
                occurred_at=_FIXED_TS,
                outcome=RouletteOutcome(kind=RouletteOutcomeKind.ITEM),
                idempotency_key="",
            )


class TestRouletteSpinImmutability:
    """frozen-VO: `RouletteSpin` нельзя мутировать; сравнение по полям."""

    def _make(self, **overrides: object) -> RouletteSpin:
        defaults: dict[str, object] = {
            "player_id": 42,
            "occurred_at": _FIXED_TS,
            "outcome": RouletteOutcome(kind=RouletteOutcomeKind.ITEM),
            "idempotency_key": "roulette_free:42:msg-1",
        }
        defaults.update(overrides)
        return RouletteSpin(**defaults)  # type: ignore[arg-type]

    def test_spin_is_frozen(self) -> None:
        spin = self._make()
        with pytest.raises(dataclasses.FrozenInstanceError):
            spin.idempotency_key = "other"  # type: ignore[misc]

    def test_spins_with_same_fields_compare_equal(self) -> None:
        a = self._make()
        b = self._make()
        assert a == b
        assert hash(a) == hash(b)

    def test_spins_with_different_fields_compare_unequal(self) -> None:
        a = self._make(idempotency_key="key-a")
        b = self._make(idempotency_key="key-b")
        assert a != b

    def test_kind_and_length_cm_properties_delegate_to_outcome(self) -> None:
        spin = self._make(
            outcome=RouletteOutcome(
                kind=RouletteOutcomeKind.LENGTH,
                length_cm=150,
            ),
        )
        assert spin.kind is RouletteOutcomeKind.LENGTH
        assert spin.length_cm == 150
