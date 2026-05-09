"""Domain-errors рулетки (ГДД §12.4, Спринт 3.5-A/C).

Все наследуют общий `RouletteDomainError` (он же — `DomainError` из
`pipirik_wars.shared.errors`), чтобы в use-case-ах 3.5-C и в bot-handler-ах
3.5-D было удобно ловить «всё, что относится к рулетке» одним
`except RouletteDomainError`.

Спринт 3.5-A: `InvalidRouletteConfigError` (defence-in-depth picker-а).
Спринт 3.5-C: `RouletteThicknessGateError`, `InsufficientLengthForRouletteError`
— гейты use-case-а `SpinFreeRoulette` (минимальный уровень толщины и
наличия длины >= cost). Pydantic-валидаторы `RouletteFreeConfig`
ловят большинство мисконфигов на старте процесса (сумма весов != 1.0,
дубликаты исходов и т.п.), но picker дополнительно валидирует
runtime-условия (например, отсутствие исходов с положительным весом
после исключения нулевых) — эта ошибка нужна именно для них.
"""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError

__all__ = [
    "InsufficientLengthForRouletteError",
    "InvalidRouletteConfigError",
    "RouletteDomainError",
    "RouletteThicknessGateError",
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


class RouletteThicknessGateError(RouletteDomainError):
    """Игрок не дотянул до минимального уровня толщины для прокрутки.

    Бросается use-case-ом `SpinFreeRoulette` (Спринт 3.5-C) до списания
    стоимости и до записи в `roulette_spins`: гейт `thickness_level >=
    config.roulette.free.min_thickness_level` проверяется первым, чтобы
    отказать «дёшево» (без побочных эффектов на длину / event-log).

    Ловится bot-handler-ом 3.5-D и маппится на локаль `roulette-error-thickness-gate`.

    Атрибуты — для машинной обработки и подстановки в локаль:
    - `player_id` — id игрока (обычно `tg_id` для удобной трассировки логов).
    - `thickness_level` — текущий уровень толщины игрока.
    - `required_level` — порог из `RouletteFreeConfig.min_thickness_level`.
    """

    def __init__(
        self,
        *,
        player_id: int,
        thickness_level: int,
        required_level: int,
    ) -> None:
        self.player_id = player_id
        self.thickness_level = thickness_level
        self.required_level = required_level
        super().__init__(
            f"player {player_id} thickness_level={thickness_level} below "
            f"required {required_level} for free roulette",
        )


class InsufficientLengthForRouletteError(RouletteDomainError):
    """У игрока меньше длины, чем стоит одна прокрутка.

    Бросается use-case-ом `SpinFreeRoulette` (Спринт 3.5-C) после
    прохождения thickness-гейта: `length.cm >= config.roulette.free.cost_cm`
    обязан быть истинным до списания стоимости. Иначе — ошибка, без
    побочных эффектов.

    Ловится bot-handler-ом 3.5-D и маппится на локаль
    `roulette-error-insufficient-length`.

    Атрибуты:
    - `player_id` — id игрока.
    - `length_cm` — текущая длина игрока в см.
    - `cost_cm` — стоимость одной прокрутки из `RouletteFreeConfig.cost_cm`.
    """

    def __init__(
        self,
        *,
        player_id: int,
        length_cm: int,
        cost_cm: int,
    ) -> None:
        self.player_id = player_id
        self.length_cm = length_cm
        self.cost_cm = cost_cm
        super().__init__(
            f"player {player_id} length_cm={length_cm} below cost {cost_cm} for free roulette",
        )
