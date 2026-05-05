"""In-memory `IAnticheatRepository` для unit-тестов use-case-ов.

Хранит список «событий-аналогов audit_log-строк» в памяти и собирает
ту же rolling-агрегацию, что и `SqlAlchemyAnticheatRepository`. Тесты
заполняют `events` руками (через `record_event(...)`) и проверяют, что
use-case (1.6.D) корректно интерпретирует возвращаемый `AnticheatWindow`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from pipirik_wars.domain.anticheat import AnticheatWindow, IAnticheatRepository
from pipirik_wars.domain.shared.ports.audit import AuditSource


@dataclass(frozen=True, slots=True)
class _Event:
    player_id: int
    source: AuditSource
    delta_cm: int | None
    occurred_at: datetime


@dataclass
class FakeAnticheatRepository(IAnticheatRepository):
    """In-memory реализация для тестов."""

    events: list[_Event] = field(default_factory=list)

    def record_event(
        self,
        *,
        player_id: int,
        source: AuditSource,
        delta_cm: int | None,
        occurred_at: datetime,
    ) -> None:
        """Добавить «как-будто-аудит-строку» в in-memory лог."""
        if occurred_at.tzinfo is None:
            raise ValueError(f"occurred_at must be timezone-aware (UTC), got naive {occurred_at!r}")
        self.events.append(
            _Event(
                player_id=player_id,
                source=source,
                delta_cm=delta_cm,
                occurred_at=occurred_at,
            )
        )

    async def sum_organic_in_window(
        self,
        *,
        player_id: int,
        since: datetime,
        organic_sources: Iterable[AuditSource],
    ) -> AnticheatWindow:
        if player_id <= 0:
            raise ValueError(f"player_id must be > 0, got {player_id}")
        if since.tzinfo is None:
            raise ValueError(f"since must be timezone-aware (UTC), got naive {since!r}")

        sources = set(organic_sources)
        if not sources:
            return AnticheatWindow(player_id=player_id, since=since, organic_sum_cm=0)

        total = 0
        for ev in self.events:
            if ev.player_id != player_id:
                continue
            if ev.source not in sources:
                continue
            if ev.delta_cm is None or ev.delta_cm <= 0:
                continue
            if ev.occurred_at < since:
                continue
            total += ev.delta_cm

        return AnticheatWindow(
            player_id=player_id,
            since=since,
            organic_sum_cm=total,
        )
