"""Презентер ответов `/lang` (Спринт 1.5.F).

Тонкий слой между handler-ом `/lang ru|en` и `IMessageBundle`. Делает
ровно одно: формирует локализованную строку по ключу. Никакого I/O.

Особенность 1.5.F: после переключения локали игрок ожидает увидеть
**подтверждение в новой локали** (например, `/lang en` → ответ на
английском, не на русском). Поэтому `confirmed(...)` принимает
именно ту `Locale`, которую пользователь только что выбрал — handler
читает её из `SetPlayerLocaleResult.locale_override` (или передаёт
`Locale("ru"|"en")` напрямую) и НЕ использует старую `Locale` из
middleware-а (которая в этот момент представляет ещё прошлый выбор).

Все ключи живут в `locales/{ru,en}.ftl` (раздел `lang-*`).
"""

from __future__ import annotations

from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

_KEY_GROUP: Final[MessageKey] = MessageKey("lang-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("lang-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("lang-not-registered")
_KEY_USAGE: Final[MessageKey] = MessageKey("lang-usage")
_KEY_UNSUPPORTED: Final[MessageKey] = MessageKey("lang-unsupported")
_KEY_SET_RU: Final[MessageKey] = MessageKey("lang-set-ru")
_KEY_SET_EN: Final[MessageKey] = MessageKey("lang-set-en")


class LangPresenter:
    """Локализованный рендер ответов `/lang` через `IMessageBundle`."""

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def group(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_OTHER, locale=locale)

    def not_registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_NOT_REGISTERED, locale=locale)

    def usage(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_USAGE, locale=locale)

    def unsupported(self, *, locale: Locale, code: str) -> str:
        return self._bundle.format(_KEY_UNSUPPORTED, locale=locale, code=code)

    def confirmed(self, *, locale: Locale) -> str:
        """Подтверждение выбора. Рендерится в **новой** локали."""
        if locale.code == "ru":
            return self._bundle.format(_KEY_SET_RU, locale=locale)
        return self._bundle.format(_KEY_SET_EN, locale=locale)


__all__ = ["LangPresenter"]
