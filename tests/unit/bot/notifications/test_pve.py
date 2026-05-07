"""Unit-тесты `TelegramMountainFinishNotifier` / `TelegramDungeonFinishNotifier` (Спринт 3.1-E).

Параметризованные сюжетные линии: оба нотификатора структурно идентичны,
тестируем оба в одном файле через параметризацию `kind`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from pipirik_wars.application.dungeon import DungeonRunFinished
from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.mountains import MountainRunFinished
from pipirik_wars.bot.notifications import (
    TelegramDungeonFinishNotifier,
    TelegramMountainFinishNotifier,
)
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.dungeon import DungeonRun, DungeonRunStatus
from pipirik_wars.domain.mountains import MountainRun, MountainRunStatus
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.domain.pve import Item, PveItemDrop, Rarity, Slot
from tests.fakes import FakeMessageBundle, FakePlayerLocaleResolver

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_RU = Locale("ru")
_EN = Locale("en")


@dataclass
class _SendCall:
    chat_id: int | str
    text: str
    reply_markup: InlineKeyboardMarkup | None


@dataclass
class _FakeBot:
    """Минимальная замена `aiogram.Bot.send_message` для тестов."""

    calls: list[_SendCall] = field(default_factory=list)
    raise_exc: BaseException | None = None

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        **_kwargs: Any,
    ) -> None:
        self.calls.append(_SendCall(chat_id=chat_id, text=text, reply_markup=reply_markup))
        if self.raise_exc is not None:
            raise self.raise_exc


@dataclass
class _FakeBalanceConfig(IBalanceConfig):
    """Stub `IBalanceConfig`: возвращает заранее переданный `display_name`."""

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


def _player(*, length_cm: int = 47, tg_id: int = 100) -> Player:
    return Player(
        id=1,
        tg_id=tg_id,
        username=Username(value="alice"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=3),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _mountain_run(
    *,
    rid: int = 11,
    length_delta_cm: int = 5,
    drops: tuple[PveItemDrop, ...] = (),
) -> MountainRun:
    return MountainRun(
        id=rid,
        player_id=1,
        status=MountainRunStatus.FINISHED,
        started_at=_NOW - timedelta(minutes=15),
        ends_at=_NOW,
        finished_at=_NOW,
        branch_name="normal_gain",
        length_delta_cm=length_delta_cm,
        drops=drops,
    )


def _dungeon_run(
    *,
    rid: int = 11,
    length_delta_cm: int = 5,
    drops: tuple[PveItemDrop, ...] = (),
) -> DungeonRun:
    return DungeonRun(
        id=rid,
        player_id=1,
        status=DungeonRunStatus.FINISHED,
        started_at=_NOW - timedelta(minutes=15),
        ends_at=_NOW,
        finished_at=_NOW,
        branch_name="normal_gain",
        length_delta_cm=length_delta_cm,
        drops=drops,
    )


def _mountain_finished(
    *,
    length_delta_cm: int = 5,
    drops: tuple[PveItemDrop, ...] = (),
) -> MountainRunFinished:
    return MountainRunFinished(
        run=_mountain_run(length_delta_cm=length_delta_cm, drops=drops),
        player_before=_player(length_cm=42),
        player_after=_player(length_cm=42 + length_delta_cm),
        was_already_finished=False,
    )


def _dungeon_finished(
    *,
    length_delta_cm: int = 5,
    drops: tuple[PveItemDrop, ...] = (),
) -> DungeonRunFinished:
    return DungeonRunFinished(
        run=_dungeon_run(length_delta_cm=length_delta_cm, drops=drops),
        player_before=_player(length_cm=42),
        player_after=_player(length_cm=42 + length_delta_cm),
        was_already_finished=False,
    )


def _bundle() -> IMessageBundle:
    return FakeMessageBundle()


def _build_mountain_notifier(
    *,
    bot: _FakeBot,
    balance: _FakeBalanceConfig | None = None,
    locale_resolver: FakePlayerLocaleResolver | None = None,
    default_locale: Locale = _RU,
) -> TelegramMountainFinishNotifier:
    return TelegramMountainFinishNotifier(
        bot=cast(Bot, bot),
        balance=balance or _FakeBalanceConfig(),
        bundle=_bundle(),
        locale_resolver=locale_resolver,
        default_locale=default_locale,
    )


def _build_dungeon_notifier(
    *,
    bot: _FakeBot,
    balance: _FakeBalanceConfig | None = None,
    locale_resolver: FakePlayerLocaleResolver | None = None,
    default_locale: Locale = _RU,
) -> TelegramDungeonFinishNotifier:
    return TelegramDungeonFinishNotifier(
        bot=cast(Bot, bot),
        balance=balance or _FakeBalanceConfig(),
        bundle=_bundle(),
        locale_resolver=locale_resolver,
        default_locale=default_locale,
    )


@pytest.mark.asyncio
class TestMountainNotifier:
    async def test_sends_message_to_player(self) -> None:
        bot = _FakeBot()
        notifier = _build_mountain_notifier(bot=bot)
        await notifier.notify(_mountain_finished(length_delta_cm=5))

        assert len(bot.calls) == 1
        call = bot.calls[0]
        assert call.chat_id == 100
        assert "mountains-finished-header" in call.text
        assert "mountains-finished-length-gain" in call.text
        # Без дропов клавиатуры нет.
        assert call.reply_markup is None

    async def test_sends_message_with_drops_and_keyboard(self) -> None:
        bot = _FakeBot()
        notifier = _build_mountain_notifier(bot=bot)
        item = Item(id="item.head.cap", display_name="Cap", slot=Slot.HAT, rarity=Rarity.COMMON)
        await notifier.notify(_mountain_finished(drops=(PveItemDrop(item=item),)))

        assert len(bot.calls) == 1
        call = bot.calls[0]
        assert call.reply_markup is not None
        assert len(call.reply_markup.inline_keyboard) == 1
        for btn in call.reply_markup.inline_keyboard[0]:
            assert btn.callback_data is not None
            assert btn.callback_data.startswith("mountains:")

    async def test_locale_resolver_used(self) -> None:
        bot = _FakeBot()
        resolver = FakePlayerLocaleResolver({100: _EN})
        notifier = _build_mountain_notifier(bot=bot, locale_resolver=resolver)
        await notifier.notify(_mountain_finished(length_delta_cm=3))

        assert "en:mountains-finished-header" in bot.calls[0].text

    async def test_locale_resolver_failure_falls_back_to_default(self) -> None:
        bot = _FakeBot()

        class _BoomResolver:
            async def resolve_for_tg_id(self, tg_id: int) -> Locale | None:
                raise RuntimeError("db down")

        notifier = TelegramMountainFinishNotifier(
            bot=cast(Bot, bot),
            balance=_FakeBalanceConfig(),
            bundle=_bundle(),
            locale_resolver=cast(Any, _BoomResolver()),
            default_locale=_RU,
            logger=logging.getLogger("test_pve_notifier"),
        )
        await notifier.notify(_mountain_finished())
        assert "ru:mountains-finished-header" in bot.calls[0].text

    async def test_telegram_api_error_swallowed(self) -> None:
        bot = _FakeBot(raise_exc=TelegramAPIError(method=cast(Any, None), message="blocked"))
        notifier = _build_mountain_notifier(bot=bot)
        # Не должно бросать наружу.
        await notifier.notify(_mountain_finished())
        assert len(bot.calls) == 1

    async def test_balance_failure_short_circuits_delivery(self) -> None:
        bot = _FakeBot()
        balance = _FakeBalanceConfig(raise_exc=RuntimeError("balance broken"))
        notifier = _build_mountain_notifier(bot=bot, balance=balance)
        await notifier.notify(_mountain_finished())
        # Сообщение НЕ отправлено.
        assert bot.calls == []


@pytest.mark.asyncio
class TestDungeonNotifier:
    async def test_sends_message_to_player(self) -> None:
        bot = _FakeBot()
        notifier = _build_dungeon_notifier(bot=bot)
        await notifier.notify(_dungeon_finished(length_delta_cm=-7))

        assert len(bot.calls) == 1
        call = bot.calls[0]
        assert "dungeon-finished-header" in call.text
        assert "dungeon-finished-length-loss" in call.text

    async def test_sends_message_with_drops_and_keyboard(self) -> None:
        bot = _FakeBot()
        notifier = _build_dungeon_notifier(bot=bot)
        item = Item(id="item.head.cap", display_name="Cap", slot=Slot.HAT, rarity=Rarity.COMMON)
        await notifier.notify(_dungeon_finished(drops=(PveItemDrop(item=item),)))

        assert bot.calls[0].reply_markup is not None
        for btn in bot.calls[0].reply_markup.inline_keyboard[0]:
            assert btn.callback_data is not None
            assert btn.callback_data.startswith("dungeon:")

    async def test_telegram_api_error_swallowed(self) -> None:
        bot = _FakeBot(raise_exc=TelegramAPIError(method=cast(Any, None), message="blocked"))
        notifier = _build_dungeon_notifier(bot=bot)
        await notifier.notify(_dungeon_finished())
        assert len(bot.calls) == 1
