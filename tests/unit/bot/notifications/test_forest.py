"""Unit-тесты `TelegramForestFinishNotifier` (Спринт 1.3.D)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardMarkup

from pipirik_wars.application.forest import ForestRunFinished
from pipirik_wars.bot.notifications import TelegramForestFinishNotifier
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.forest import (
    ForestRun,
    ForestRunStatus,
    Item,
    ItemDrop,
    Name,
    NameDrop,
    NoDrop,
    Rarity,
    Slot,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerName,
    PlayerStatus,
    Thickness,
    Title,
    Username,
)
from pipirik_wars.domain.shared.ports import IUnitOfWork
from tests.fakes import FakePlayerRepository

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


@dataclass
class _SendCall:
    chat_id: int | str
    text: str
    reply_markup: InlineKeyboardMarkup | None


@dataclass
class _FakeBot:
    """Минимальная замена `aiogram.Bot.send_message` для тестов нотификатора.

    Кастится в `Bot` через `cast(...)`, чтобы mypy не пытался валидировать
    весь огромный список именованных параметров `send_message`.
    """

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
    last_length_cm: int | None = None

    def get(self) -> BalanceConfig:
        if self.raise_exc is not None:
            raise self.raise_exc
        outer = self

        class _SnapshotShim:
            def display_name_for(self, length_cm: int) -> str:
                outer.last_length_cm = length_cm
                return outer.display_name

        return cast(BalanceConfig, _SnapshotShim())


@dataclass
class _FakeUnitOfWork(IUnitOfWork):
    """Минимальный stub: реальные транзакции нотификатор не открывает."""

    async def __aenter__(self) -> _FakeUnitOfWork:
        return self

    async def __aexit__(self, *_a: Any) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _player(*, length_cm: int = 7, name: PlayerName | None = None) -> Player:
    return Player(
        id=1,
        tg_id=1001,
        username=Username(value="alice"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=1),
        title=Title.NEWBIE,
        name=name,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _run(*, drop: NoDrop | ItemDrop | NameDrop) -> ForestRun:
    return ForestRun(
        id=11,
        player_id=1,
        status=ForestRunStatus.FINISHED,
        started_at=_NOW - timedelta(minutes=15),
        ends_at=_NOW,
        finished_at=_NOW,
        branch_name="normal",
        length_delta_cm=5,
        drop=drop,
    )


def _result(
    *,
    drop: NoDrop | ItemDrop | NameDrop | None = None,
    was_already_finished: bool = False,
    granted_title: bool = True,
    granted_name: bool = False,
    after: Player | None = None,
) -> ForestRunFinished:
    actual_drop: NoDrop | ItemDrop | NameDrop = drop if drop is not None else NoDrop()
    before = _player(length_cm=2, name=None)
    after_player = after if after is not None else _player(length_cm=7)
    return ForestRunFinished(
        run=_run(drop=actual_drop),
        player_before=before,
        player_after=after_player,
        granted_title=granted_title,
        granted_name=granted_name,
        was_already_finished=was_already_finished,
    )


def _make_notifier(
    *,
    bot: _FakeBot,
    balance: _FakeBalanceConfig | None = None,
    logger: logging.Logger | None = None,
) -> TelegramForestFinishNotifier:
    return TelegramForestFinishNotifier(
        bot=cast(Bot, bot),
        players=FakePlayerRepository(),
        balance=balance if balance is not None else _FakeBalanceConfig(),
        uow=_FakeUnitOfWork(),
        logger=logger,
    )


# ----------------------- Тесты -----------------------


@pytest.mark.asyncio
async def test_skips_when_was_already_finished() -> None:
    bot = _FakeBot()
    notifier = _make_notifier(bot=bot)
    await notifier.notify(_result(was_already_finished=True))
    assert bot.calls == []


@pytest.mark.asyncio
async def test_sends_message_with_text_and_no_keyboard_for_no_drop() -> None:
    bot = _FakeBot()
    notifier = _make_notifier(bot=bot, balance=_FakeBalanceConfig(display_name="Пипирик"))
    await notifier.notify(_result(drop=NoDrop()))
    assert len(bot.calls) == 1
    call = bot.calls[0]
    assert call.chat_id == 1001
    assert "вернулся из леса" in call.text
    assert "+5 см" in call.text
    assert call.reply_markup is None


@pytest.mark.asyncio
async def test_sends_message_with_keyboard_for_item_drop() -> None:
    bot = _FakeBot()
    notifier = _make_notifier(bot=bot)
    item = Item(
        id="item.hat.berserker",
        display_name="Шлем Берсерка",
        slot=Slot.HAT,
        rarity=Rarity.EPIC,
    )
    await notifier.notify(_result(drop=ItemDrop(item=item)))
    call = bot.calls[0]
    assert call.reply_markup is not None
    assert "Шлем Берсерка" in call.text


@pytest.mark.asyncio
async def test_sends_message_with_keyboard_for_name_drop_replacement() -> None:
    bot = _FakeBot()
    notifier = _make_notifier(bot=bot)
    after_with_old_name = _player(length_cm=7, name=PlayerName(value="Старое"))
    result = _result(
        drop=NameDrop(name=Name(value="Новое")),
        granted_name=False,
        after=after_with_old_name,
    )
    await notifier.notify(result)
    call = bot.calls[0]
    assert call.reply_markup is not None
    assert "Нашёл имя: Новое" in call.text


def _telegram_api_error() -> TelegramAPIError:
    """Сконструировать `TelegramAPIError` без зависимости от реального Bot."""
    method = SendMessage(chat_id=1, text="x")
    return TelegramAPIError(method=method, message="blocked")


@pytest.mark.asyncio
async def test_swallows_telegram_api_error() -> None:
    bot = _FakeBot(raise_exc=_telegram_api_error())
    logger = logging.getLogger("test.forest_notifier")
    notifier = _make_notifier(bot=bot, logger=logger)
    # Не должно бросить — best-effort контракт.
    await notifier.notify(_result())


@pytest.mark.asyncio
async def test_swallows_unexpected_error() -> None:
    bot = _FakeBot(raise_exc=RuntimeError("network down"))
    logger = logging.getLogger("test.forest_notifier")
    notifier = _make_notifier(bot=bot, logger=logger)
    await notifier.notify(_result())


@pytest.mark.asyncio
async def test_swallows_balance_error_without_sending() -> None:
    """Если баланс упал на расчёте display_name — не падаем, не шлём."""
    bot = _FakeBot()
    balance = _FakeBalanceConfig(raise_exc=RuntimeError("yaml broken"))
    notifier = _make_notifier(bot=bot, balance=balance)
    await notifier.notify(_result())
    assert bot.calls == []


@pytest.mark.asyncio
async def test_recomputes_display_name_using_after_length() -> None:
    bot = _FakeBot()
    balance = _FakeBalanceConfig(display_name="Бананчик")
    notifier = _make_notifier(bot=bot, balance=balance)
    await notifier.notify(_result())
    assert balance.last_length_cm == 7


@pytest.mark.asyncio
async def test_uses_default_logger_when_none_provided() -> None:
    bot = _FakeBot()
    notifier = TelegramForestFinishNotifier(
        bot=cast(Bot, bot),
        players=FakePlayerRepository(),
        balance=_FakeBalanceConfig(),
        uow=_FakeUnitOfWork(),
    )
    # Конструктор не падает без logger; notify работает.
    await notifier.notify(_result())
    assert len(bot.calls) == 1
