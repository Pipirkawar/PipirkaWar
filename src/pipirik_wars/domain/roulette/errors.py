"""Domain-errors рулетки (ГДД §12.4, Спринт 3.5-A).

Все наследуют общий `RouletteDomainError` (он же — `DomainError` из
`pipirik_wars.shared.errors`), чтобы в use-case-ах 3.5-C и в bot-handler-ах
3.5-D было удобно ловить «всё, что относится к рулетке» одним
`except RouletteDomainError`.

В Спринте 3.5-A определена одна конкретная ошибка —
`InvalidRouletteConfigError`. Pydantic-валидаторы `RouletteFreeConfig`
ловят большинство мисконфигов на старте процесса (сумма весов != 1.0,
дубликаты исходов и т.п.), но picker дополнительно валидирует
runtime-условия (например, отсутствие исходов с положительным весом
после исключения нулевых) — эта ошибка нужна именно для них.
"""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError

__all__ = [
    "InvalidRouletteConfigError",
    "RouletteDomainError",
]


class RouletteDomainError(DomainError):
    """База для всех ошибок доменного слоя рулетки.

    Не бросается напрямую — у каждого случая есть свой подкласс.
    """


class InvalidRouletteConfigError(RouletteDomainError):
    """Конфиг рулетки в runtime-картине невалиден.

    Бросается picker-ом `pick_roulette_outcome(...)` в случаях, которые
    pydantic-валидаторы не могут отловить статически (но они должны
    быть невозможны при честном `RouletteFreeConfig`):

    - все исходы (после исключения нулевых) имеют вес `0.0`;
    - все бакеты длины (после исключения нулевых) имеют вес `0.0`.

    Pydantic-инвариант «сумма весов == 1.0 ± ε» **гарантирует**, что
    эти кейсы недостижимы при валидном конфиге. Ошибка нужна для
    defence-in-depth и явных тестов на «picker не молчит при битом
    конфиге».

    Атрибут `reason: str` — машинно-читаемая причина (для логов и
    локализации в bot-handler-е 3.5-D).
    """

    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        super().__init__(f"invalid roulette config: {reason}")
