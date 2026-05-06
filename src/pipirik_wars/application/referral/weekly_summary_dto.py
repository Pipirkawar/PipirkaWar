"""DTO результата `RunWeeklyClanReferralSummary` (Спринт 2.4.E).

`WeeklyClanReferralSummary` — то, что use-case возвращает шедулеру и
notifier-у. Содержит достаточно данных для рендера сообщения:

- `clan` — клан, для которого считается сводка (нужен `chat_id` для
  отправки и `title` для текста);
- `total` — суммарное число новых рефералов клана за окно;
- `top` — кортеж из топ-3 пар `(player, count)` (отсортирован
  `count DESC, player.id ASC`); меньше 3 — если в клане столько
  активных рефереров за неделю.

Иммутабельный frozen-датакласс, без логики — pure data carrier.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.clan import Clan
from pipirik_wars.domain.player import Player


@dataclass(frozen=True, slots=True)
class WeeklyClanReferralEntryDTO:
    """Один пункт top-3 в карточке: реферер + сколько он привёл."""

    player: Player
    count: int


@dataclass(frozen=True, slots=True)
class WeeklyClanReferralSummary:
    """Результат `RunWeeklyClanReferralSummary.execute(...)`.

    Поля:
    - `clan` — клан, к которому относится сводка (`chat_id`, `title`).
    - `total` — суммарное число новых рефералов клана за неделю
      (`>= 1`; если 0 — use-case вернул бы `None`).
    - `top` — top-N пар `(player, count)`, N <= 3. Сорт стабильный:
      `count DESC, player.id ASC` (то же, что репо отдало).
    """

    clan: Clan
    total: int
    top: tuple[WeeklyClanReferralEntryDTO, ...]


__all__ = [
    "WeeklyClanReferralEntryDTO",
    "WeeklyClanReferralSummary",
]
