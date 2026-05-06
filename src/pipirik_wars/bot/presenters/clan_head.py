"""Презентер для команды `/clan_head` (Спринт 2.3.E / ПД 2.3.4-5).

`ClanHeadPresenter` локализует все ответы handler-а `/clan_head` через
`IMessageBundle`. Берёт `Locale` из middleware-а и обработанный
результат use-case-а `RequestDailyHead` (через DTO `DailyHeadResolved`)
+ выбранную случайно цитату из каталога 2.3.D.

Шаблоны лежат в `.ftl` под ключами `clan-head-{...}` (RU + EN, см.
locales/ru.ftl / locales/en.ftl).
"""

from __future__ import annotations

from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

_KEY_NEEDS_GROUP: Final[MessageKey] = MessageKey("clan-head-needs-group-chat")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("clan-head-not-registered")
_KEY_FROZEN: Final[MessageKey] = MessageKey("clan-head-frozen-clan")
_KEY_NOT_ENOUGH_ACTIVE: Final[MessageKey] = MessageKey("clan-head-not-enough-active")
_KEY_SUCCESS: Final[MessageKey] = MessageKey("clan-head-success")
_KEY_ALREADY_ASSIGNED: Final[MessageKey] = MessageKey("clan-head-already-assigned")


class ClanHeadPresenter:
    """Локализованный рендер `/clan_head` через `IMessageBundle`."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def needs_group_chat(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NEEDS_GROUP, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    def frozen_clan(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_FROZEN, locale=locale)

    def not_enough_active(
        self,
        *,
        locale: Locale,
        active_count: int,
        required: int,
    ) -> str:
        return self._bundle.format(
            _KEY_NOT_ENOUGH_ACTIVE,
            locale=locale,
            active_count=active_count,
            required=required,
        )

    def success(
        self,
        *,
        locale: Locale,
        head_display_name: str,
        bonus_cm: int,
        new_length_cm: int,
        quote_text: str,
    ) -> str:
        """«🎉 Глава клана дня — {name}, +N см. <quote>»."""
        return self._bundle.format(
            _KEY_SUCCESS,
            locale=locale,
            head_display_name=head_display_name,
            bonus_cm=bonus_cm,
            new_length_cm=new_length_cm,
            quote_text=quote_text,
        )

    def already_assigned(
        self,
        *,
        locale: Locale,
        head_display_name: str,
        bonus_cm: int,
        quote_text: str,
    ) -> str:
        """«👀 На сегодня уже назначен глава — {name}, +N см. <quote>»."""
        return self._bundle.format(
            _KEY_ALREADY_ASSIGNED,
            locale=locale,
            head_display_name=head_display_name,
            bonus_cm=bonus_cm,
            quote_text=quote_text,
        )


__all__ = ["ClanHeadPresenter"]
