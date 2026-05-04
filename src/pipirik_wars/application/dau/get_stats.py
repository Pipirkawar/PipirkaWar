"""Use-case `GetDauStats` (Спринт 1.2.3, ГДД §18.4).

Возвращает текущую статистику DAU Gate для админ-команды
`/admin_stats`. На текущей фазе — только `current` и `max`. Очередь
регистраций (`signup_queue`) и пик за неделю появятся в Спринтах
1.2.C / 1.4.7 и расширят этот DTO без breaking-изменений.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.dau import IDauCounter, IDauLimit


@dataclass(frozen=True, slots=True)
class DauStats:
    """Статистика DAU Gate."""

    current: int
    """Сколько уникальных активных за сегодня (по `Europe/Moscow`)."""

    max_dau: int
    """Текущий лимит (`MAX_DAU`)."""

    @property
    def is_full(self) -> bool:
        """`True`, если новые регистрации должны идти в очередь."""
        return self.current >= self.max_dau

    @property
    def utilization_percent(self) -> int:
        """Процент использования (0..100+, может превысить 100 для безопасности)."""
        if self.max_dau <= 0:
            return 0
        return round(self.current * 100 / self.max_dau)


class GetDauStats:
    """Read-only use-case: текущий DAU и лимит."""

    __slots__ = ("_counter", "_limit")

    def __init__(
        self,
        *,
        counter: IDauCounter,
        limit: IDauLimit,
    ) -> None:
        self._counter = counter
        self._limit = limit

    async def execute(self) -> DauStats:
        current = await self._counter.current()
        max_dau = await self._limit.get()
        return DauStats(current=current, max_dau=max_dau)
