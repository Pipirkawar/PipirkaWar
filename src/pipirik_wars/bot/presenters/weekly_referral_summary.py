"""Презентер еженедельной сводки рефералов клана (Спринт 2.4.E.3, ГДД §13.3).

Формирует текст карточки «📊 ИТОГИ НЕДЕЛИ — Клан "X"», которую
отправляет `TelegramWeeklyClanReferralSummaryNotifier` в чат клана
по cron-у в воскресенье 18:00 UTC.

В отличие от полной weekly-карточки из ГДД §13.3 (PvP / караваны /
рейды / место в топе), мы пока показываем только **реферальную**
сводку — остальные агрегаты появятся в Фазе 3 (ГДД §1, ПД 2.4).
Оформление поэтому компактное: заголовок + total + Топ-3 рефереров +
короткий футер.

Шаблоны лежат в `locales/{ru,en}.ftl` под ключами
`weekly-referral-summary-{title, total, line, footer}`. Текст
собирается из частей через `_join`, чтобы Fluent-параметризация
оставалась простой и легко-локализуемой.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.referral.weekly_summary_dto import (
    WeeklyClanReferralSummary,
)
from pipirik_wars.bot.presenters.profile import title_message_key
from pipirik_wars.domain.player import DisplayName, Player

_KEY_TITLE: Final[MessageKey] = MessageKey("weekly-referral-summary-title")
_KEY_TOTAL: Final[MessageKey] = MessageKey("weekly-referral-summary-total")
_KEY_LINE: Final[MessageKey] = MessageKey("weekly-referral-summary-line")
_KEY_FOOTER: Final[MessageKey] = MessageKey("weekly-referral-summary-footer")


class WeeklyClanReferralSummaryPresenter:
    """Локализованный рендер weekly-карточки рефералов клана."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def render(
        self,
        summary: WeeklyClanReferralSummary,
        *,
        locale: Locale,
        display_names: Iterable[DisplayName | None],
    ) -> str:
        """Сформировать полный текст карточки.

        `display_names` — итерируемое той же длины, что `summary.top`:
        вычисленные снаружи `DisplayName`-ы (для учёта актуальных
        диапазонов длины из `IBalanceConfig`). Если для какого-то
        реферера `DisplayName` собрать не удалось — `None`, и в строке
        используется только `username` / `first_name`.
        """
        title = self._bundle.format(
            _KEY_TITLE,
            locale=locale,
            clan_title=summary.clan.title.value,
        )
        total = self._bundle.format(
            _KEY_TOTAL,
            locale=locale,
            total=summary.total,
        )
        lines = []
        for rank, (entry, display_name) in enumerate(
            zip(summary.top, display_names, strict=True),
            start=1,
        ):
            lines.append(
                self._bundle.format(
                    _KEY_LINE,
                    locale=locale,
                    rank=rank,
                    referrer_display_name=self._format_referrer(
                        entry.player,
                        display_name=display_name,
                        locale=locale,
                    ),
                    count=entry.count,
                ),
            )
        footer = self._bundle.format(_KEY_FOOTER, locale=locale)
        return "\n".join((title, total, *lines, footer))

    def _format_referrer(
        self,
        player: Player,
        *,
        display_name: DisplayName | None,
        locale: Locale,
    ) -> str:
        """Собрать читабельное имя реферера для строки top-N.

        Приоритет: `[Локализованный титул] [DisplayName] @username`.
        Если `display_name` = None — фолбэк на `@username` или просто
        идентификатор. Локализованное имя титула берётся через
        `title_message_key(...)`, как в `ForestPresenter`.
        """
        parts: list[str] = []
        if player.title is not None:
            title_key = title_message_key(player.title)
            parts.append(self._bundle.format(title_key, locale=locale))
        if display_name is not None:
            parts.append(display_name.value)
        if player.username is not None:
            parts.append(f"@{player.username.value}")
        if not parts:
            return f"id{player.id}"
        return " ".join(parts)


__all__ = ["WeeklyClanReferralSummaryPresenter"]
