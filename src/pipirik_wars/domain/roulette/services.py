"""Чистые picker-ы рулеток (ГДД §12.4.2 free + §12.5.2 paid, Спринт 4.1-A/4.1-C).

Две доменных функции:

- `pick_roulette_outcome` — free-рулетка (Спринт 3.5-A, ГДД §12.4.2).
- `pick_paid_outcome` — платная рулетка (Спринт 4.1-A, ГДД §12.5.2).

Обе возвращают `RouletteOutcome` с `kind` (один из 5 типов исхода), для
`LENGTH` — конкретным `length_cm`, для `CRYPTO_LOT` — `lot_id` выбранного
из `active_lots` лота. Каталог-зависимые типы (`item` /
`scroll_regular` / `scroll_blessed`) дальше резолвятся в use-case-е
(Спринт 3.5-C/D), потому что им нужен доступ к каталогу предметов /
пулу скроллов.

Алгоритм (одинаковый для free и paid):

1. Считаются итоговые веса исходов с учётом перетекания
   `crypto_lot` → `length`, когда пул активных лотов `active_lots`
   пуст. Сигнал «крипто-пул пуст» = `len(active_lots) == 0`
   (задаётся вызывающим use-case-ом через `IPrizeLotRepository
   .list_active(currency)`). На 4.1-A/B `active_lots=()` всегда,
   поэтому `crypto_lot` перетекает в `length`; в 4.1-C/D
   use-case-ы начнут передавать реальный список.
2. `IRandom.weighted_choice(kinds, int_weights)` выбирает один тип.
3. Если `kind == LENGTH` — выбирается бакет
   `IRandom.weighted_choice(buckets, int_weights)`,
   затем `IRandom.randint(min_cm, max_cm)` даёт конкретное число
   сантиметров.
4. Если `kind == CRYPTO_LOT` — `IRandom.choice(active_lots)`
   выбирает один лот из `active_lots`; `lot.id` идёт в
   `RouletteOutcome.lot_id`. Бросать в `active_lots` неперсистивные
   лоты (`lot.id is None`) запрещено: контракт use-case-а —
   `IPrizeLotRepository.list_active(currency)` возвращает только
   сохранённые лоты. defense-in-depth —
   `InvalidRouletteConfigError`.

Различие — только в конфиге (free vs paid веса). Внутренние хелперы
`_roll_kind` / `_roll_length_bucket` / `_roll_crypto_lot` / `_weighted_choice`
шарятся между free и paid.

Picker — чистая функция от `(config, random, active_lots)`. В тестах
`IRandom` подменяется на `FakeRandom(seed=...)`, что даёт детерминированный
3σ-Bernoulli-контроль частот всех веток.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pipirik_wars.domain.balance.config import (
    RouletteFreeConfig,
    RouletteLengthBucket,
    RouletteOutcomeKind,
    RouletteOutcomeWeight,
    RoulettePaidConfig,
)
from pipirik_wars.domain.monetization.entities import PrizeLot
from pipirik_wars.domain.roulette.entities import RouletteOutcome
from pipirik_wars.domain.roulette.errors import InvalidRouletteConfigError
from pipirik_wars.domain.shared.ports import IRandom

__all__ = [
    "pick_length_only_outcome",
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
    active_lots: Sequence[PrizeLot],
) -> RouletteOutcome:
    """Разыграть один исход free-рулетки.

    Параметры:
    - `config` — провалидированный `RouletteFreeConfig` (pydantic
      гарантирует: сумма весов исходов = 1.0 ± ε, сумма весов бакетов
      = 1.0 ± ε, бакеты длины не перекрываются и `min_cm <= max_cm`).
    - `random` — DI-источник случайности (`IRandom`).
    - `active_lots` — список активных `PrizeLot`-ов (Спринт 4.1-C);
      формируется use-case-ом из `IPrizeLotRepository.list_active(currency)`.
      Пустой список равносилен «крипто-пул пуст»: вес `CRYPTO_LOT`
      перетекает на `LENGTH` (ГДД §12.4.2). При непустом списке и
      выпавшем весе `CRYPTO_LOT` — `random.choice(active_lots)` выбирает
      один лот, его `id` идёт в `RouletteOutcome.lot_id`.

    Returns:
    - `RouletteOutcome(kind, length_cm, lot_id)`, где для `kind == LENGTH`
      `length_cm` — целое число в `[bucket.min_cm, bucket.max_cm]`,
      `lot_id = None`; для `kind == CRYPTO_LOT` `lot_id = chosen.id`,
      `length_cm = None`; для остальных типов — оба `None`.

    Raises:
    - `InvalidRouletteConfigError` — defence-in-depth, если все веса
      нулевые (pydantic-инвариант не должен такое пропустить) или если
      в `active_lots` попал лот с `id is None` (нарушен контракт
      `IPrizeLotRepository.list_active`).
    """
    crypto_pool_empty = len(active_lots) == 0
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
    if kind is RouletteOutcomeKind.CRYPTO_LOT:
        return _roll_crypto_lot(active_lots=active_lots, random=random)
    return RouletteOutcome(kind=kind)


def pick_paid_outcome(
    *,
    config: RoulettePaidConfig,
    random: IRandom,
    active_lots: Sequence[PrizeLot],
) -> RouletteOutcome:
    """Разыграть один исход платной рулетки (ГДД §12.5.2, Спринт 4.1-A).

    Параметры — те же, что у `pick_roulette_outcome`, но `config` —
    `RoulettePaidConfig` (веса смещены в пользу шмота / скроллов /
    крипто, см. §12.5.2).

    Returns:
    - `RouletteOutcome(kind, length_cm, lot_id)` — семантика идентична
      `pick_roulette_outcome` (см. выше).

    Raises:
    - `InvalidRouletteConfigError` — defence-in-depth, если все веса
      нулевые (pydantic-инвариант не должен такое пропустить) или если
      в `active_lots` попал лот с `id is None`.

    Использование: вызывается из use-case `SpinPaidRoulette` (4.1-A). На
    4.1-A/B use-case передаёт `active_lots=()` всегда — `CRYPTO_LOT`
    всегда перетекает в `LENGTH` (по ГДД §12.5.2: 0.020 + 0.550 = 0.570).
    Реальный вызов `IPrizeLotRepository.list_active(STARS)` появится в
    Спринте 4.1-C (шаг C.6, резервирование лота при выпадении).
    """
    crypto_pool_empty = len(active_lots) == 0
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
    if kind is RouletteOutcomeKind.CRYPTO_LOT:
        return _roll_crypto_lot(active_lots=active_lots, random=random)
    return RouletteOutcome(kind=kind)


def pick_length_only_outcome(
    *,
    length_buckets: tuple[RouletteLengthBucket, ...],
    random: IRandom,
) -> RouletteOutcome:
    """Гарантированно выбрать LENGTH-исход из бакетов.

    Используется в race-fallback use-case-ов спинов (C.6.d): когда
    `update_status(lot_id, RESERVED)` бросает `PrizeLotStatusTransitionError`
    (другой игрок забронировал лот первым между `list_active`
    и `update_status`) — use-case заменяет outcome на
    `pick_length_only_outcome(...)` и продолжает спин как LengthGain.

    Сигнатура принимает только `length_buckets`, а не полный config,
    чтобы работать и с free-, и с paid-конфигом одновременно (у обоих есть
    идентичный по shape блок `length_buckets`).

    Raises:
    - `InvalidRouletteConfigError` — если все веса бакетов нулевые
      (pydantic-инвариант такое не должен пропускать).
    """
    bucket = _roll_length_bucket(buckets=length_buckets, random=random)
    length_cm = random.randint(bucket.min_cm, bucket.max_cm)
    return RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=length_cm)


def _roll_crypto_lot(
    *,
    active_lots: Sequence[PrizeLot],
    random: IRandom,
) -> RouletteOutcome:
    """Выбрать один лот из `active_lots` через `IRandom.choice`.

    Должно вызываться только при непустом `active_lots`: в пустом
    случае picker раньше выбирает `LENGTH` (через `crypto_pool_empty
    → перетекание` в `_roll_kind`).

    Raises:
    - `InvalidRouletteConfigError` — если `chosen.id is None`. Контракт
      use-case-а: `IPrizeLotRepository.list_active` возвращает только
      сохранённые лоты (`id > 0`). Появление свежесгенерированного
      лота — контрактная ошибка коллера.
    """
    chosen = random.choice(active_lots)
    if chosen.id is None:
        raise InvalidRouletteConfigError(
            reason="active_lots contained a non-persisted PrizeLot (id is None)",
        )
    return RouletteOutcome.crypto_lot(lot_id=chosen.id)


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
