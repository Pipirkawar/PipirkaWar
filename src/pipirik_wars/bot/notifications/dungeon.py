"""`TelegramDungeonFinishNotifier` — реализация `IDungeonFinishNotifier`.

Зеркалит `TelegramMountainFinishNotifier`. См. соседний модуль для
обоснования общего базового класса.
"""

from __future__ import annotations

import logging

from aiogram import Bot

from pipirik_wars.application.dungeon import (
    DungeonRunFinished,
    IDungeonFinishNotifier,
)
from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    IMessageBundle,
    IPlayerLocaleResolver,
    Locale,
)
from pipirik_wars.bot.notifications._pve import _PveFinishNotifierBase
from pipirik_wars.bot.presenters._pve import PvePresenter
from pipirik_wars.bot.presenters.dungeon import DungeonPresenter
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.pve import PveLocationKind


class TelegramDungeonFinishNotifier(
    _PveFinishNotifierBase[DungeonRunFinished],
    IDungeonFinishNotifier,
):
    """Доставка сообщения «вернулся из данжона» через aiogram-`Bot.send_message`."""

    def __init__(
        self,
        *,
        bot: Bot,
        balance: IBalanceConfig,
        bundle: IMessageBundle,
        locale_resolver: IPlayerLocaleResolver | None = None,
        default_locale: Locale = DEFAULT_LOCALE,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            bot=bot,
            balance=balance,
            bundle=bundle,
            kind=PveLocationKind.DUNGEON,
            locale_resolver=locale_resolver,
            default_locale=default_locale,
            logger=logger,
        )

    @staticmethod
    def _make_presenter(*, bundle: IMessageBundle, kind: PveLocationKind) -> PvePresenter:
        del kind  # ctor зашит в `DUNGEON`
        return DungeonPresenter(bundle=bundle)

    async def notify(self, result: DungeonRunFinished) -> None:
        await self._deliver(result)


__all__ = ["TelegramDungeonFinishNotifier"]
