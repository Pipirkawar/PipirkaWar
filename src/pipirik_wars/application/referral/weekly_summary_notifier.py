"""Порт нотификации weekly-сводки клана (Спринт 2.4.E, ГДД §13.3).

Отдельный порт — по той же логике, что и `IForestFinishNotifier`:

- use-case (`RunWeeklyClanReferralSummary`) живёт в application-слое
  и не должен знать про Telegram (правило ГДД §0.3 «нет I/O внутри
  транзакции»);
- если нотификация упадёт — состояние клана (`referrals`) всё равно
  консистентно (мы только читаем); notifier — best-effort;
- метод `notify(...)` зовётся **только** при `total > 0` (use-case
  отдаёт `None` при пустой неделе — спам-карточек «никого не пригласил»
  нет).

Реализация (`TelegramWeeklyClanReferralSummaryNotifier`) знает про
aiogram-бот и `WeeklyClanReferralSummaryPresenter`-форматирование; сам
контракт здесь — чистый.
"""

from __future__ import annotations

import abc

from pipirik_wars.application.referral.weekly_summary_dto import (
    WeeklyClanReferralSummary,
)


class IWeeklyClanReferralSummaryNotifier(abc.ABC):
    """Контракт «прислать в чат клана еженедельную карточку рефералов»."""

    @abc.abstractmethod
    async def notify(self, summary: WeeklyClanReferralSummary) -> None:
        """Отправить карточку в `summary.clan.chat_id`.

        Вызывается **только** при `summary.total > 0` (use-case фильтрует
        пустые недели заранее).

        Любые ошибки доставки (`TelegramAPIError`, network, бот удалён
        из чата) реализация обязана поглотить и залогировать —
        нотификация best-effort, шедулер продолжает обходить остальные
        кланы.
        """


__all__ = ["IWeeklyClanReferralSummaryNotifier"]
