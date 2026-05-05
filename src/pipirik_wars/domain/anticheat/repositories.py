"""Порт repository-агрегатора anti-cheat-окна (Спринт 1.6.C / ПД 1.6.3).

`IAnticheatRepository` — узкий read-only порт, отвечает за быстрый
SUM-запрос по `audit_log` для построения rolling-окна. Список
organic-источников передаётся параметром: единый source-of-truth —
`balance.yaml::anticheat.organic_sources`. Use-case (1.6.D) сам читает
конфиг и пробрасывает в репо — так балансовая конфигурация остаётся
влиятельной без прямой зависимости infra-слоя на pydantic-схему.
"""

from __future__ import annotations

import abc
from collections.abc import Iterable
from datetime import datetime

from pipirik_wars.domain.anticheat.entities import AnticheatWindow
from pipirik_wars.domain.shared.ports.audit import AuditSource


class IAnticheatRepository(abc.ABC):
    """Read-only агрегатор записей `audit_log` под anti-cheat-хардкап."""

    @abc.abstractmethod
    async def sum_organic_in_window(
        self,
        *,
        player_id: int,
        since: datetime,
        organic_sources: Iterable[AuditSource],
    ) -> AnticheatWindow:
        """Сумма positive `delta_cm` по organic-источникам за окно `[since, now]`.

        Включаются только строки, удовлетворяющие ВСЕМ условиям:
          * `target_kind = 'player'` AND `target_id = str(player_id)`
          * `source IN organic_sources` (по value enum-а)
          * `delta_cm IS NOT NULL` AND `delta_cm > 0`
          * `occurred_at >= since` (UTC, timezone-aware)

        Возвращает `AnticheatWindow` (`organic_sum_cm = 0`, если нет записей).
        Не делает собственных коммитов — выполняется в текущей транзакции
        UoW (правило Спринта 0.2). `organic_sources` пустой → вернётся 0.

        :raises ValueError: если `since` без tzinfo или `player_id <= 0`.
        """
