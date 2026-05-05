"""Локализация (i18n) — application-слой (Спринт 1.5.A / ПД 1.5.1, 1.5.2).

Здесь живут чистые value-object-ы и порты, описывающие «что значит
локализация» в наших терминах. **Без** реализации (Fluent / .ftl /
файловая система) — это инфраструктура (`infrastructure/i18n/`).

ПД 1.5.1: «Подключение fluent/i18n, файлы `locales/ru.ftl`,
`locales/en.ftl`. Все сообщения вытащены из кода».
ПД 1.5.2: «Определение языка по `language_code`, fallback EN».

Граф зависимостей (см. `.importlinter`):

```
bot ──▶ application.i18n  (порт IMessageBundle)
        ▲
        │ реализует
        │
infrastructure.i18n.FluentMessageBundle
```

`application.i18n` импортирует только `domain.shared` и stdlib.
"""

from pipirik_wars.application.i18n.errors import I18nError, MessageKeyError
from pipirik_wars.application.i18n.locale import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    Locale,
    LocaleResolver,
)
from pipirik_wars.application.i18n.message_bundle import IMessageBundle, MessageKey
from pipirik_wars.application.i18n.player_locale import IPlayerLocaleResolver

__all__ = [
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "I18nError",
    "IMessageBundle",
    "IPlayerLocaleResolver",
    "Locale",
    "LocaleResolver",
    "MessageKey",
    "MessageKeyError",
]
