"""Прокачка толщины + table-driven unlock-проверки активностей.

ГДД §3.2 — формула цены прокачки уровня толщины:

    cost_for_upgrade(current_thickness=n, base, exponent) = base * (n+1) ** exponent

Параметры `cost_base` и `cost_exponent` приходят из `balance.yaml::thickness`.
Для значения по умолчанию (`cost_base=1000`, `cost_exponent=2`) получаем:

    n = 1 → next 2  → стоимость 2² · 1000 = 4000 см
    n = 2 → next 3  → стоимость 3² · 1000 = 9000 см
    n = 9 → next 10 → стоимость 10² · 1000 = 100 000 см
    n = 19 → next 20 → стоимость 20² · 1000 = 400 000 см

Эта функция — **чистая** (никаких зависимостей, только арифметика). Use-case
`UpgradeThickness` сам зовёт её, передаёт в `require_spend(...)` и пишет
аудит. Ни один слой выше домена не должен дублировать формулу.

ГДД §3.3 — table-driven unlock-проверки активностей. Минимальный уровень
толщины для каждой активности хранится в `balance.yaml::thickness.unlock_levels`.
Доменная функция `is_activity_unlocked(...)` принимает таблицу как аргумент,
а не лезет в `IBalanceConfig` напрямую — это сохраняет домен чистым и
изолирует unit-тесты от загрузчика баланса.

Перечень активностей и их минимальных уровней (по умолчанию из ГДД §3.3):

    forest             1   ← всегда доступно с регистрации
    pvp_chat           2
    mountains          3
    raid_participate   4
    caravan_raider     5
    dungeon            6
    caravan_create     7
    raid_summon        9
"""

from __future__ import annotations

from collections.abc import Mapping

from pipirik_wars.domain.progression.errors import ActivityLockedError


def cost_for_upgrade(
    *,
    current_thickness: int,
    cost_base: int,
    cost_exponent: int,
) -> int:
    """Сколько см стоит подняться с уровня `current_thickness` на следующий.

    `cost(n→n+1) = cost_base · (n+1) ** cost_exponent`. Все аргументы должны
    быть положительными целыми; иначе бросается ``ValueError``.

    Возвращает ``int`` — стоимость в см. Гарантируется > 0 при корректных
    входных данных.
    """
    if current_thickness < 1:
        raise ValueError(f"current_thickness must be >= 1, got {current_thickness}")
    if cost_base <= 0:
        raise ValueError(f"cost_base must be > 0, got {cost_base}")
    if cost_exponent < 1:
        raise ValueError(f"cost_exponent must be >= 1, got {cost_exponent}")
    next_level = current_thickness + 1
    return int(cost_base * (next_level**cost_exponent))


def is_activity_unlocked(
    *,
    thickness: int,
    activity: str,
    unlock_levels: Mapping[str, int],
) -> bool:
    """Проверка, доступна ли активность игроку с данной толщиной.

    `activity` — строковый ключ из `balance.yaml::thickness.unlock_levels`
    (например, ``"forest"``, ``"mountains"``, ``"dungeon"``). Если ключ
    отсутствует в таблице — бросается ``KeyError``: это конфигурационная
    ошибка, а не run-time situation.

    Возвращает ``True``, если ``thickness >= unlock_levels[activity]``.
    """
    if thickness < 1:
        raise ValueError(f"thickness must be >= 1, got {thickness}")
    if activity not in unlock_levels:
        raise KeyError(
            f"unknown activity {activity!r}; check balance.yaml::thickness.unlock_levels"
        )
    return thickness >= unlock_levels[activity]


def require_unlocked(
    *,
    thickness: int,
    activity: str,
    unlock_levels: Mapping[str, int],
) -> None:
    """Императивная версия `is_activity_unlocked`: бросает `ActivityLockedError`.

    Аналог `progression.require_spend(...)`: вызывается use-case-ом перед
    выполнением активности. Сообщение ошибки содержит требуемый и текущий
    уровень — handler преобразует это в дружелюбный текст пользователю.
    """
    if not is_activity_unlocked(
        thickness=thickness, activity=activity, unlock_levels=unlock_levels
    ):
        raise ActivityLockedError(
            activity=activity,
            current_thickness=thickness,
            required_thickness=unlock_levels[activity],
        )
