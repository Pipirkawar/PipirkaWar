"""Unit-тесты `IsAdminFilter` (Спринт 2.5-B.6)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from aiogram.types import TelegramObject

from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.domain.admin import Admin, AdminRole


def _admin(*, is_active: bool = True) -> Admin:
    return Admin(
        id=1,
        tg_id=42,
        role=AdminRole.SUPPORT,
        is_active=is_active,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
class TestIsAdminFilter:
    async def test_passes_for_admin(self) -> None:
        flt = IsAdminFilter()
        event = MagicMock(spec=TelegramObject)
        assert await flt(event, admin=_admin()) is True

    async def test_rejects_when_admin_is_none(self) -> None:
        flt = IsAdminFilter()
        event = MagicMock(spec=TelegramObject)
        assert await flt(event, admin=None) is False

    async def test_rejects_when_admin_key_missing(self) -> None:
        """`AdminGuard`-middleware не подключён — secure default = отказать."""
        flt = IsAdminFilter()
        event = MagicMock(spec=TelegramObject)
        assert await flt(event) is False

    async def test_rejects_when_admin_value_is_wrong_type(self) -> None:
        flt = IsAdminFilter()
        event = MagicMock(spec=TelegramObject)
        assert await flt(event, admin="hello") is False
