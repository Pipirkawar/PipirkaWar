"""Юнит-тесты `AdminGuard` (Спринт 2.5-A.2)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, TelegramObject

from pipirik_wars.bot.middlewares.admin_guard import (
    DATA_KEY as ADMIN_DATA_KEY,
    AdminGuard,
)
from pipirik_wars.bot.middlewares.auth import DATA_KEY as AUTH_DATA_KEY, TgIdentity
from pipirik_wars.domain.admin import AdminRole
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.uow import FakeUnitOfWork


def _identity(*, tg_user_id: int = 42) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=-100,
        chat_kind="private",
        language_code="ru",
    )


@pytest.mark.asyncio
class TestAdminGuard:
    async def _run(
        self,
        *,
        admins: FakeAdminRepository,
        identity: TgIdentity | None,
    ) -> tuple[Any, dict[str, Any], FakeUnitOfWork]:
        uow = FakeUnitOfWork()
        mw = AdminGuard(uow=uow, admins=admins)
        data: dict[str, Any] = {AUTH_DATA_KEY: identity}
        event: TelegramObject = MagicMock(spec=Message)
        handler = AsyncMock(return_value="handler-result")
        result = await mw(handler, event, data)
        handler.assert_awaited_once_with(event, data)
        return result, data, uow

    async def test_no_identity_passes_through_with_admin_none(self) -> None:
        admins = FakeAdminRepository()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
        result, data, uow = await self._run(admins=admins, identity=None)

        assert result == "handler-result"
        assert data[ADMIN_DATA_KEY] is None
        # БД-roundtrip не должен происходить, если identity-а нет.
        assert uow.commits == 0
        assert uow.rollbacks == 0

    async def test_unknown_user_sets_admin_none(self) -> None:
        admins = FakeAdminRepository()
        # Залит другой админ — наш tg_user_id=42 ему не равен.
        admins.seed(tg_id=999, role=AdminRole.SUPER_ADMIN)

        result, data, uow = await self._run(
            admins=admins,
            identity=_identity(tg_user_id=42),
        )

        assert result == "handler-result"
        assert data[ADMIN_DATA_KEY] is None
        # Был вызов get_by_tg_id — UoW открыт-закрыт ровно один раз.
        assert uow.commits == 1

    async def test_active_admin_is_set_in_data(self) -> None:
        admins = FakeAdminRepository()
        admin = admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, is_active=True)

        result, data, _ = await self._run(
            admins=admins,
            identity=_identity(tg_user_id=42),
        )

        assert result == "handler-result"
        assert data[ADMIN_DATA_KEY] is admin

    async def test_inactive_admin_is_treated_as_none(self) -> None:
        """Деактивированные админы не считаются — ГДД §18.6 (revoke = отзыв прав)."""
        admins = FakeAdminRepository()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, is_active=False)

        result, data, _ = await self._run(
            admins=admins,
            identity=_identity(tg_user_id=42),
        )

        assert result == "handler-result"
        assert data[ADMIN_DATA_KEY] is None

    async def test_uow_is_committed_on_lookup(self) -> None:
        """`async with uow:` открывается-закрывается; rollback не должен вызываться."""
        admins = FakeAdminRepository()
        admins.seed(tg_id=42, role=AdminRole.ECONOMIST)

        _, _, uow = await self._run(
            admins=admins,
            identity=_identity(tg_user_id=42),
        )

        assert uow.commits == 1
        assert uow.rollbacks == 0

    async def test_propagates_handler_exception(self) -> None:
        """Если handler рейзит — middleware пробрасывает (свою транзакцию уже закоммитил)."""
        admins = FakeAdminRepository()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)

        uow = FakeUnitOfWork()
        mw = AdminGuard(uow=uow, admins=admins)
        data: dict[str, Any] = {AUTH_DATA_KEY: _identity(tg_user_id=42)}
        handler = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await mw(handler, MagicMock(spec=Message), data)

        assert data[ADMIN_DATA_KEY] is not None
        assert uow.commits == 1  # lookup-транзакция зафиксирована
        assert uow.rollbacks == 0  # rollback в middleware не должен происходить

    async def test_returns_handler_result_unchanged(self) -> None:
        """Middleware прозрачно возвращает то, что вернул handler."""
        admins = FakeAdminRepository()
        admins.seed(tg_id=42, role=AdminRole.READ_ONLY)

        uow = FakeUnitOfWork()
        mw = AdminGuard(uow=uow, admins=admins)
        data: dict[str, Any] = {AUTH_DATA_KEY: _identity(tg_user_id=42)}
        handler = AsyncMock(return_value=12345)

        result = await mw(handler, MagicMock(spec=Message), data)

        assert result == 12345
