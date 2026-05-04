"""Тесты `FakeRandom`."""

from __future__ import annotations

from collections import Counter

import pytest

from tests.fakes import FakeRandom


class TestFakeRandom:
    def test_randint_inclusive(self) -> None:
        rng = FakeRandom(seed=42)
        results = [rng.randint(1, 3) for _ in range(200)]
        assert set(results) == {1, 2, 3}

    def test_randint_low_greater_than_high_raises(self) -> None:
        rng = FakeRandom()
        with pytest.raises(ValueError, match="low > high"):
            rng.randint(10, 5)

    def test_uniform_in_range(self) -> None:
        rng = FakeRandom(seed=42)
        for _ in range(100):
            x = rng.uniform(1.0, 20.0)
            assert 1.0 <= x <= 20.0

    def test_uniform_low_greater_than_high_raises(self) -> None:
        rng = FakeRandom()
        with pytest.raises(ValueError, match="low > high"):
            rng.uniform(20.0, 1.0)

    def test_choice_picks_from_sequence(self) -> None:
        rng = FakeRandom(seed=42)
        items = ["a", "b", "c"]
        for _ in range(50):
            assert rng.choice(items) in items

    def test_choice_empty_raises(self) -> None:
        rng = FakeRandom()
        with pytest.raises(ValueError, match="empty"):
            rng.choice([])

    def test_weighted_choice_respects_weights_in_aggregate(self) -> None:
        # 50/35/15 — те же веса леса в balance.yaml.
        rng = FakeRandom(seed=42)
        items = ["scarce", "normal", "abundant"]
        weights = [50, 35, 15]
        counter: Counter[str] = Counter(rng.weighted_choice(items, weights) for _ in range(5_000))
        # Средние частоты должны быть в окрестности заданных весов.
        assert 0.45 < counter["scarce"] / 5_000 < 0.55
        assert 0.30 < counter["normal"] / 5_000 < 0.40
        assert 0.10 < counter["abundant"] / 5_000 < 0.20

    def test_weighted_choice_empty_raises(self) -> None:
        rng = FakeRandom()
        with pytest.raises(ValueError, match="empty"):
            rng.weighted_choice([], [])

    def test_weighted_choice_length_mismatch_raises(self) -> None:
        rng = FakeRandom()
        with pytest.raises(ValueError, match="length mismatch"):
            rng.weighted_choice(["a", "b"], [1])

    def test_weighted_choice_nonpositive_weight_raises(self) -> None:
        rng = FakeRandom()
        with pytest.raises(ValueError, match="positive"):
            rng.weighted_choice(["a", "b"], [1, 0])

    def test_deterministic_uint_is_stable(self) -> None:
        rng = FakeRandom()
        # Тот же seed → тот же результат, независимо от состояния RNG.
        a = rng.deterministic_uint("clan-123|2026-05-04", 24)
        b = rng.deterministic_uint("clan-123|2026-05-04", 24)
        assert a == b
        assert 0 <= a < 24

    def test_deterministic_uint_modulo_must_be_positive(self) -> None:
        rng = FakeRandom()
        with pytest.raises(ValueError, match="positive"):
            rng.deterministic_uint("x", 0)

    def test_deterministic_uint_distributes_across_clans(self) -> None:
        # Разные seed-ы → не одно и то же значение (вероятностно).
        rng = FakeRandom()
        offsets = {rng.deterministic_uint(f"clan-{i}|2026-05-04", 24) for i in range(50)}
        # Среди 50 разных кланов должно быть хотя бы 5 разных offset-ов.
        assert len(offsets) >= 5
