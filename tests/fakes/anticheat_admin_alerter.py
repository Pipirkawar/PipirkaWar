"""Фейк `IAnticheatAdminAlerter`. In-memory список событий для assert-ов."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.domain.anticheat import IAnticheatAdminAlerter
from pipirik_wars.domain.shared.ports.audit import AuditSource


@dataclass(frozen=True, slots=True)
class AnticheatAdminAlertEvent:
    """Snapshot одного `IAnticheatAdminAlerter.emit(...)` для тестов."""

    player_id: int
    cap_kind: str
    cap_cm: int
    observed_sum_cm: int
    source: AuditSource
    banned_until: datetime
    occurred_at: datetime


class FakeAnticheatAdminAlerter(IAnticheatAdminAlerter):
    """Записывает события в `events` без побочных эффектов."""

    __slots__ = ("events",)

    def __init__(self) -> None:
        self.events: list[AnticheatAdminAlertEvent] = []

    async def emit(
        self,
        *,
        player_id: int,
        cap_kind: str,
        cap_cm: int,
        observed_sum_cm: int,
        source: AuditSource,
        banned_until: datetime,
        occurred_at: datetime,
    ) -> None:
        self.events.append(
            AnticheatAdminAlertEvent(
                player_id=player_id,
                cap_kind=cap_kind,
                cap_cm=cap_cm,
                observed_sum_cm=observed_sum_cm,
                source=source,
                banned_until=banned_until,
                occurred_at=occurred_at,
            )
        )
