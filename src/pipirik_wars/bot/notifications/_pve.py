"""Общий базовый класс PvE-нотификатора (Спринт 3.1-E, ГДД §8.2).

Mountains и dungeon структурно идентичны: оба после `Finish*Run` шлют
одно сообщение «вернулся из <локации>» в личку. Все различия (тип
`Run`-сущности и тип результата) параметризуются дженериком
`_PveFinishNotifierBase` — это держит mountains/dungeon notifier-ы
тонкими и эквивалентными между собой.

См. `bot/notifications/forest.py` как референс — именно его шаблон
повторяется здесь без `IForestLogTemplateProvider` (для гор/данжона
flavour-логи в Спринте 3.1-E не предусмотрены) и без `ReferralShare`-row
(share под PvE добавим в отдельную задачу — ГДД §13.2 пока только лес).
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Final, Generic, TypeVar

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from pipirik_wars.application.dungeon import DungeonRunFinished
from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    IMessageBundle,
    IPlayerLocaleResolver,
    Locale,
)
from pipirik_wars.application.mountains import MountainRunFinished
from pipirik_wars.bot.presenters._pve import PvePresenter
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import DisplayName
from pipirik_wars.domain.pve import PveLocationKind

PveResultT = TypeVar("PveResultT", MountainRunFinished, DungeonRunFinished)

_KIND_LOG_NAME: Final[dict[PveLocationKind, str]] = {
    PveLocationKind.MOUNTAINS: "mountain_notifier",
    PveLocationKind.DUNGEON: "dungeon_notifier",
}


class _PveFinishNotifierBase(Generic[PveResultT]):
    """Базовая реализация Telegram-нотификатора PvE-локации.

    Подкласс задаёт `_kind` и `_presenter`; общий код — резолв локали,
    рендер «полного ника» с актуальным `DisplayName`, отправка сообщения
    с inline-клавиатурой кнопок «надеть/выбросить».
    """

    __slots__ = (
        "_balance",
        "_bot",
        "_default_locale",
        "_locale_resolver",
        "_logger",
        "_presenter",
    )

    def __init__(
        self,
        *,
        bot: Bot,
        balance: IBalanceConfig,
        bundle: IMessageBundle,
        kind: PveLocationKind,
        locale_resolver: IPlayerLocaleResolver | None = None,
        default_locale: Locale = DEFAULT_LOCALE,
        logger: logging.Logger | None = None,
    ) -> None:
        self._bot = bot
        self._balance = balance
        self._presenter = self._make_presenter(bundle=bundle, kind=kind)
        self._locale_resolver = locale_resolver
        self._default_locale = default_locale
        self._logger = logger or logging.getLogger(_KIND_LOG_NAME[kind])

    @staticmethod
    @abstractmethod
    def _make_presenter(*, bundle: IMessageBundle, kind: PveLocationKind) -> PvePresenter:
        """Создаёт конкретный презентер (Mountains/DungeonPresenter)."""

    async def _deliver(self, result: PveResultT) -> None:
        """Общая логика отправки.

        Идемпотентность по `was_already_finished` — на стороне вызывающего
        (`infrastructure/scheduler/aps.py::_run_*_finish_job`).
        """
        player_after = result.player_after
        try:
            display_name = DisplayName(
                value=self._balance.get().display_name_for(player_after.length.cm),
            )
        except Exception:
            self._logger.exception(
                "pve_notifier: failed to compute display_name",
                extra={"run_id": result.run.id, "player_id": player_after.id},
            )
            return

        locale = await self._resolve_locale(player_after.tg_id)
        text = self._presenter.finished(
            result=result,
            display_name_after=display_name,
            locale=locale,
        )
        keyboard = self._presenter.finish_keyboard(result, locale=locale)

        try:
            await self._bot.send_message(
                chat_id=player_after.tg_id,
                text=text,
                reply_markup=keyboard,
            )
        except TelegramAPIError:
            # Игрок мог удалить чат с ботом / заблокировать бота.
            self._logger.warning(
                "pve_notifier: telegram delivery failed",
                extra={"run_id": result.run.id, "tg_id": player_after.tg_id},
            )
        except Exception:
            self._logger.exception(
                "pve_notifier: unexpected delivery error",
                extra={"run_id": result.run.id, "tg_id": player_after.tg_id},
            )

    async def _resolve_locale(self, tg_id: int) -> Locale:
        if self._locale_resolver is None:
            return self._default_locale
        try:
            resolved = await self._locale_resolver.resolve_for_tg_id(tg_id)
        except Exception:
            self._logger.exception(
                "pve_notifier: locale resolver failed",
                extra={"tg_id": tg_id},
            )
            return self._default_locale
        return resolved or self._default_locale


__all__ = ["_PveFinishNotifierBase"]
