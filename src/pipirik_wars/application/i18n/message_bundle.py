"""`IMessageBundle` — порт «как получить локализованную строку» (ПД 1.5.1).

Application-слой определяет только контракт. Реализация
(`FluentMessageBundle`, поверх Mozilla Fluent) живёт в
`infrastructure/i18n/`.

Контракт минимальный:

- `format(key, locale, **params) -> str` — вернуть локализованное
  сообщение. Если ключа нет в `locale`, реализация **обязана** упасть
  на дефолтную локаль (`Locale("en")`). Если и там нет — `MessageKeyError`.
- Параметры подстановки — позиционные, передаются как `kwargs`. Это
  совместимо с Fluent-плейсхолдерами `{ $name }`. Если параметр не
  использован в шаблоне — это ОК (Fluent игнорирует лишние).

`MessageKey` — `NewType` поверх `str`, чтобы handler-ы не путали
ключи с произвольными строками. Все валидные ключи живут как
константы рядом с использующими их презентерами.
"""

from __future__ import annotations

from typing import NewType, Protocol

from pipirik_wars.application.i18n.locale import Locale

MessageKey = NewType("MessageKey", str)


class IMessageBundle(Protocol):
    """Порт «локализованная строка по ключу».

    Реализация: `infrastructure.i18n.FluentMessageBundle` (поверх .ftl-файлов).
    Тестовые fakes: `tests.fakes.fake_message_bundle.FakeMessageBundle`.
    """

    def format(
        self,
        key: MessageKey,
        *,
        locale: Locale,
        **params: object,
    ) -> str:
        """Отрендерить сообщение `key` под локаль `locale` с подстановкой
        `params`.

        Контракт:
        - если ключа нет в `locale`, ищем в `Locale("en")` (fallback).
        - если ключа нет нигде — `MessageKeyError(key)`.
        - подстановки безопасны: если в шаблоне есть `{ $foo }`, а в
          `params` нет `foo`, реализация может или вернуть строку с
          плейсхолдером, или райзить `MessageRenderError` (это опция
          реализации; FluentMessageBundle оставляет «{ $foo }» как есть
          и логирует).
        """


__all__ = [
    "IMessageBundle",
    "MessageKey",
]
