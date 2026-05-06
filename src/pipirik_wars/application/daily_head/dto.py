"""DTO результата use-case-а «Глава клана дня» (Спринт 2.3.C).

`DailyHeadResolved` — то, что use-case возвращает в bot-handler.
Содержит достаточно данных для рендера сообщения:

- сам `DailyHeadAssignment` (id уже проставлен; `bonus_cm` — для UI);
- `player_after` — снимок игрока после прибавки длины (handler
  показывает «было N см → стало M см»);
- `was_new` — флаг «прямо сейчас назначили» vs «вернули
  идемпотентного существующего». Handler по нему различает «🎉
  поздравляем» и «👀 на сегодня уже выбрана: имя».

Иммутабельный frozen-датакласс, без логики — pure data carrier.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.daily_head.entities import DailyHeadAssignment
from pipirik_wars.domain.player import Player


@dataclass(frozen=True, slots=True)
class DailyHeadResolved:
    """Результат `RequestDailyHead.execute(...)` / `RunDailyHeadCron.execute(...)`.

    Поля:
    - `assignment` — итоговая запись `daily_heads` (`id` всегда не-None,
      т.к. либо вновь сохранена, либо найдена существующая).
    - `player` — игрок-глава с применённой прибавкой длины (для UI).
      None допустим только в крайних состояниях гонки (например, repo
      вернул клан, но игрок был только что удалён — не пытаемся
      падать, handler рендерит fallback). На happy-path всегда заполнен.
    - `was_new` — `True`, если эта `execute()` фактически назначила
      главу (запись добавлена, длина прибавлена); `False`, если глава
      уже была назначен ранее (идемпотентный возврат).
    """

    assignment: DailyHeadAssignment
    player: Player | None
    was_new: bool


__all__ = ["DailyHeadResolved"]
