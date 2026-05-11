"""Тесты picker-а крипто-приза в free + paid рулетках (Спринт 4.1-C, шаг C.5).

Фокус: `pick_roulette_outcome` / `pick_paid_outcome` принимают
`active_lots: Sequence[PrizeLot]`. Когда weighted-choice выбрал
`CRYPTO_LOT` и `active_lots` непуст → picker выбирает случайный лот
через тот же `IRandom.choice(active_lots)` и возвращает
`RouletteOutcome.crypto_lot(lot_id=...)`. Когда `active_lots` пуст —
fallback `CRYPTO_LOT → LENGTH` (см. `_roll_kind`-механику).

Структура аналогична `tests/unit/domain/roulette/test_picker.py`:
`FakeRandom(seed=...)` даёт детерминированный контроль распределений
на каждом seed-е, multi-roll Bernoulli-эксперименты использовать
не нужно (`_roll_crypto_lot` — единственная новая ветка, она
тривиальна).

Покрытие:

* **3 валюты** (`STARS` / `TON_NANO` / `USDT_DECIMAL`) — lot выбирается
  одинаково независимо от валюты (picker оперирует только `lot.id`).
* **Single-lot pool** — `random.choice([single])` всегда возвращает
  тот же лот, `outcome.lot_id == single.id`.
* **Multi-lot pool, deterministic seed** — `FakeRandom(seed=...)`
  выбирает один лот из набора, повтор того же seed-а возвращает
  тот же лот (детерминизм).
* **Multi-lot pool, distribution across seeds** — на 1000 прогонов
  всех seed-ов lot выбирается с примерно равной частотой
  (Bernoulli-bound на uniform distribution).
* **Free picker** — те же гарантии, что и paid.
* **Empty active_lots** — picker никогда не вернёт `CRYPTO_LOT`
  (перетекание `CRYPTO_LOT → LENGTH` через `_roll_kind`).
* **Lot with `id is None`** — defence-in-depth, `InvalidRouletteConfigError`
  (контракт `IPrizeLotRepository.list_active` нарушен).
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.balance.config import (
    RouletteFreeConfig,
    RouletteLengthBucket,
    RouletteOutcomeKind,
    RouletteOutcomeWeight,
    RoulettePaidConfig,
)
from pipirik_wars.domain.monetization import (
    Currency,
    FeeBufferAmount,
    PrizeLot,
    PrizeLotStatus,
)
from pipirik_wars.domain.roulette import (
    InvalidRouletteConfigError,
    RouletteOutcome,
    pick_paid_outcome,
    pick_roulette_outcome,
)
from tests.fakes.random import FakeRandom

_DUMMY_NOW = datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC)

_CURRENCY_AMOUNTS: dict[Currency, int] = {
    # Минимально-достаточные суммы под `amount_native > fee_buffer_native`-invariant
    # `PrizeLot`. Конкретные значения picker-у не важны — он смотрит только `id`.
    Currency.STARS: 100,
    Currency.TON_NANO: 1_000_000_000,
    Currency.USDT_DECIMAL: 1_000_000,
}


def _lot(
    *,
    lot_id: int,
    currency: Currency = Currency.TON_NANO,
) -> PrizeLot:
    """Persisted-лот с конкретным `lot_id` под `random.choice`-тесты."""
    return PrizeLot(
        id=lot_id,
        currency=currency,
        amount_native=_CURRENCY_AMOUNTS[currency],
        fee_buffer_native=FeeBufferAmount(0),
        status=PrizeLotStatus.ACTIVE,
        created_at=_DUMMY_NOW,
        claimed_at=None,
    )


def _forced_crypto_free_config() -> RouletteFreeConfig:
    """Free-конфиг, где `CRYPTO_LOT.weight = 1.0`, остальные `0.0`.

    `weighted_choice` гарантированно выберет `CRYPTO_LOT` → picker
    зайдёт в ветку `_roll_crypto_lot`.
    """
    outcomes = tuple(
        RouletteOutcomeWeight(
            kind=k,
            weight=1.0 if k is RouletteOutcomeKind.CRYPTO_LOT else 0.0,
        )
        for k in RouletteOutcomeKind
    )
    return RouletteFreeConfig(
        cost_cm=100,
        min_thickness_level=2,
        outcomes=outcomes,
        length_buckets=(RouletteLengthBucket(name="only", min_cm=1, max_cm=10, weight=1.0),),
    )


def _forced_crypto_paid_config() -> RoulettePaidConfig:
    """Paid-конфиг, где `CRYPTO_LOT.weight = 1.0`, остальные `0.0`."""
    outcomes = tuple(
        RouletteOutcomeWeight(
            kind=k,
            weight=1.0 if k is RouletteOutcomeKind.CRYPTO_LOT else 0.0,
        )
        for k in RouletteOutcomeKind
    )
    return RoulettePaidConfig(
        cost_stars_single=1,
        cost_stars_pack10=9,
        pack10_spins=10,
        min_thickness_level=1,
        outcomes=outcomes,
        length_buckets=(RouletteLengthBucket(name="only", min_cm=1, max_cm=10, weight=1.0),),
    )


# --------------------------------------------------------------------------- #
# Single-lot pool: picker всегда выбирает этот единственный лот
# --------------------------------------------------------------------------- #


class TestSingleLotPool:
    """`random.choice([single])` всегда возвращает один и тот же лот."""

    @pytest.mark.parametrize("currency", list(Currency))
    def test_paid_picker_returns_single_lot_id(self, currency: Currency) -> None:
        cfg = _forced_crypto_paid_config()
        lot = _lot(lot_id=777, currency=currency)
        for seed in range(20):
            outcome = pick_paid_outcome(
                config=cfg,
                random=FakeRandom(seed=seed),
                active_lots=(lot,),
            )
            assert outcome.kind is RouletteOutcomeKind.CRYPTO_LOT
            assert outcome.lot_id == 777
            assert outcome.length_cm is None

    @pytest.mark.parametrize("currency", list(Currency))
    def test_free_picker_returns_single_lot_id(self, currency: Currency) -> None:
        cfg = _forced_crypto_free_config()
        lot = _lot(lot_id=42, currency=currency)
        for seed in range(20):
            outcome = pick_roulette_outcome(
                config=cfg,
                random=FakeRandom(seed=seed),
                active_lots=(lot,),
            )
            assert outcome.kind is RouletteOutcomeKind.CRYPTO_LOT
            assert outcome.lot_id == 42
            assert outcome.length_cm is None


# --------------------------------------------------------------------------- #
# Multi-lot pool: deterministic seed → один и тот же lot_id
# --------------------------------------------------------------------------- #


class TestMultiLotDeterminism:
    """Тот же `seed` → тот же выбранный `lot_id` (одна сессия = воспроизводимо)."""

    def test_paid_picker_same_seed_same_lot(self) -> None:
        cfg = _forced_crypto_paid_config()
        lots = tuple(_lot(lot_id=i) for i in (10, 20, 30, 40, 50))
        first = pick_paid_outcome(config=cfg, random=FakeRandom(seed=42), active_lots=lots)
        second = pick_paid_outcome(config=cfg, random=FakeRandom(seed=42), active_lots=lots)
        assert first.kind is RouletteOutcomeKind.CRYPTO_LOT
        assert second.kind is RouletteOutcomeKind.CRYPTO_LOT
        assert first.lot_id == second.lot_id
        assert first.lot_id in {10, 20, 30, 40, 50}

    def test_free_picker_same_seed_same_lot(self) -> None:
        cfg = _forced_crypto_free_config()
        lots = tuple(_lot(lot_id=i) for i in (10, 20, 30, 40, 50))
        first = pick_roulette_outcome(config=cfg, random=FakeRandom(seed=7), active_lots=lots)
        second = pick_roulette_outcome(config=cfg, random=FakeRandom(seed=7), active_lots=lots)
        assert first.kind is RouletteOutcomeKind.CRYPTO_LOT
        assert second.kind is RouletteOutcomeKind.CRYPTO_LOT
        assert first.lot_id == second.lot_id
        assert first.lot_id in {10, 20, 30, 40, 50}


# --------------------------------------------------------------------------- #
# Multi-lot pool: Bernoulli-distribution across seeds (uniform)
# --------------------------------------------------------------------------- #


class TestMultiLotDistribution:
    """`random.choice([5 lots])` распределяет выбор примерно равномерно.

    Идём через много seed-ов FakeRandom (а не через много roll-ов одного
    `FakeRandom`-инстанса), чтобы получить независимые выборки. Каждый
    seed = одна выборка `choice`-а.
    """

    def test_paid_picker_uniform_across_seeds(self) -> None:
        cfg = _forced_crypto_paid_config()
        lots = tuple(_lot(lot_id=i) for i in (100, 200, 300, 400, 500))
        n = 2_000
        counter: Counter[int] = Counter()
        for seed in range(n):
            outcome = pick_paid_outcome(
                config=cfg,
                random=FakeRandom(seed=seed),
                active_lots=lots,
            )
            assert outcome.lot_id is not None
            counter[outcome.lot_id] += 1
        # Все 5 лотов должны хотя бы раз выпасть (sanity на 2k проб).
        assert set(counter.keys()) == {100, 200, 300, 400, 500}
        # Bernoulli-bound на uniform p=0.2 с 3σ.
        p = 1.0 / len(lots)
        expected = p * n
        sigma = math.sqrt(n * p * (1 - p))
        delta = max(3 * sigma, 10.0)
        low, high = expected - delta, expected + delta
        for lot_id, count in counter.items():
            assert low <= count <= high, (
                f"lot_id={lot_id}: count={count}, expected_in=[{low:.1f}, {high:.1f}]"
            )

    def test_free_picker_uniform_across_seeds(self) -> None:
        cfg = _forced_crypto_free_config()
        lots = tuple(_lot(lot_id=i) for i in (1, 2, 3, 4, 5))
        n = 2_000
        counter: Counter[int] = Counter()
        for seed in range(n):
            outcome = pick_roulette_outcome(
                config=cfg,
                random=FakeRandom(seed=seed),
                active_lots=lots,
            )
            assert outcome.lot_id is not None
            counter[outcome.lot_id] += 1
        assert set(counter.keys()) == {1, 2, 3, 4, 5}
        p = 1.0 / len(lots)
        expected = p * n
        sigma = math.sqrt(n * p * (1 - p))
        delta = max(3 * sigma, 10.0)
        low, high = expected - delta, expected + delta
        for lot_id, count in counter.items():
            assert low <= count <= high, (
                f"lot_id={lot_id}: count={count}, expected_in=[{low:.1f}, {high:.1f}]"
            )


# --------------------------------------------------------------------------- #
# Empty pool: CRYPTO_LOT никогда не выпадает (перетекание в LENGTH)
# --------------------------------------------------------------------------- #


class TestEmptyPoolFallback:
    """Семантика `active_lots=()` = `crypto_pool_empty=True` (4.1-A контракт).

    Проверяем, что C.5-рефакторинг сохранил существующее поведение:
    при пустом списке `CRYPTO_LOT` не выпадает, вес перетекает в `LENGTH`.
    """

    def test_paid_picker_empty_pool_never_returns_crypto(self) -> None:
        cfg = _forced_crypto_paid_config()
        for seed in range(50):
            outcome = pick_paid_outcome(
                config=cfg,
                random=FakeRandom(seed=seed),
                active_lots=(),
            )
            # `CRYPTO_LOT.weight=1.0` после перетекания становится
            # `LENGTH.weight=1.0` — single-bucket конфиг гарантирует
            # length_cm в [1, 10].
            assert outcome.kind is RouletteOutcomeKind.LENGTH
            assert outcome.length_cm is not None
            assert outcome.lot_id is None
            assert 1 <= outcome.length_cm <= 10

    def test_free_picker_empty_pool_never_returns_crypto(self) -> None:
        cfg = _forced_crypto_free_config()
        for seed in range(50):
            outcome = pick_roulette_outcome(
                config=cfg,
                random=FakeRandom(seed=seed),
                active_lots=(),
            )
            assert outcome.kind is RouletteOutcomeKind.LENGTH
            assert outcome.length_cm is not None
            assert outcome.lot_id is None
            assert 1 <= outcome.length_cm <= 10


# --------------------------------------------------------------------------- #
# Defence-in-depth: лот с `id is None` (нарушен контракт list_active)
# --------------------------------------------------------------------------- #


class TestNonPersistedLotDefence:
    """Контракт `IPrizeLotRepository.list_active`: возвращает только лоты с `id`.

    Если в `active_lots` всё же попал свежесгенерированный лот (`id is None`),
    picker бросает явный `InvalidRouletteConfigError` вместо тихого падения
    на `RouletteOutcome.crypto_lot(lot_id=None)`-mypy-violation внутри.
    """

    def _make_unpersisted_lot(self) -> PrizeLot:
        return PrizeLot(
            id=None,
            currency=Currency.TON_NANO,
            amount_native=1_000_000_000,
            fee_buffer_native=FeeBufferAmount(0),
            status=PrizeLotStatus.ACTIVE,
            created_at=_DUMMY_NOW,
            claimed_at=None,
        )

    def test_paid_picker_unpersisted_lot_raises(self) -> None:
        cfg = _forced_crypto_paid_config()
        with pytest.raises(InvalidRouletteConfigError, match="non-persisted PrizeLot"):
            pick_paid_outcome(
                config=cfg,
                random=FakeRandom(seed=1),
                active_lots=(self._make_unpersisted_lot(),),
            )

    def test_free_picker_unpersisted_lot_raises(self) -> None:
        cfg = _forced_crypto_free_config()
        with pytest.raises(InvalidRouletteConfigError, match="non-persisted PrizeLot"):
            pick_roulette_outcome(
                config=cfg,
                random=FakeRandom(seed=1),
                active_lots=(self._make_unpersisted_lot(),),
            )


# --------------------------------------------------------------------------- #
# Mixed-currency pool: picker не фильтрует по валюте (это работа use-case-а)
# --------------------------------------------------------------------------- #


class TestMixedCurrencyPool:
    """Picker берёт `active_lots` «как есть» — фильтрация по валюте — задача use-case-а.

    Use-case вызывает `IPrizeLotRepository.list_active(currency=...)` и
    получает уже отфильтрованный по валюте список. Picker этого
    инварианта не сторожит (он покрывается тестами на самом репозитории
    + integration-тестами use-case-а в C.6). Этот тест просто проверяет,
    что picker не падает на смеси валют — на случай если когда-то
    use-case будет звать picker с микс-pool-ом.
    """

    def test_paid_picker_mixed_currencies_does_not_crash(self) -> None:
        cfg = _forced_crypto_paid_config()
        lots = (
            _lot(lot_id=1, currency=Currency.STARS),
            _lot(lot_id=2, currency=Currency.TON_NANO),
            _lot(lot_id=3, currency=Currency.USDT_DECIMAL),
        )
        outcome = pick_paid_outcome(
            config=cfg,
            random=FakeRandom(seed=11),
            active_lots=lots,
        )
        assert outcome.kind is RouletteOutcomeKind.CRYPTO_LOT
        assert outcome.lot_id in {1, 2, 3}


# --------------------------------------------------------------------------- #
# Factory consistency: picker возвращает `RouletteOutcome.crypto_lot(...)`-shape
# --------------------------------------------------------------------------- #


class TestFactoryShape:
    """`RouletteOutcome.crypto_lot(...)` и обычный конструктор дают равные VO."""

    def test_picker_outcome_equals_factory(self) -> None:
        cfg = _forced_crypto_paid_config()
        lot = _lot(lot_id=777)
        outcome = pick_paid_outcome(
            config=cfg,
            random=FakeRandom(seed=3),
            active_lots=(lot,),
        )
        assert outcome == RouletteOutcome.crypto_lot(lot_id=777)
