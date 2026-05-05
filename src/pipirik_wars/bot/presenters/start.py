"""Презентер ответов `/start` (Спринт 1.5.B).

Тонкий слой между handler-ом `/start` и `IMessageBundle`. Не делает
I/O, не зависит от инфраструктуры — только склеивает локализованные
строки по ключам.

Все ключи живут в `locales/{ru,en}.ftl` (Спринт 1.5.A: `start-*`).
Презентер не «прибивает» язык по месту: handler передаёт `Locale`
(пришедший из `LocaleMiddleware`), презентер форматирует через
порт `IMessageBundle`.

Контракт ключей (см. `locales/{ru,en}.ftl`):

- ``start-registered``  — успешная регистрация в ЛС.
- ``start-already``     — игрок уже зарегистрирован.
- ``start-group``       — `/start` пришёл в group/supergroup.
- ``start-other``       — прочие типы чатов (channel и т.п.).
- ``start-queued``      — DAU Gate: «серверы переполнены, позиция #N».
                         Параметр `position` (int) → плейсхолдер
                         `{ $position }` в .ftl.
"""

from __future__ import annotations

from typing import Final

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey

_KEY_REGISTERED: Final[MessageKey] = MessageKey("start-registered")
_KEY_ALREADY: Final[MessageKey] = MessageKey("start-already")
_KEY_GROUP: Final[MessageKey] = MessageKey("start-group")
_KEY_OTHER: Final[MessageKey] = MessageKey("start-other")
_KEY_QUEUED: Final[MessageKey] = MessageKey("start-queued")


class StartPresenter:
    """Локализованный рендер ответов `/start` через `IMessageBundle`.

    Использование (в handler-е):

        presenter = StartPresenter(bundle=bundle)
        await message.answer(presenter.registered(locale=locale))
        await message.answer(presenter.queued(locale=locale, position=42))
    """

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def registered(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_REGISTERED, locale=locale)

    def already(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_ALREADY, locale=locale)

    def group(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_GROUP, locale=locale)

    def other(self, *, locale: Locale) -> str:
        return self._bundle.format(_KEY_OTHER, locale=locale)

    def queued(self, *, locale: Locale, position: int) -> str:
        return self._bundle.format(_KEY_QUEUED, locale=locale, position=position)


__all__ = ["StartPresenter"]
