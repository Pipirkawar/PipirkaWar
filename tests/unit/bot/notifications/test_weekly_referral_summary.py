"""Unit-тесты `TelegramWeeklyClanReferralSummaryNotifier` (Спринт 2.4.E.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.referral import (
    WeeklyClanReferralEntryDTO,
    WeeklyClanReferralSummary,
)
from pipirik_wars.bot.notifications import TelegramWeeklyClanReferralSummaryNotifier
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanStatus,
    ClanTitle,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerStatus,
    Thickness,
    Username,
)
from tests.fakes import FakeMessageBundle

_NOW = datetime(2026, 5, 10, 18, 0, tzinfo=UTC)


@dataclass
class _SendCall:
    chat_id: int | str
    text: str


@dataclass
class _FakeBot:
    calls: list[_SendCall] = field(default_factory=list)
    raise_exc: BaseException | None = None

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        **_kwargs: Any,
    ) -> None:
        self.calls.append(_SendCall(chat_id=chat_id, text=text))
        if self.raise_exc is not None:
            raise self.raise_exc


@dataclass
class _FakeBalanceConfig(IBalanceConfig):
    display_name: str = "Пипирик"
    raise_exc: BaseException | None = None

    def get(self) -> BalanceConfig:
        if self.raise_exc is not None:
            raise self.raise_exc
        outer = self

        class _SnapshotShim:
            def display_name_for(self, length_cm: int) -> str:
                return outer.display_name

        return cast(BalanceConfig, _SnapshotShim())


def _make_player(*, pid: int) -> Player:
    return Player(
        id=pid,
        tg_id=1000 + pid,
        username=Username(value=f"u{pid}"),
        length=Length(cm=50),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_summary(top_count: int = 1, total: int = 1) -> WeeklyClanReferralSummary:
    top = tuple(
        WeeklyClanReferralEntryDTO(
            player=_make_player(pid=10 + i),
            count=top_count - i,
        )
        for i in range(top_count)
    )
    clan = Clan(
        id=1,
        chat_id=-100123,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value="Огурцы"),
        status=ClanStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )
    return WeeklyClanReferralSummary(clan=clan, total=total, top=top)


def _make_notifier(
    *,
    bot: _FakeBot,
    balance: _FakeBalanceConfig | None = None,
) -> TelegramWeeklyClanReferralSummaryNotifier:
    return TelegramWeeklyClanReferralSummaryNotifier(
        bot=cast(Bot, bot),
        bundle=cast(IMessageBundle, FakeMessageBundle()),
        balance=balance or _FakeBalanceConfig(),
        default_locale=Locale("en"),
    )


class TestTelegramWeeklyClanReferralSummaryNotifier:
    @pytest.mark.asyncio
    async def test_sends_message_to_clan_chat(self) -> None:
        bot = _FakeBot()
        notifier = _make_notifier(bot=bot)
        summary = _make_summary(top_count=2, total=5)
        await notifier.notify(summary)

        assert len(bot.calls) == 1
        call = bot.calls[0]
        assert call.chat_id == -100123
        assert "weekly-referral-summary-title" in call.text
        assert "weekly-referral-summary-total" in call.text

    @pytest.mark.asyncio
    async def test_telegram_error_is_swallowed(self) -> None:
        bot = _FakeBot(raise_exc=TelegramAPIError(method=None, message="kicked"))  # type: ignore[arg-type]
        notifier = _make_notifier(bot=bot)
        summary = _make_summary(top_count=1, total=1)
        # Не падаем.
        await notifier.notify(summary)
        assert len(bot.calls) == 1

    @pytest.mark.asyncio
    async def test_unexpected_error_is_swallowed(self) -> None:
        bot = _FakeBot(raise_exc=RuntimeError("boom"))
        notifier = _make_notifier(bot=bot)
        summary = _make_summary(top_count=1, total=1)
        await notifier.notify(summary)

    @pytest.mark.asyncio
    async def test_balance_failure_falls_back_to_no_display_name(self) -> None:
        bot = _FakeBot()
        notifier = _make_notifier(
            bot=bot,
            balance=_FakeBalanceConfig(raise_exc=RuntimeError("balance broken")),
        )
        summary = _make_summary(top_count=1, total=1)
        await notifier.notify(summary)
        assert len(bot.calls) == 1
