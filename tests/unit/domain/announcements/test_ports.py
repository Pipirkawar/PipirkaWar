"""Юнит-тесты domain/announcements ports (Спринт 4.9)."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.announcements.ports import IAnnouncementPublisher
from tests.fakes import FakeAnnouncementPublisher


class TestIAnnouncementPublisher:
    def test_fake_is_valid_implementation(self) -> None:
        publisher = FakeAnnouncementPublisher()
        assert isinstance(publisher, IAnnouncementPublisher)

    @pytest.mark.asyncio
    async def test_fake_records_calls(self) -> None:
        publisher = FakeAnnouncementPublisher()
        await publisher.publish(123, "test", "HTML")
        assert len(publisher.calls) == 1
        assert publisher.calls[0] == (123, "test", "HTML")

    @pytest.mark.asyncio
    async def test_fake_raises_when_configured(self) -> None:
        publisher = FakeAnnouncementPublisher(
            should_raise=RuntimeError("test error"),
        )
        with pytest.raises(RuntimeError, match="test error"):
            await publisher.publish(123, "test")
