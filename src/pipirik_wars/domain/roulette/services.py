"""Чистые picker-ы рулеток (ГДД §12.4.2 free + §12.5.2 paid, Спринт 4.1-A).

Две доменных функции:

- `pick_roulette_outcome` — free-рулетка (Спринт 3.5-A, ГДД §12.4.2).
- `pick_paid_outcome` — платная рулетка (Спринт 4.1-A, ГДД §12.5.2).

Обе возвращают `RouletteOutcome` с `kind` (один из 5 типов исхода) и —
для `LENGTH` — конкретным `length_cm`. Все остальные типы (`item` /
`scroll_regular` / `scroll_blessed` / `crypto_lot`) дальше резолвятся
в use-case-е (Спринт 3.5-C/D / 4.1-C-D), потому что им нужен доступ к
каталогу предметов / пулу скроллов / крипто-API.

Алгоритм (одинаковый для free и paid):

1. Считаются итоговые веса исходов с учётом перетекания
   `crypto_lot` → `length` при пустом крипто-пуле (флаг
   `crypto_pool_empty` задаётся вызывающим use-case-ом).
2. `IRandom.weighted_choice(kinds, int_weights)` выбирает один тип.
3. Если `kind == LENGTH` — выбирается бакет
   `IRandom.weighted_choice(buckets, int_weights)`,
   затем `IRandom.randint(min_cm, max_cm)` даёт конкретное число
   сантиметров.

Различие — только в конфиге (free vs paid веса). Внутренние хелперы
`_roll_kind` / `_roll_length_bucket` / `_weighted_choice` шарятся.

Picker — чистая функция от `(config, random, crypto_pool_empty)`.
В тестах `IRandom` подменяется на `FakeRandom(seed=...)`, что даёт
детерминированный 3σ-Bernoulli-контроль частот всех веток.
"""

from __future__ import annotations

from typing import TypeVar

from pipirik_wars.domain.balance.config import (
    RouletteFreeConfig,
    RouletteLengthBucket,
    RouletteOutcomeKind,
    RouletteOutcomeWeight,
    RoulettePaidConfig,
)
from pipirik_wars.domain.roulette.entities import RouletteOutcome
from pipirik_wars.domain.roulette.errors import InvalidRouletteConfigError
from pipirik_wars.domain.shared.ports import IRandom

__all__ = [
    "pick_paid_outcome",
    "pick_roulette_outcome",
]

_T = TypeVar("_T")

# Грубое целочисленное представление весов для `IRandom.weighted_choice`.
# Веса в `RouletteFreeConfig` — `float` в `[0.0, 1.0]` с шагом ~0.001
# (см. ГДД §12.4.2 — три знака после запятой). Идентично подходу
# в `domain/inventory/services.py::_WEIGHT_SCALE` (Спринт 3.4-A).
_WEIGHT_SCALE: int = 100_000


def pick_roulette_outcome(
    *,
    config: RouletteFreeConfig,
    random: IRandom,
    crypto_pool_empty: bool,
) -> RouletteOutcome:
    """Разыграть один исход free-рулетки.

    Параметры:
    - `config` — провалидированный `RouletteFreeConfig` (pydantic
      гарантирует: сумма весов исходов = 1.0 ± ε, сумма весов бакетов
      = 1.0 ± ε, бакеты длины не перекрываются и `min_cm <= max_cm`).
    - `random` — DI-источник случайности (`IRandom`).
    - `crypto_pool_empty` — флаг от use-case-а: если `True`, вес
      `CRYPTO_LOT` перетекает на `LENGTH` (ГДД §12.4.2: «если крипто-пул
      пуст → вес `crypto_lot` перетекает на `length`»). На 3.5-A крипто-пул
      всегда пуст (крипто-инфраструктура — Спринт 4.x), use-case
      `SpinFreeRoulette` (3.5-C) пока всегда передаёт `True`.

    Returns:
    - `RouletteOutcome(kind, length_cm)`, где для `kind == LENGTH`
      `length_cm` — целое число в `[bucket.min_cm, bucket.max_cm]`,
      для остальных типов `length_cm = None`.

    Raises:
    - `InvalidRouletteConfigError` — defence-in-depth, если все веса
      нулевые (pydantic-инвариант не должен такое пропустить).
    """
    kind = _roll_kind(
        outcomes=config.outcomes,
        random=random,
        crypto_pool_empty=crypto_pool_empty,
    )
    if kind is RouletteOutcomeKind.LENGTH:
        bucket = _roll_length_bucket(
            buckets=config.length_buckets,
            random=random,
        )
        length_cm = random.randint(bucket.min_cm, bucket.max_cm)
        return RouletteOutcome(kind=kind, length_cm=length_cm)
    return RouletteOutcome(kind=kind)


def pick_paid_outcome(
    *,
    config: RoulettePaidConfig,
    random: IRandom,
    crypto_pool_empty: bool,
) -> RouletteOutcome:
    """Разыграть один исход платной рулетки (ГДД §12.5.2, Спринт 4.1-A).

    Параметры — те же, что у `pick_roulette_outcome`, но `config` —
    `RoulettePaidConfig` (веса смещены в пользу шмота / скроллов /
    крипто, см. §12.5.2).

    Returns:
    - `RouletteOutcome(kind, length_cm)`, где для `kind == LENGTH`
      `length_cm` — целое число в `[bucket.min_cm, bucket.max_cm]`,
      для остальных типов `length_cm = None`.

    Raises:
    - `InvalidRouletteConfigError` — defence-in-depth, если все веса
      нулевые (pydantic-инвариант не должен такое пропустить).

    Использование: вызывается из use-case `SpinPaidRoulette` (4.1-A).
    Как и для free-рулетки, `crypto_pool_empty=True` на 4.1-A до
    Спринта 4.1-D (когда появится `IPrizePool` порт). До тех пор вес
    `crypto_lot` (0.020) перетекает на `length` (становится 0.570).
    """
    kind = _roll_kind(
        outcomes=config.outcomes,
        random=random,
        crypto_pool_empty=crypto_pool_empty,
    )
    if kind is RouletteOutcomeKind.LENGTH:
        bucket = _roll_length_bucket(
            buckets=config.length_buckets,
            random=random,
        )
        length_cm = random.randint(bucket.min_cm, bucket.max_cm)
        return RouletteOutcome(kind=kind, length_cm=length_cm)
    return RouletteOutcome(kind=kind)


def _roll_kind(
    *,
    outcomes: tuple[RouletteOutcomeWeight, ...],
    random: IRandom,
    crypto_pool_empty: bool,
) -> RouletteOutcomeKind:
    """Взвешенный выбор типа исхода (5 вариантов, ГДД §12.4.2).

    Перетекание `CRYPTO_LOT → LENGTH` при `crypto_pool_empty=True`:
    вес `CRYPTO_LOT` прибавляется к весу `LENGTH`, а в самом списке
    `CRYPTO_LOT` уже не участвует. Если в конфиге исхода `CRYPTO_LOT` нет
    (теоретически возможно, если кто-то его убрал) — перетекать нечему,
    спокойно идём дальше.
    """
    pairs: list[tuple[RouletteOutcomeKind, float]] = []
    crypto_weight: float = 0.0
    for entry in outcomes:
        if crypto_pool_empty and entry.kind is RouletteOutcomeKind.CRYPTO_LOT:
            crypto_weight = entry.weight
            continue
        pairs.append((entry.kind, entry.weight))
    if crypto_pool_empty and crypto_weight > 0.0:
        pairs = [
            (k, w + crypto_weight) if k is RouletteOutcomeKind.LENGTH else (k, w) for k, w in pairs
        ]
    return _weighted_choice(pairs=tuple(pairs), random=random)


def _roll_length_bucket(
    *,
    buckets: tuple[RouletteLengthBucket, ...],
    random: IRandom,
) -> RouletteLengthBucket:
    """Взвешенный выбор бакета длины (4 варианта в дефолтах, ГДД §12.4.2)."""
    pairs: tuple[tuple[RouletteLengthBucket, float], ...] = tuple((b, b.weight) for b in buckets)
    return _weighted_choice(pairs=pairs, random=random)


def _weighted_choice(
    *,
    pairs: tuple[tuple[_T, float], ...],
    random: IRandom,
) -> _T:
    """`IRandom.weighted_choice` на парах `(item, float-weight)`.

    Идентично `domain/inventory/services.py::_weighted_choice`: пары с
    весом `0.0` отфильтровываются (`IRandom.weighted_choice` требует
    `weight > 0`); float-веса масштабируются в `int` через
    `_WEIGHT_SCALE` (погрешность ≤ `1 / _WEIGHT_SCALE` = `0.00001`,
    на 3σ-Bernoulli-тестах не различима).

    Если после фильтрации не осталось ни одной пары с положительным
    весом — `InvalidRouletteConfigError` (pydantic-инвариант сумм не
    должен такое допускать; ошибка нужна для defence-in-depth).
    """
    non_zero = tuple((c, w) for c, w in pairs if w > 0.0)
    if not non_zero:
        raise InvalidRouletteConfigError(
            reason="all roulette weights are zero (no pickable outcome)",
        )
    items = [c for c, _ in non_zero]
    int_weights = [round(w * _WEIGHT_SCALE) for _, w in non_zero]
    return random.weighted_choice(items, int_weights)
