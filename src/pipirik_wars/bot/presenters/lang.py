"""Презентер ответов `/lang` (Спринт 1.5.F, расширен в 4.1-K).

Тонкий слой между handler-ом `/lang <code>` и `IMessageBundle`. Делает
ровно одно: формирует локализованную строку по ключу. Никакого I/O.

Особенность 1.5.F: после переключения локали игрок ожидает увидеть
**подтверждение в новой локали** (например, `/lang en` → ответ на
английском, не на русском). Поэтому `confirmed(...)` принимает
именно ту `Locale`, которую пользователь только что выбрал — handler
читает её из `SetPlayerLocaleResult.locale_override` (или передаёт
`Locale("ru"|"en"|"pt"|"es"|"tr"|"id"|"fa"|"uk"|"ar")` напрямую) и НЕ
использует старую `Locale` из middleware-а (которая в этот момент
представляет ещё прошлый выбор).

Все ключи живут в `locales/{code}.ftl` (раздел `lang-*`). Спринт 4.1-K
расширил каталог поддерживаемых локалей с 2 (ru, en) до 8 (+pt, es,
tr, id, fa, uk); `confirmed()` диспетчеризуется через словарь
`_KEY_SET_BY_LOCALE`, чтобы добавление новых локалей не требовало
правки `if/elif`-цепочки.
"""

from __future__ import annotations

from typing import Final

from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    IMessageBundle,
    Locale,
    MessageKey,
)

_KEY_GROUP: Final[MessageKey] = MessageKey("lang-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("lang-other")
_KEY_NOT_REGISTERED: Final[MessageKey] = MessageKey("lang-not-registered")
_KEY_USAGE: Final[MessageKey] = MessageKey("lang-usage")
_KEY_UNSUPPORTED: Final[MessageKey] = MessageKey("lang-unsupported")
_KEY_SET_RU: Final[MessageKey] = MessageKey("lang-set-ru")
_KEY_SET_EN: Final[MessageKey] = MessageKey("lang-set-en")
_KEY_SET_PT: Final[MessageKey] = MessageKey("lang-set-pt")
_KEY_SET_ES: Final[MessageKey] = MessageKey("lang-set-es")
_KEY_SET_TR: Final[MessageKey] = MessageKey("lang-set-tr")
_KEY_SET_ID: Final[MessageKey] = MessageKey("lang-set-id")
_KEY_SET_FA: Final[MessageKey] = MessageKey("lang-set-fa")
_KEY_SET_UK: Final[MessageKey] = MessageKey("lang-set-uk")
_KEY_SET_AR: Final[MessageKey] = MessageKey("lang-set-ar")

# `lang-set-<code>` ключ для каждой поддерживаемой локали. Ключи отсутствующие
# в этом словаре фолбэкаются на `lang-set-en` (теоретически не должно
# случаться, т.к. `Locale.__post_init__` уже валидирует `code` против
# `SUPPORTED_LOCALES`).
_KEY_SET_BY_LOCALE: Final[dict[str, MessageKey]] = {
    "ru": _KEY_SET_RU,
    "en": _KEY_SET_EN,
    "pt": _KEY_SET_PT,
    "es": _KEY_SET_ES,
    "tr": _KEY_SET_TR,
    "id": _KEY_SET_ID,
    "fa": _KEY_SET_FA,
    "uk": _KEY_SET_UK,
    "ar": _KEY_SET_AR,
}


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
        key = _KEY_SET_BY_LOCALE.get(locale.code, _KEY_SET_BY_LOCALE[DEFAULT_LOCALE.code])
        return self._bundle.format(key, locale=locale)


__all__ = ["LangPresenter"]
