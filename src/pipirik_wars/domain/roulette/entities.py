"""Доменные сущности рулетки (ГДД §12.4, Спринт 3.5-A).

`RouletteOutcomeKind` живёт в `domain/balance/config.py` (стабильные
машинные id попадают в `audit_log.target_id` Спринта 3.5-C). Этот
модуль ре-экспортирует его, чтобы доменный код мог импортировать
«одной строкой» из `domain.roulette` (по аналогии с
`domain/inventory/entities.py`, который ре-экспортирует `Slot` из
`domain/balance/config`).

`RouletteOutcome` — frozen-VO с распакованным результатом одного спина:
тип исхода + (для `LENGTH`) разыгранное количество сантиметров. Для
других типов `length_cm = None` — конкретный приз/предмет/скролл
выкатывается в use-case-е (Спринт 3.5-C/D), picker возвращает только
тип. Это сделано, чтобы picker оставался чистой функцией от
`(config, random, crypto_pool_empty)` без зависимостей от каталога
предметов / пула скроллов / внешних крипто-API.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.balance.config import RouletteOutcomeKind

__all__ = [
    "RouletteOutcome",
    "RouletteOutcomeKind",
]


@dataclass(frozen=True, slots=True)
class RouletteOutcome:
    """Результат одного спина рулетки (ГДД §12.4.2).

    Возвращается чистой функцией `pick_roulette_outcome(...)`. Для
    `kind == LENGTH` поле `length_cm` обязано быть положительным `int`
    (бакет уже выбран и `uniform` уже разыгран); для остальных типов —
    `None` (конкретный приз/скролл/лот выкатывается в use-case-е,
    Спринт 3.5-C/D).

    Инвариант проверяется в `__post_init__`:
    - `kind == LENGTH` ⇒ `length_cm is not None and length_cm >= 1`;
    - `kind != LENGTH` ⇒ `length_cm is None`.

    Frozen + slots — VO без identity, безопасно сравнивать `==` / хэшировать.
    """

    kind: RouletteOutcomeKind
    length_cm: int | None = None

    def __post_init__(self) -> None:
        if self.kind is RouletteOutcomeKind.LENGTH:
            if self.length_cm is None:
                raise ValueError(
                    "RouletteOutcome(kind=LENGTH) requires length_cm to be set",
                )
            if self.length_cm < 1:
                raise ValueError(
                    f"RouletteOutcome(kind=LENGTH).length_cm must be >= 1, got {self.length_cm}",
                )
        elif self.length_cm is not None:
            raise ValueError(
                f"RouletteOutcome(kind={self.kind.value!r}) must have "
                f"length_cm=None, got {self.length_cm}",
            )
