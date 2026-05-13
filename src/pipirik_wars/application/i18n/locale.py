"""`Locale` — иммутабельный value object «язык игрока» (ПД 1.5.2).

Каталог локалей расширен в Спринте 4.1-K (PR 4.1-K, задача 4.1.14):
- MVP-набор: `ru`, `en` (Спринт 1.5.A).
- 4.1-K: добавлены `pt`, `es`, `tr`, `id`, `fa`, `uk` — для каждого из
  6 новых языков создан собственный `locales/{code}.ftl`-файл с
  30-50 ключевыми переводами (`start-*`/`profile-*`/`lang-*`);
  остальные ~1550 ключей рендерятся через fallback на EN внутри
  `FluentMessageBundle`. Это backward-compat-расширение: никаких
  изменений для пользователей `ru`/`en`.

`LocaleResolver` — чистая функция-стратегия, переводящая Telegram
`language_code` (BCP-47, e.g. `"ru"`, `"ru-RU"`, `"en-US"`, `"en-GB"`,
`"pt-BR"`, `"es-MX"`, `"fa-IR"`, `"uk-UA"`) в одну из поддерживаемых
нами локалей. Стратегия (см. ПД 1.5.2):

1. `language_code` начинается на короткий BCP-47-префикс одной из
   поддерживаемых локалей (case-insensitive) → соответствующая `Locale`.
2. иначе (включая `None`, пустую строку, любой другой язык) → `DEFAULT_LOCALE`,
   которая равна `Locale("en")` (English fallback из ПД 1.5.2).

Реализация перебирает `SUPPORTED_LOCALES` в **отсортированном** порядке
по длине-убыванию tie-breaker-а по алфавиту — на момент K.1 все
поддерживаемые коды двухбуквенные, коллизий префиксов нет.

Решение «русскоговорящие пользователи иногда регистрируются с английской
телегой» — НЕ делаем эвристик в `LocaleResolver`-е (это не его слой);
если игроку нужно переключить язык, он делает это командой `/lang <code>`
(Спринт 1.5.F расширен в 4.1-K на 8 поддерживаемых кодов).
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


SUPPORTED_LOCALES: Final[frozenset[str]] = frozenset(
    {
        # MVP (Спринт 1.5.A)
        "ru",
        "en",
        # Расширение каталога — Спринт 4.1-K (задача 4.1.14)
        "pt",  # Portuguese (`pt`, `pt-BR`, `pt-PT`)
        "es",  # Spanish (`es`, `es-ES`, `es-MX`)
        "tr",  # Turkish (`tr`)
        "id",  # Indonesian (`id`)
        "fa",  # Persian / Farsi (`fa`, `fa-IR`) — RTL
        "uk",  # Ukrainian (`uk`, `uk-UA`)
        "ar",  # Arabic (`ar`) — RTL — Спринт 4.5 (локализация)
    },
)
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
