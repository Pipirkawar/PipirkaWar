"""In-memory фейк для `IAnnouncementPublisher` (Спринт 4.9)."""

from __future__ import annotations

from dataclasses import dataclass, field

from pipirik_wars.domain.announcements.ports import IAnnouncementPublisher


@dataclass
class FakeAnnouncementPublisher(IAnnouncementPublisher):
    """Записывает вызовы publish() для проверки в тестах."""

    calls: list[tuple[int, str, str]] = field(default_factory=list)
    should_raise: Exception | None = None

    async def publish(
        self,
        channel_id: int,
        text: str,
        parse_mode: str = "HTML",
    ) -> None:
        if self.should_raise is not None:
            raise self.should_raise
        self.calls.append((channel_id, text, parse_mode))
