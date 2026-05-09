"""Тесты доменного picker-а рулетки `pick_roulette_outcome` (Спринт 3.5-A).

Структура аналогична `tests/unit/domain/inventory/test_enchant_picker.py`
(Спринт 3.4-A) — тот же `_bernoulli_bounds`-приём (3σ + аддитивный
флор `±10` от ожидаемого), та же интуиция «много прогонов на каждый
кейс, проверяем частоты в Bernoulli-границах».

Покрытие:

* **Forced-outcome** — конфиг с одним типом исхода `weight=1.0` всегда
  возвращает этот тип. Если `kind == LENGTH`, проверяется ещё и
  weighted-выбор бакета и `randint(min_cm, max_cm)` диапазон.
* **Bernoulli-частоты исходов** — все 5 типов на дефолтном балансе
  с `crypto_pool_empty=False` (10000 прогонов, 3σ-границы).
* **Bernoulli-частоты бакетов длины** — после исхода `LENGTH`
  4 бакета попадают в свои 3σ-границы.
* **`length_cm` в диапазоне выбранного бакета** — `randint(min_cm,
  max_cm)` всегда возвращает целое в `[min_cm, max_cm]`.
* **Перетекание `crypto_lot → length`** — при `crypto_pool_empty=True`
  частота `CRYPTO_LOT` строго `0`, а частота `LENGTH` сдвинута на
  weight `crypto_lot` (3σ-bound).
* **Crypto-pool not empty** — при `crypto_pool_empty=False` частота
  `CRYPTO_LOT` ≠ 0 (в 3σ-границе исходного веса).
* **Zero-weight outcome filtered** — конфиг, где один из исходов
  имеет `weight=0.0`, никогда не возвращает этот исход.
* **All-zero filter triggers `InvalidRouletteConfigError`** — если
  все веса исходов после фильтрации стали нулевыми (synthetic-кейс,
  pydantic-инвариант не должен такое пропустить, но defence-in-depth).
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from pipirik_wars.domain.balance.config import (
    RouletteFreeConfig,
    RouletteLengthBucket,
    RouletteOutcomeKind,
    RouletteOutcomeWeight,
)
from pipirik_wars.domain.roulette import (
    InvalidRouletteConfigError,
    RouletteOutcome,
    pick_roulette_outcome,
)
from tests.fakes.random import FakeRandom
from tests.unit.domain.balance.factories import build_valid_balance

_ROLLS = 10_000


def _bernoulli_bounds(p: float, *, n: int = _ROLLS) -> tuple[float, float]:
    """3σ-границы Bernoulli с аддитивным флором `±10` от ожидаемого.

    Идентично `tests/unit/domain/inventory/test_enchant_picker.py`
    — копия специально (тесты в разных доменах не должны делить
    test-utility между собой по соглашению проекта).
    """
    expected = p * n
    sigma = math.sqrt(n * p * (1 - p))
    delta = max(3 * sigma, 10.0)
    return expected - delta, expected + delta


def _free_config() -> RouletteFreeConfig:
    return build_valid_balance().roulette.free


# --------------------------------------------------------------------------- #
# Forced-outcome
# --------------------------------------------------------------------------- #


class TestForcedOutcomeKinds:
    """Конфиг с одним исходом `weight=1.0` → всегда этот исход."""

    @staticmethod
    def _config_with_only_kind(kind: RouletteOutcomeKind) -> RouletteFreeConfig:
        outcomes = tuple(
            RouletteOutcomeWeight(
                kind=k,
                weight=1.0 if k is kind else 0.0,
            )
            for k in RouletteOutcomeKind
        )
        return RouletteFreeConfig(
            cost_cm=100,
            min_thickness_level=2,
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
        outcome = pick_roulette_outcome(
            config=cfg,
            random=FakeRandom(seed=1),
            crypto_pool_empty=False,
        )
        assert outcome == RouletteOutcome(kind=RouletteOutcomeKind.ITEM)

    def test_forced_scroll_regular(self) -> None:
        cfg = self._config_with_only_kind(RouletteOutcomeKind.SCROLL_REGULAR)
        outcome = pick_roulette_outcome(
            config=cfg,
            random=FakeRandom(seed=1),
            crypto_pool_empty=False,
        )
        assert outcome.kind is RouletteOutcomeKind.SCROLL_REGULAR
        assert outcome.length_cm is None

    def test_forced_scroll_blessed(self) -> None:
        cfg = self._config_with_only_kind(RouletteOutcomeKind.SCROLL_BLESSED)
        outcome = pick_roulette_outcome(
            config=cfg,
            random=FakeRandom(seed=1),
            crypto_pool_empty=False,
        )
        assert outcome.kind is RouletteOutcomeKind.SCROLL_BLESSED

    def test_forced_crypto_lot_when_pool_not_empty(self) -> None:
        cfg = self._config_with_only_kind(RouletteOutcomeKind.CRYPTO_LOT)
        outcome = pick_roulette_outcome(
            config=cfg,
            random=FakeRandom(seed=1),
            crypto_pool_empty=False,
        )
        assert outcome.kind is RouletteOutcomeKind.CRYPTO_LOT

    def test_forced_length_picks_bucket_and_random_int(self) -> None:
        cfg = self._config_with_only_kind(RouletteOutcomeKind.LENGTH)
        for seed in range(50):
            outcome = pick_roulette_outcome(
                config=cfg,
                random=FakeRandom(seed=seed),
                crypto_pool_empty=False,
            )
            assert outcome.kind is RouletteOutcomeKind.LENGTH
            assert outcome.length_cm is not None
            assert 10 <= outcome.length_cm <= 20


# --------------------------------------------------------------------------- #
# Bernoulli-частоты на дефолтном балансе
# --------------------------------------------------------------------------- #


class TestKindFrequenciesOnDefaultBalance:
    """Все 5 типов исходов попадают в 3σ-Bernoulli границы."""

    def test_outcomes_within_bernoulli_bounds_no_crypto_pool_drain(self) -> None:
        cfg = _free_config()
        rng = FakeRandom(seed=42)
        counter: Counter[RouletteOutcomeKind] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_roulette_outcome(
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
        cfg = _free_config()
        rng = FakeRandom(seed=7)
        counter: Counter[RouletteOutcomeKind] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_roulette_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=False,
            )
            counter[outcome.kind] += 1
        assert sum(counter.values()) == _ROLLS


class TestLengthBucketFrequencies:
    """Бакеты длины при `kind == LENGTH` попадают в 3σ-границы."""

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
        default = _free_config()
        cfg = RouletteFreeConfig(
            cost_cm=default.cost_cm,
            min_thickness_level=default.min_thickness_level,
            outcomes=outcomes,
            length_buckets=default.length_buckets,
        )
        rng = FakeRandom(seed=11)
        counter: Counter[str] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_roulette_outcome(
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
        # Бакеты `medium` и `good` имеют пересекающиеся границы с
        # `small` и `medium` соответственно (50/150 cm). При попадании
        # точно на границу `length_cm == 50` обратимся к `small` (он
        # первый в списке) — поэтому считаем именно по «первый
        # подходящий бакет», как делает product (длина показана игроку
        # как «маленькая», если она 50 cm).
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
        cfg = _free_config()
        rng = FakeRandom(seed=13)
        counter: Counter[RouletteOutcomeKind] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_roulette_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=True,
            )
            counter[outcome.kind] += 1
        assert counter[RouletteOutcomeKind.CRYPTO_LOT] == 0

    def test_length_weight_increased_by_crypto_weight(self) -> None:
        cfg = _free_config()
        weight_by_kind = {o.kind: o.weight for o in cfg.outcomes}
        crypto_weight = weight_by_kind[RouletteOutcomeKind.CRYPTO_LOT]
        length_weight = weight_by_kind[RouletteOutcomeKind.LENGTH]
        expected_length_p = length_weight + crypto_weight
        rng = FakeRandom(seed=17)
        counter: Counter[RouletteOutcomeKind] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_roulette_outcome(
                config=cfg,
                random=rng,
                crypto_pool_empty=True,
            )
            counter[outcome.kind] += 1
        low, high = _bernoulli_bounds(expected_length_p)
        count = counter[RouletteOutcomeKind.LENGTH]
        assert low <= count <= high, (
            f"length: count={count}, expected_in=[{low:.1f}, {high:.1f}], p={expected_length_p}",
        )

    def test_crypto_lot_can_drop_when_pool_not_empty(self) -> None:
        cfg = _free_config()
        weight_by_kind = {o.kind: o.weight for o in cfg.outcomes}
        crypto_weight = weight_by_kind[RouletteOutcomeKind.CRYPTO_LOT]
        rng = FakeRandom(seed=19)
        counter: Counter[RouletteOutcomeKind] = Counter()
        for _ in range(_ROLLS):
            outcome = pick_roulette_outcome(
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
        # Конфиг: только `length` и `item` имеют ненулевой вес;
        # остальные = 0.0. Сумма = 1.0, валидаторы прокатывают.
        outcomes = (
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.LENGTH, weight=0.5),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.ITEM, weight=0.5),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.SCROLL_REGULAR, weight=0.0),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.SCROLL_BLESSED, weight=0.0),
            RouletteOutcomeWeight(kind=RouletteOutcomeKind.CRYPTO_LOT, weight=0.0),
        )
        cfg = RouletteFreeConfig(
            cost_cm=100,
            min_thickness_level=2,
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
            outcome = pick_roulette_outcome(
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
        # Бакет `gone` имеет нулевой вес → ни разу не выпадет.
        buckets = (
            RouletteLengthBucket(name="gone", min_cm=1000, max_cm=2000, weight=0.0),
            RouletteLengthBucket(name="alive", min_cm=10, max_cm=20, weight=1.0),
        )
        cfg = RouletteFreeConfig(
            cost_cm=100,
            min_thickness_level=2,
            outcomes=outcomes,
            length_buckets=buckets,
        )
        rng = FakeRandom(seed=29)
        for _ in range(200):
            outcome = pick_roulette_outcome(
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
        # Конфиг с весами, которые после `crypto_pool_empty=True` стали
        # нулевыми. Pydantic-инвариант не должен такое допустить, но
        # picker дополнительно сторожит. Чтобы добраться до этой ветки,
        # нужно обойти pydantic — используем `model_construct` (без
        # валидаторов), ибо обычное `RouletteFreeConfig(...)` отвергнет
        # сумма-весов != 1.0.
        outcomes = (RouletteOutcomeWeight(kind=RouletteOutcomeKind.CRYPTO_LOT, weight=1.0),)
        cfg = RouletteFreeConfig.model_construct(
            cost_cm=100,
            min_thickness_level=2,
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
        # При `crypto_pool_empty=True` единственный исход (CRYPTO_LOT)
        # вычитается из списка — остаётся пусто → ошибка.
        with pytest.raises(InvalidRouletteConfigError, match="all roulette weights are zero"):
            pick_roulette_outcome(
                config=cfg,
                random=FakeRandom(seed=31),
                crypto_pool_empty=True,
            )
