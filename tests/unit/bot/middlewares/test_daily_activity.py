"""Юнит-тесты `DailyActivityMiddleware` (Спринт 2.3.F.1)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message, TelegramObject

from pipirik_wars.bot.middlewares.auth import DATA_KEY as AUTH_DATA_KEY, TgIdentity
from pipirik_wars.bot.middlewares.daily_activity import DailyActivityMiddleware


def _identity(*, chat_kind: str) -> TgIdentity:
    return TgIdentity(
        tg_user_id=42,
        chat_id=-100123,
        chat_kind=chat_kind,
        language_code="ru",
    )


def _message_event() -> TelegramObject:
    """Реальный `Message`-spec — middleware проверяет `isinstance`."""
    return MagicMock(spec=Message)


@pytest.mark.asyncio
class TestDailyActivityMiddleware:
    async def _run(
        self,
        *,
        event: TelegramObject,
        identity: TgIdentity | None,
        use_case: AsyncMock,
    ) -> Any:
        mw = DailyActivityMiddleware(use_case=MagicMock(execute=use_case))
        data: dict[str, Any] = {AUTH_DATA_KEY: identity}
        handler = AsyncMock(return_value="handler-result")
        result = await mw(handler, event, data)
        handler.assert_awaited_once_with(event, data)
        return result

    async def test_records_activity_for_message_in_group(self) -> None:
        use_case = AsyncMock(return_value=True)
        result = await self._run(
            event=_message_event(),
            identity=_identity(chat_kind="group"),
            use_case=use_case,
        )

        assert result == "handler-result"
        use_case.assert_awaited_once()
        # Argument: RecordPlayerActivityInput(tg_user_id=42).
        call_arg = use_case.await_args.args[0]
        assert call_arg.tg_user_id == 42

    async def test_records_activity_for_message_in_supergroup(self) -> None:
        use_case = AsyncMock(return_value=True)
        await self._run(
            event=_message_event(),
            identity=_identity(chat_kind="supergroup"),
            use_case=use_case,
        )
        use_case.assert_awaited_once()

    async def test_skips_private_chat(self) -> None:
        use_case = AsyncMock(return_value=True)
        await self._run(
            event=_message_event(),
            identity=_identity(chat_kind="private"),
            use_case=use_case,
        )
        use_case.assert_not_awaited()

    async def test_skips_channel(self) -> None:
        use_case = AsyncMock(return_value=True)
        await self._run(
            event=_message_event(),
            identity=_identity(chat_kind="channel"),
            use_case=use_case,
        )
        use_case.assert_not_awaited()

    async def test_skips_when_no_identity(self) -> None:
        use_case = AsyncMock(return_value=True)
        await self._run(
            event=_message_event(),
            identity=None,
            use_case=use_case,
        )
        use_case.assert_not_awaited()

    async def test_skips_callback_query(self) -> None:
        use_case = AsyncMock(return_value=True)
        await self._run(
            event=MagicMock(spec=CallbackQuery),
            identity=_identity(chat_kind="group"),
            use_case=use_case,
        )
        use_case.assert_not_awaited()

    async def test_skips_chat_member_updated(self) -> None:
        use_case = AsyncMock(return_value=True)
        await self._run(
            event=MagicMock(spec=ChatMemberUpdated),
            identity=_identity(chat_kind="supergroup"),
            use_case=use_case,
        )
        use_case.assert_not_awaited()

    async def test_handler_runs_even_when_use_case_raises(self) -> None:
        """Падение записи активности не должно ронять команду пользователя."""
        use_case = AsyncMock(side_effect=RuntimeError("DB down"))
        mw = DailyActivityMiddleware(use_case=MagicMock(execute=use_case))
        event = _message_event()
        identity = _identity(chat_kind="group")
        data: dict[str, Any] = {AUTH_DATA_KEY: identity}
        handler = AsyncMock(return_value="still-runs")

        result = await mw(handler, event, data)

        assert result == "still-runs"
        handler.assert_awaited_once_with(event, data)
        use_case.assert_awaited_once()

    async def test_use_case_returning_false_is_silent(self) -> None:
        """No-op результат use-case-а (`False`) не должен влиять на handler."""
        use_case = AsyncMock(return_value=False)
        result = await self._run(
            event=_message_event(),
            identity=_identity(chat_kind="group"),
            use_case=use_case,
        )
        assert result == "handler-result"
        use_case.assert_awaited_once()
