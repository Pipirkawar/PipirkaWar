"""Unit-тесты handler-а `/clan_daily_head_history` (Спринт 2.5-D.3)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.admin import (
    DailyHeadHistoryEntry,
    GetClanDailyHeadHistory,
    GetClanDailyHeadHistoryOutput,
    PlayerSummary,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.bot.handlers.admin_clan import (
    REPLY_NON_PRIVATE_RU,
    handle_clan_daily_head_history,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.daily_head.entities import DailyHeadSource
from pipirik_wars.domain.player import PlayerStatus

_RU = Locale("ru")
_FIXED_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


class _StubBundle(IMessageBundle):
    def format(
        self,
        key: MessageKey,
        *,
        locale: Locale,
        **kwargs: object,
    ) -> str:
        params = ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"{key}|{locale.code}|{params}"


@pytest.fixture
def bundle() -> IMessageBundle:
    return _StubBundle()


def _msg_mock(chat_type: str = "private") -> MagicMock:
    msg = MagicMock()
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    return msg


def _identity(chat_kind: str = "private", tg_user_id: int = 42) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42 if chat_kind == "private" else -1,
        chat_kind=chat_kind,
        language_code=None,
    )


def _player_summary(*, tg_id: int = 100, username: str = "alice") -> PlayerSummary:
    return PlayerSummary(
        tg_id=tg_id,
        username=username,
        name="Alice",
        title=None,
        length_cm=10,
        thickness_level=1,
        status=PlayerStatus.ACTIVE,
        anticheat_ban_until=None,
    )


@pytest.mark.asyncio
class TestHandleClanDailyHeadHistory:
    async def test_non_private_chat_rejected(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        uc = MagicMock(spec=GetClanDailyHeadHistory)
        await handle_clan_daily_head_history(
            cast(Message, msg),
            CommandObject(command="clan_daily_head_history", args="1"),
            _identity(chat_kind="group"),
            uc,
            bundle,
            _RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_missing_identity_rejected(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = MagicMock(spec=GetClanDailyHeadHistory)
        await handle_clan_daily_head_history(
            cast(Message, msg),
            CommandObject(command="clan_daily_head_history", args="1"),
            None,
            uc,
            bundle,
            _RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_no_args_returns_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = MagicMock(spec=GetClanDailyHeadHistory)
        await handle_clan_daily_head_history(
            cast(Message, msg),
            CommandObject(command="clan_daily_head_history", args=None),
            _identity(),
            uc,
            bundle,
            _RU,
        )
        msg.answer.assert_awaited_once()
        call_arg = msg.answer.call_args[0][0]
        assert "admin-clan-daily-head-history-usage" in call_arg

    async def test_bad_id_rejected(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = MagicMock(spec=GetClanDailyHeadHistory)
        await handle_clan_daily_head_history(
            cast(Message, msg),
            CommandObject(command="clan_daily_head_history", args="abc"),
            _identity(),
            uc,
            bundle,
            _RU,
        )
        call_arg = msg.answer.call_args[0][0]
        assert "admin-clan-daily-head-history-bad-id" in call_arg

    async def test_bad_limit_rejected(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = MagicMock(spec=GetClanDailyHeadHistory)
        await handle_clan_daily_head_history(
            cast(Message, msg),
            CommandObject(command="clan_daily_head_history", args="1 abc"),
            _identity(),
            uc,
            bundle,
            _RU,
        )
        call_arg = msg.answer.call_args[0][0]
        assert "admin-clan-daily-head-history-bad-limit" in call_arg

    async def test_auth_error_returns_not_authorized(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        uc = MagicMock(spec=GetClanDailyHeadHistory)
        uc.execute = AsyncMock(
            side_effect=AuthorizationError(
                requirement="admin_active",
                detail="not admin",
            ),
        )
        await handle_clan_daily_head_history(
            cast(Message, msg),
            CommandObject(command="clan_daily_head_history", args="1"),
            _identity(),
            uc,
            bundle,
            _RU,
        )
        call_arg = msg.answer.call_args[0][0]
        assert "admin-clan-daily-head-history-not-authorized" in call_arg

    async def test_clan_not_found(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = MagicMock(spec=GetClanDailyHeadHistory)
        uc.execute = AsyncMock(
            return_value=GetClanDailyHeadHistoryOutput(
                query=999,
                clan_id=None,
                clan_title=None,
                entries=(),
            ),
        )
        await handle_clan_daily_head_history(
            cast(Message, msg),
            CommandObject(command="clan_daily_head_history", args="999"),
            _identity(),
            uc,
            bundle,
            _RU,
        )
        call_arg = msg.answer.call_args[0][0]
        assert "admin-clan-daily-head-history-not-found" in call_arg
        assert "query=999" in call_arg

    async def test_renders_history(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = MagicMock(spec=GetClanDailyHeadHistory)
        uc.execute = AsyncMock(
            return_value=GetClanDailyHeadHistoryOutput(
                query=1,
                clan_id=1,
                clan_title="The Pipiriks",
                entries=(
                    DailyHeadHistoryEntry(
                        moscow_date=date(2026, 5, 7),
                        assigned_at=_FIXED_NOW,
                        bonus_cm=5,
                        source=DailyHeadSource.BUTTON,
                        player=_player_summary(),
                    ),
                ),
            ),
        )
        await handle_clan_daily_head_history(
            cast(Message, msg),
            CommandObject(command="clan_daily_head_history", args="1"),
            _identity(),
            uc,
            bundle,
            _RU,
        )
        call_arg = msg.answer.call_args[0][0]
        assert "admin-clan-daily-head-history-header" in call_arg
        assert "admin-clan-daily-head-history-row" in call_arg

    async def test_renders_empty_history(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = MagicMock(spec=GetClanDailyHeadHistory)
        uc.execute = AsyncMock(
            return_value=GetClanDailyHeadHistoryOutput(
                query=1,
                clan_id=1,
                clan_title="Empty Clan",
                entries=(),
            ),
        )
        await handle_clan_daily_head_history(
            cast(Message, msg),
            CommandObject(command="clan_daily_head_history", args="1"),
            _identity(),
            uc,
            bundle,
            _RU,
        )
        call_arg = msg.answer.call_args[0][0]
        assert "admin-clan-daily-head-history-empty" in call_arg

    async def test_renders_orphan_player(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = MagicMock(spec=GetClanDailyHeadHistory)
        uc.execute = AsyncMock(
            return_value=GetClanDailyHeadHistoryOutput(
                query=1,
                clan_id=1,
                clan_title="C",
                entries=(
                    DailyHeadHistoryEntry(
                        moscow_date=date(2026, 5, 7),
                        assigned_at=_FIXED_NOW,
                        bonus_cm=5,
                        source=DailyHeadSource.CRON,
                        player=None,
                    ),
                ),
            ),
        )
        await handle_clan_daily_head_history(
            cast(Message, msg),
            CommandObject(command="clan_daily_head_history", args="1"),
            _identity(),
            uc,
            bundle,
            _RU,
        )
        call_arg = msg.answer.call_args[0][0]
        assert "admin-clan-daily-head-history-row-orphan" in call_arg

    async def test_passes_limit_to_use_case(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = MagicMock(spec=GetClanDailyHeadHistory)
        uc.execute = AsyncMock(
            return_value=GetClanDailyHeadHistoryOutput(
                query=1,
                clan_id=1,
                clan_title="C",
                entries=(),
            ),
        )
        await handle_clan_daily_head_history(
            cast(Message, msg),
            CommandObject(command="clan_daily_head_history", args="1 25"),
            _identity(),
            uc,
            bundle,
            _RU,
        )
        # Validate args passed to use-case
        actual_input = uc.execute.call_args[0][0]
        assert actual_input.query == 1
        assert actual_input.limit == 25
        assert actual_input.actor_tg_id == 42
