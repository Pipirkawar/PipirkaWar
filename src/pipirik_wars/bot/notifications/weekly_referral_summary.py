"""`TelegramWeeklyClanReferralSummaryNotifier` (Спринт 2.4.E.3, ГДД §13.3).

Отправляет еженедельную карточку рефералов клана в `clan.chat_id`.
Зовётся APScheduler-callback-ом (`infrastructure/scheduler/aps.py`)
сразу после `RunWeeklyClanReferralSummary.execute(...)` (по
воскресеньям 18:00 UTC).

Размещён в `bot/notifications/`, потому что использует
`WeeklyClanReferralSummaryPresenter` из `bot/presenters/`. Контракт
слоёв `bot → application` / `bot → infrastructure` соблюдается.

Best-effort доставка:
- любая `TelegramAPIError` (бот удалён из чата, чат недоступен) —
  поглощается и логируется;
- любая иная ошибка — поглощается и логируется (фон не должен падать);
- никакого ретрая — карточка показывается раз в неделю, дубликат не нужен.

Локаль: `default_locale` (по дефолту EN, ПД 1.5.2). Сообщение в
групповой чат — общее для всех участников, поэтому per-user override
не применяется. Если у клана появится `clan.locale_override` (Фаза 3) —
сюда будет добавлен `IClanLocaleResolver`, тут менять придётся
только конструктор.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    IMessageBundle,
    Locale,
)
from pipirik_wars.application.referral import (
    IWeeklyClanReferralSummaryNotifier,
    WeeklyClanReferralSummary,
)
from pipirik_wars.bot.presenters.weekly_referral_summary import (
    WeeklyClanReferralSummaryPresenter,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import DisplayName


class TelegramWeeklyClanReferralSummaryNotifier(IWeeklyClanReferralSummaryNotifier):
    """Доставка weekly-сводки клана через aiogram-`Bot.send_message`."""

    __slots__ = (
        "_balance",
        "_bot",
        "_default_locale",
        "_logger",
        "_presenter",
    )

    def __init__(
        self,
        *,
        bot: Bot,
        bundle: IMessageBundle,
        balance: IBalanceConfig,
        default_locale: Locale = DEFAULT_LOCALE,
        logger: logging.Logger | None = None,
    ) -> None:
        self._bot = bot
        self._presenter = WeeklyClanReferralSummaryPresenter(bundle=bundle)
        self._balance = balance
        self._default_locale = default_locale
        self._logger = logger or logging.getLogger(__name__)

    async def notify(self, summary: WeeklyClanReferralSummary) -> None:
        # Use-case фильтрует пустые недели заранее (`total == 0` → None),
        # поэтому до сюда долетают только сводки с >= 1 реферером.
        display_names = [
            self._compute_display_name(length_cm=entry.player.length.cm) for entry in summary.top
        ]
        try:
            text = self._presenter.render(
                summary,
                locale=self._default_locale,
                display_names=display_names,
            )
        except Exception:
            self._logger.exception(
                "weekly_referral_summary_notifier: failed to render text",
                extra={"clan_id": summary.clan.id},
            )
            return

        try:
            await self._bot.send_message(
                chat_id=summary.clan.chat_id,
                text=text,
            )
        except TelegramAPIError:
            self._logger.warning(
                "weekly_referral_summary_notifier: telegram delivery failed",
                extra={
                    "clan_id": summary.clan.id,
                    "chat_id": summary.clan.chat_id,
                },
            )
        except Exception:
            self._logger.exception(
                "weekly_referral_summary_notifier: unexpected delivery error",
                extra={
                    "clan_id": summary.clan.id,
                    "chat_id": summary.clan.chat_id,
                },
            )

    def _compute_display_name(self, *, length_cm: int) -> DisplayName | None:
        """Best-effort: если `IBalanceConfig` не отдал диапазон —
        отдаём `None` и презентер фолбэчит на `@username`.
        """
        try:
            return DisplayName(value=self._balance.get().display_name_for(length_cm))
        except Exception:
            self._logger.exception(
                "weekly_referral_summary_notifier: failed to compute display_name",
                extra={"length_cm": length_cm},
            )
            return None


__all__ = ["TelegramWeeklyClanReferralSummaryNotifier"]
