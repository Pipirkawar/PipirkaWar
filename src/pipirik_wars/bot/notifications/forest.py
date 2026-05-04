"""`TelegramForestFinishNotifier` — реализация `IForestFinishNotifier`.

Шлёт сообщение «вернулся из леса» (ГДД §8.2) в личный чат игрока
после успешного `FinishForestRun` (Спринт 1.3.C). Используется
APScheduler-callback-ом (`infrastructure/scheduler/aps.py`) сразу
после коммита транзакции — это значит, что игровое состояние уже
консистентно (длина начислена, лок снят, аудит записан), а нотификация
— best-effort: ошибки доставки только логируются, на состояние не
влияют.

Размещён в `bot/notifications/`, а не в `infrastructure/telegram/`,
потому что использует презентеры из `bot/presenters/` (в т.ч.
`InlineKeyboardMarkup`). Контракт слоёв `bot → application` /
`bot → infrastructure` соблюдается; обратные ссылки запрещены
`import-linter`-ом.

Контракт `IForestFinishNotifier.notify(...)`:
- Если `result.was_already_finished is True` — no-op (повторный
  finish-job, рестарт воркера).
- Любая `TelegramAPIError` / общая ошибка — поглощается и логируется.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from pipirik_wars.application.forest import ForestRunFinished, IForestFinishNotifier
from pipirik_wars.bot.presenters.forest import (
    build_finish_keyboard,
    render_forest_finished,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import DisplayName, IPlayerRepository
from pipirik_wars.domain.shared.ports import IUnitOfWork


class TelegramForestFinishNotifier(IForestFinishNotifier):
    """Доставка «вернулся из леса» через aiogram-`Bot.send_message`.

    Адресат — `result.player_after.tg_id`. Бот регистрирует игроков
    только в ЛС (`RegisterPlayer`-контракт), поэтому `chat_id == tg_id`
    всегда валиден. В будущих фазах (например, broadcast в чат клана)
    появится `IClanBroadcaster`, тут менять не придётся.
    """

    __slots__ = ("_balance", "_bot", "_logger", "_players", "_uow")

    def __init__(
        self,
        *,
        bot: Bot,
        players: IPlayerRepository,
        balance: IBalanceConfig,
        uow: IUnitOfWork,
        logger: logging.Logger | None = None,
    ) -> None:
        self._bot = bot
        self._players = players
        self._balance = balance
        self._uow = uow
        self._logger = logger or logging.getLogger(__name__)

    async def notify(self, result: ForestRunFinished) -> None:
        if result.was_already_finished:
            # Идемпотентный no-op: повторный finish-job (рестарт воркера)
            # не должен спамить игрока. Audit и состояние уже не меняются
            # внутри FinishForestRun в этом случае.
            return

        player_after = result.player_after
        try:
            display_name = self._compute_display_name(length_cm=player_after.length.cm)
        except Exception:
            self._logger.exception(
                "forest_notifier: failed to compute display_name",
                extra={"run_id": result.run.id, "player_id": player_after.id},
            )
            return

        text = render_forest_finished(
            result=result,
            display_name_after=display_name,
        )
        keyboard = build_finish_keyboard(result)

        try:
            await self._bot.send_message(
                chat_id=player_after.tg_id,
                text=text,
                reply_markup=keyboard,
            )
        except TelegramAPIError:
            # Игрок мог удалить чат с ботом / заблокировать бота.
            # Это не ошибка use-case-а — фиксируем и идём дальше.
            self._logger.warning(
                "forest_notifier: telegram delivery failed",
                extra={"run_id": result.run.id, "tg_id": player_after.tg_id},
            )
        except Exception:
            self._logger.exception(
                "forest_notifier: unexpected delivery error",
                extra={"run_id": result.run.id, "tg_id": player_after.tg_id},
            )

    def _compute_display_name(self, *, length_cm: int) -> DisplayName:
        """Достать `DisplayName` из текущего `IBalanceConfig.get()`.

        Не открываем UoW: `IBalanceConfig` — read-only in-memory снимок.
        """
        return DisplayName(value=self._balance.get().display_name_for(length_cm))


__all__ = ["TelegramForestFinishNotifier"]
