"""`Locale` — иммутабельный value object «язык игрока» (ПД 1.5.2).

Поддерживаем только `ru` и `en` на MVP (ПД §3 «Работает RU + EN»).
Остальные локали из ГДД (PT/ES/TR/ID/FA/UK) появятся в Спринте 4.1.7.

`LocaleResolver` — чистая функция-стратегия, переводящая Telegram
`language_code` (BCP-47, e.g. `"ru"`, `"ru-RU"`, `"en-US"`, `"en-GB"`)
в одну из поддерживаемых нами локалей. Стратегия (см. ПД 1.5.2):

1. `language_code` начинается на `"ru"` (case-insensitive) → `Locale("ru")`
2. `language_code` начинается на `"en"` (case-insensitive) → `Locale("en")`
3. иначе (включая `None`, пустую строку, любой другой язык) → `DEFAULT_LOCALE`,
   которая равна `Locale("en")` (English fallback из ПД 1.5.2).

Решение «русскоговорящие пользователи иногда регистрируются с английской
телегой» — НЕ делаем эвристик в `LocaleResolver`-е (это не его слой);
если игроку нужно переключить язык, он делает это командой `/lang ru` или
`/lang en` (Спринт 1.5.B+, отдельный handler).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Locale:
    """Доменный value-object «язык интерфейса».

    Хранится как BCP-47 short tag (`"ru"`, `"en"`). На MVP — только эти два.
    Конструктор валидирует тег, чтобы handler-ы / презентеры не получали
    «гнилые» значения и `IMessageBundle` всегда мог отрезолвить bundle.
    """

    code: str

    def __post_init__(self) -> None:
        if self.code not in SUPPORTED_LOCALES:
            raise ValueError(
                f"unsupported locale {self.code!r}; supported: {sorted(SUPPORTED_LOCALES)!r}",
            )


SUPPORTED_LOCALES: Final[frozenset[str]] = frozenset({"ru", "en"})
DEFAULT_LOCALE: Final[Locale] = Locale("en")


@dataclass(frozen=True, slots=True)
class LocaleResolver:
    """Чистая стратегия «Telegram language_code → Locale».

    Stateless, без I/O — поэтому находится в application-слое, а не в
    infrastructure. Использование (через DI):

        locale = resolver.resolve(tg_lang="ru-RU")  # → Locale("ru")
        locale = resolver.resolve(tg_lang="fr")     # → DEFAULT_LOCALE = Locale("en")
        locale = resolver.resolve(tg_lang=None)     # → DEFAULT_LOCALE
    """

    default: Locale = DEFAULT_LOCALE

    def resolve(self, *, tg_lang: str | None) -> Locale:
        if tg_lang is None or not tg_lang.strip():
            return self.default
        normalized = tg_lang.strip().lower()
        for supported in sorted(SUPPORTED_LOCALES):
            if normalized.startswith(supported):
                return Locale(supported)
        return self.default


__all__ = [
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "Locale",
    "LocaleResolver",
]
