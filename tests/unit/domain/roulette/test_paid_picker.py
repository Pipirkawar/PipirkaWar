"""Тесты доменного picker-а платной рулетки `pick_paid_outcome` (Спринт 4.1-A).

Структура повторяет `tests/unit/domain/roulette/test_picker.py` (free-рулетка):
тот же `_bernoulli_bounds`-приём (3σ + аддитивный флор `±10`), тот же набор
кейсов (forced-outcome, частоты исходов, частоты бакетов длины, перетекание
crypto-pool, zero-weight филтр, all-zero defence). Различие — только
конфиг (`RoulettePaidConfig` с весами §12.5.2 vs `RouletteFreeConfig` §12.4.2).

Дополнительно проверяется:

* **Empirical E[CM | spin, paid]** — на 10000 спинов средний CM-выигрыш
  попадает в `26.7 ± δ` (δ — щедрая граница на стандартную ошибку
  среднего CM). Это integration-mode проверка экономики §12.5.2.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from pipirik_wars.domain.balance.config import (
    RouletteLengthBucket,
    RouletteOutcomeKind,
    RouletteOutcomeWeight,
    RoulettePaidConfig,
)
from pipirik_wars.domain.roulette import (
    InvalidRouletteConfigError,
    RouletteOutcome,
    pick_paid_outcome,
)
from tests.fakes.random import FakeRandom

_ROLLS = 10_000


def _bernoulli_bounds(p: float, *, n: int = _ROLLS) -> tuple[float, float]:
    """3σ-границы Bernoulli с аддитивным флором `±10`."""
    expected = p * n
    sigma = math.sqrt(n * p * (1 - p))
    delta = max(3 * sigma, 10.0)
    return expected - delta, expected + delta


def _paid_config_default() -> RoulettePaidConfig:
    """Дефолтный paid-конфиг по ГДД §12.5.2 (стартовые значения)."""
    return RoulettePaidConfig(
        cost_stars_single=1,
        cost_stars_pack10=9,
        pack10_spins=10,
        min_thickness_level=1,
        outcomes=(
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.LENGTH, weight=0.550),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.ITEM, weight=0.200),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.SCROLL_REGULAR, weight=0.180),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.SCROLL_BLESSED, weight=0.050),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.CRYPTO_LOT, weight=0.020),
        ),
        length_buckets=(
            RouletteLengthBucket(name="small", min_cm=10, max_cm=50, weight=0.800),
            RouletteLengthBucket(name="medium", min_cm=50, max_cm=150, weight=0.170),
            RouletteLengthBucket(name="good", min_cm=150, max_cm=300, weight=0.025),
            RouletteLengthBucket(name="big", min_cm=300, max_cm=500, weight=0.005),
        ),
    )


# --------------------------------------------------------------------------- #
# Forced-outcome
# --------------------------------------------------------------------------- #


class TestForcedOutcomeKinds:
    """Конфиг с одним paid-исходом `weight=1.0` → всегда этот исход."""

    @staticmethod
    def _config_with_only_kind(kind: RouletteOutcomeKind) -> RoulettePaidConfig:
        outcomes = tuple(
            RouletteOutcomeWeight(
                kind=k,
                weight=1.0 if k is kind else 0.0,
            )
            for k in RouletteOutcomeKind
        )
        return RoulettePaidConfig(
            cost_stars_single=1,
            cost_stars_pack10=9,
            pack10_spins=10,
            min_thickness_level=1,
            outcomes=outcomes,
            length_buckets=(
                RouletteLengthBucket(
                    name="only",
                    min_cm=10,
                    max_cm=20,
                    weight=1.0,
                ),
            ),
        )

    def test_forced_item(self) -> None:
        cfg = self._config_with_only_kind(RouletteOutcomeKind.ITEM)
        outcome = pick_paid_outcome(
            config=cfg,
            random=FakeRandom(seed=1),
            crypto_pool_empty=False,
        )
        assert outcome == RouletteOutcome(kind=RouletteOutcomeKind.ITEM)

    def test_forced_scroll_regular(self) -> None:
        cfg = self._config_with_only_kind(RouletteOutcomeKind.SCROLL_REGULAR)
        outcome = pick_paid_outcome(
            config=cfg,
            random=FakeRandom(seed=1),
            crypto_pool_empty=False,
        )
        assert outcome.kind is RouletteOutcomeKind.SCROLL_REGULAR
        assert outcome.length_cm is None

    def test_forced_scroll_blessed(self) -> None:
        cfg = self._config_with_only_kind(RouletteOutcomeKind.SCROLL_BLESSED)
        outcome = pick_paid_outcome(
            config=cfg,
            random=FakeRandom(seed=1),
            crypto_pool_empty=False,
        )
        assert outcome.kind is RouletteOutcomeKind.SCROLL_BLESSED

    def test_forced_crypto_lot_when_pool_not_empty(self) -> None:
        cfg = self._config_with_only_kind(RouletteOutcomeKind.CRYPTO_LOT)
        outcome = pick_paid_outcome(
            config=cfg,
            random=FakeRandom(seed=1),
            crypto_pool_empty=False,
        )
        assert outcome.kind is RouletteOutcomeKind.CRYPTO_LOT

    def test_forced_length_picks_bucket_and_random_int(self) -> None:
        cfg = self._config_with_only_kind(RouletteOutcomeKind.LENGTH)
        for seed in range(50):
            outcome = pick_paid_outcome(
                config=cfg,
                random=FakeRandom(seed=seed),
                crypto_pool_empty=False,
            )
            assert outcome.kind is RouletteOutcomeKind.LENGTH
            assert outcome.length_cm is not None
            assert 10 <= outcome.length_cm <= 20


# --------------------------------------------------------------------------- #
# Bernoulli-частоты на дефолтных весах §12.5.2
# --------------------------------------------------------------------------- #


class TestKindFrequenciesOnDefaultPaidWeights:
    """Все 5 типов исходов попадают в 3σ-Bernoulli границы (paid веса §12.5.2)."""

    def test_outcomes_within_bernoulli_bounds_no_crypto_pool_drain(self) -> None:
        cfg = _paid_config_default()
        rng = FakeRandom(seed=42)
        counter: Counter[RouletteOutcomeKind] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_paid_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=False,
            )
            counter[outcome.kind] += 1
        weight_by_kind = {o.kind: o.weight for o in cfg.outcomes}
        for kind, weight in weight_by_kind.items():
            low, high = _bernoulli_bounds(weight)
            count = counter[kind]
            assert low <= count <= high, (
                f"{kind.value}: count={count}, expected_in=[{low:.1f}, {high:.1f}], weight={weight}"
            )

    def test_total_count_equals_rolls(self) -> None:
        cfg = _paid_config_default()
        rng = FakeRandom(seed=7)
        counter: Counter[RouletteOutcomeKind] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_paid_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=False,
            )
            counter[outcome.kind] += 1
        assert sum(counter.values()) == _ROLLS


class TestLengthBucketFrequencies:
    """Бакеты длины при `kind == LENGTH` попадают в 3σ-границы (paid веса §12.5.2)."""

    def test_buckets_within_bernoulli_bounds(self) -> None:
        # Выкручиваем `length` weight на 1.0, чтобы все прогоны попадали
        # в length-ветку и можно было считать частоты бакетов.
        outcomes = tuple(
            RouletteOutcomeWeight(
                kind=k,
                weight=1.0 if k is RouletteOutcomeKind.LENGTH else 0.0,
            )
            for k in RouletteOutcomeKind
        )
        default = _paid_config_default()
        cfg = RoulettePaidConfig(
            cost_stars_single=default.cost_stars_single,
            cost_stars_pack10=default.cost_stars_pack10,
            pack10_spins=default.pack10_spins,
            min_thickness_level=default.min_thickness_level,
            outcomes=outcomes,
            length_buckets=default.length_buckets,
        )
        rng = FakeRandom(seed=11)
        counter: Counter[str] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_paid_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=False,
            )
            assert outcome.kind is RouletteOutcomeKind.LENGTH
            assert outcome.length_cm is not None
            for bucket in cfg.length_buckets:
                if bucket.min_cm <= outcome.length_cm <= bucket.max_cm:
                    counter[bucket.name] += 1
                    break
        for bucket in cfg.length_buckets:
            low, high = _bernoulli_bounds(bucket.weight)
            count = counter[bucket.name]
            assert low <= count <= high, (
                f"bucket {bucket.name!r}: count={count}, "
                f"expected_in=[{low:.1f}, {high:.1f}], weight={bucket.weight}"
            )


# --------------------------------------------------------------------------- #
# Crypto pool drain (`crypto_lot → length`)
# --------------------------------------------------------------------------- #


class TestCryptoPoolDrain:
    """Перетекание веса `CRYPTO_LOT` на `LENGTH` при пустом крипто-пуле."""

    def test_crypto_lot_never_picked_when_pool_empty(self) -> None:
        cfg = _paid_config_default()
        rng = FakeRandom(seed=13)
        counter: Counter[RouletteOutcomeKind] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_paid_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=True,
            )
            counter[outcome.kind] += 1
        assert counter[RouletteOutcomeKind.CRYPTO_LOT] == 0

    def test_length_weight_increased_by_crypto_weight(self) -> None:
        cfg = _paid_config_default()
        weight_by_kind = {o.kind: o.weight for o in cfg.outcomes}
        crypto_weight = weight_by_kind[RouletteOutcomeKind.CRYPTO_LOT]
        length_weight = weight_by_kind[RouletteOutcomeKind.LENGTH]
        expected_length_p = length_weight + crypto_weight
        rng = FakeRandom(seed=17)
        counter: Counter[RouletteOutcomeKind] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_paid_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=True,
            )
            counter[outcome.kind] += 1
        low, high = _bernoulli_bounds(expected_length_p)
        count = counter[RouletteOutcomeKind.LENGTH]
        assert low <= count <= high, (
            f"length: count={count}, expected_in=[{low:.1f}, {high:.1f}], p={expected_length_p}"
        )

    def test_crypto_lot_can_drop_when_pool_not_empty(self) -> None:
        cfg = _paid_config_default()
        weight_by_kind = {o.kind: o.weight for o in cfg.outcomes}
        crypto_weight = weight_by_kind[RouletteOutcomeKind.CRYPTO_LOT]
        rng = FakeRandom(seed=19)
        counter: Counter[RouletteOutcomeKind] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_paid_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=False,
            )
            counter[outcome.kind] += 1
        low, high = _bernoulli_bounds(crypto_weight)
        count = counter[RouletteOutcomeKind.CRYPTO_LOT]
        assert low <= count <= high, (
            f"crypto_lot: count={count}, expected_in=[{low:.1f}, {high:.1f}], p={crypto_weight}"
        )


# --------------------------------------------------------------------------- #
# Zero-weight filter / all-zero defence
# --------------------------------------------------------------------------- #


class TestZeroWeightFiltering:
    """Pydantic не запрещает `weight=0.0` для отдельных исходов / бакетов."""

    def test_zero_weight_outcome_never_picked(self) -> None:
        outcomes = (
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.LENGTH, weight=0.5),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.ITEM, weight=0.5),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.SCROLL_REGULAR, weight=0.0),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.SCROLL_BLESSED, weight=0.0),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.CRYPTO_LOT, weight=0.0),
        )
        cfg = RoulettePaidConfig(
            cost_stars_single=1,
            cost_stars_pack10=9,
            pack10_spins=10,
            min_thickness_level=1,
            outcomes=outcomes,
            length_buckets=(
                RouletteLengthBucket(
                    name="only",
                    min_cm=1,
                    max_cm=10,
                    weight=1.0,
                ),
            ),
        )
        rng = FakeRandom(seed=23)
        seen: set[RouletteOutcomeKind] = set()
        for _ in range(_ROLLS):
            outcome = pick_paid_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=False,
            )
            seen.add(outcome.kind)
        assert seen == {RouletteOutcomeKind.LENGTH, RouletteOutcomeKind.ITEM}

    def test_zero_weight_bucket_never_picked(self) -> None:
        outcomes = tuple(
            RouletteOutcomeWeight(
                kind=k,
                weight=1.0 if k is RouletteOutcomeKind.LENGTH else 0.0,
            )
            for k in RouletteOutcomeKind
        )
        buckets = (
            RouletteLengthBucket(name="gone", min_cm=1000, max_cm=2000, weight=0.0),
            RouletteLengthBucket(name="alive", min_cm=10, max_cm=20, weight=1.0),
        )
        cfg = RoulettePaidConfig(
            cost_stars_single=1,
            cost_stars_pack10=9,
            pack10_spins=10,
            min_thickness_level=1,
            outcomes=outcomes,
            length_buckets=buckets,
        )
        rng = FakeRandom(seed=29)
        for _ in range(200):
            outcome = pick_paid_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=False,
            )
            assert outcome.kind is RouletteOutcomeKind.LENGTH
            assert outcome.length_cm is not None
            assert 10 <= outcome.length_cm <= 20


class TestInvalidConfigDefence:
    """Defence-in-depth: при битом runtime-конфиге picker бросает явную ошибку."""

    def test_all_zero_outcomes_raises(self) -> None:
        # Конфиг, в котором при `crypto_pool_empty=True` остаются только нули.
        # Pydantic не должен такое допустить, но picker сторожит. Чтобы обойти
        # pydantic — `model_construct` (без валидаторов).
        outcomes = (RouletteOutcomeWeight(kind=RouletteOutcomeKind.CRYPTO_LOT, weight=1.0),)
        cfg = RoulettePaidConfig.model_construct(
            cost_stars_single=1,
            cost_stars_pack10=9,
            pack10_spins=10,
            min_thickness_level=1,
            outcomes=outcomes,
            length_buckets=(
                RouletteLengthBucket(
                    name="only",
                    min_cm=1,
                    max_cm=10,
                    weight=1.0,
                ),
            ),
        )
        with pytest.raises(InvalidRouletteConfigError, match="all roulette weights are zero"):
            pick_paid_outcome(
                config=cfg,
                random=FakeRandom(seed=31),
                crypto_pool_empty=True,
            )


# --------------------------------------------------------------------------- #
# E[CM | spin, paid] на 10000 прогонах ≈ 26.7 см (ГДД §12.5.2)
# --------------------------------------------------------------------------- #


class TestExpectedCmGain:
    """ГДД §12.5.2: `E[CM | spin, paid] = 0.550 · 48.6 = 26.7 см`.

    На 10000 спинов средний `length_cm` (с учётом нулей для не-LENGTH-исходов)
    должен попасть в `26.7 ± δ`. Граница δ — щедрая: стандартное отклонение
    одной выборки `σ_X ≈ 60 см` (грубо), стандартная ошибка среднего на
    n=10000 — `σ_X / sqrt(n) ≈ 0.6 см`. Берём 5σ-границу `±3 см` для
    устойчивости теста на разных seed-ах.
    """

    @pytest.mark.parametrize("seed", [42, 7, 11, 17, 19])
    def test_average_cm_per_spin_close_to_26_7(self, seed: int) -> None:
        cfg = _paid_config_default()
        rng = FakeRandom(seed=seed)
        total_cm = 0
        for _ in range(_ROLLS):
            outcome = pick_paid_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=False,
            )
            if outcome.kind is RouletteOutcomeKind.LENGTH:
                assert outcome.length_cm is not None
                total_cm += outcome.length_cm
        avg = total_cm / _ROLLS
        # Ожидаемое: 26.7 см. Допуск ±3 см (≈5σ для n=10000).
        assert 23.7 <= avg <= 29.7, (
            f"E[CM | spin, paid] = {avg:.2f}, expected ≈ 26.7 ± 3.0 (seed={seed})"
        )
