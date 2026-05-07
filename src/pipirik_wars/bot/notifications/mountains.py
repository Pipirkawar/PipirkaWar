"""`TelegramMountainFinishNotifier` — реализация `IMountainFinishNotifier`.

Зеркалит `TelegramForestFinishNotifier` (см. `bot/notifications/forest.py`).
Шлёт сообщение «вернулся из гор» в личку игрока после успешного
`FinishMountainRun.execute(...)`. APScheduler-callback фильтрует
повторные вызовы по `was_already_finished` — здесь это пред-условие.
"""

from __future__ import annotations

import logging

from aiogram import Bot

from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    IMessageBundle,
    IPlayerLocaleResolver,
    Locale,
)
from pipirik_wars.application.mountains import (
    IMountainFinishNotifier,
    MountainRunFinished,
)
from pipirik_wars.bot.notifications._pve import _PveFinishNotifierBase
from pipirik_wars.bot.presenters._pve import PvePresenter
from pipirik_wars.bot.presenters.mountains import MountainsPresenter
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.pve import PveLocationKind


class TelegramMountainFinishNotifier(
    _PveFinishNotifierBase[MountainRunFinished],
    IMountainFinishNotifier,
):
    """Доставка сообщения «вернулся из гор» через aiogram-`Bot.send_message`."""

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
            kind=PveLocationKind.MOUNTAINS,
            locale_resolver=locale_resolver,
            default_locale=default_locale,
            logger=logger,
        )

    @staticmethod
    def _make_presenter(*, bundle: IMessageBundle, kind: PveLocationKind) -> PvePresenter:
        del kind  # ctor зашит в `MOUNTAINS`
        return MountainsPresenter(bundle=bundle)

    async def notify(self, result: MountainRunFinished) -> None:
        await self._deliver(result)


__all__ = ["TelegramMountainFinishNotifier"]
