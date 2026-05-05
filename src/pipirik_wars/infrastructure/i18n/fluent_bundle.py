"""`FluentMessageBundle` — реализация `IMessageBundle` поверх Mozilla Fluent.

Спринт 1.5.A / ПД 1.5.1.

На каждый поддерживаемый `Locale` создаём отдельный `FluentBundle`
и подгружаем `locales/{locale.code}.ftl`. Bundle лениво кэшируется
(eager-loading сделать тоже можно, но для тестов и `bot/main.py`
ленивая инициализация удобнее: «отсутствующий .ftl-файл — это
ошибка только при первом обращении, а не при импорте модуля»).

Стратегия fallback (`format`):

1. Берём bundle для запрошенной `locale`. Если ключ есть — рендерим.
2. Если ключа нет — берём bundle для `Locale("en")`. Если есть — рендерим.
3. Если и в `en` нет — `MessageKeyError(key)`.

Параметры подстановки передаются как обычные `kwargs`. Реализация
проксирует их в `format_pattern(args=...)`. Если в шаблоне есть
плейсхолдер `{ $foo }`, а в `params` нет `foo` — Fluent вернёт строку
с именем переменной, обёрнутым в BiDi-isolation marks (Unicode FSI/PDI),
и список `errors`. Мы логируем это (`logger.warning`), но возвращаем
строку как есть — это «soft fail»: один сломанный плейсхолдер не
должен ронять весь ответ бота.

Спринт 1.5.B+ выправит handler-ы / презентеры и вытащит из них все
текстовые литералы → ключи в .ftl.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Final

from fluent.runtime import FluentBundle, FluentResource

from pipirik_wars.application.i18n import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    IMessageBundle,
    Locale,
    MessageKey,
    MessageKeyError,
)

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


class FluentMessageBundle(IMessageBundle):
    """Bundle поверх локального каталога с `*.ftl`-файлами.

    `locales_dir` — путь до папки. Внутри ожидается по одному файлу
    на локаль (`ru.ftl`, `en.ftl`).

    Безопасно использовать из нескольких корутин: внутри `format`
    держим `_lock` только на время первой загрузки конкретной
    локали; после загрузки чтение из dict-а — атомарно.
    """

    def __init__(self, *, locales_dir: Path) -> None:
        self._locales_dir = locales_dir
        self._bundles: dict[str, FluentBundle] = {}
        self._lock = threading.Lock()

    # -------- public API ----------------------------------------------------

    def format(
        self,
        key: MessageKey,
        *,
        locale: Locale,
        **params: object,
    ) -> str:
        # Сначала пробуем запрошенную локаль; если ключа нет — fallback на en.
        if locale != DEFAULT_LOCALE:
            text = self._try_format(locale=locale, key=key, params=params)
            if text is not None:
                return text
        text = self._try_format(locale=DEFAULT_LOCALE, key=key, params=params)
        if text is not None:
            return text
        raise MessageKeyError(key)

    # -------- internals -----------------------------------------------------

    def _try_format(
        self,
        *,
        locale: Locale,
        key: MessageKey,
        params: dict[str, object],
    ) -> str | None:
        bundle = self._get_bundle(locale)
        try:
            message = bundle.get_message(key)
        except (KeyError, LookupError):
            return None
        if message.value is None:
            return None
        text, errors = bundle.format_pattern(message.value, params or None)
        for err in errors:
            _LOGGER.warning(
                "fluent format error: locale=%s key=%s err=%s",
                locale.code,
                key,
                err,
            )
        # `format_pattern` теоретически может вернуть `FluentNone` (sentinel
        # для unresolved value); в нашем сценарии (топ-левел Pattern) это не
        # должно случаться, но ради type-safety явно стрингуем и логируем.
        if not isinstance(text, str):
            _LOGGER.warning(
                "fluent format returned non-str (%s) for key=%s locale=%s",
                type(text).__name__,
                key,
                locale.code,
            )
            return str(text)
        return text

    def _get_bundle(self, locale: Locale) -> FluentBundle:
        cached = self._bundles.get(locale.code)
        if cached is not None:
            return cached
        with self._lock:
            cached = self._bundles.get(locale.code)
            if cached is not None:
                return cached
            bundle = self._load_bundle(locale)
            self._bundles[locale.code] = bundle
            return bundle

    def _load_bundle(self, locale: Locale) -> FluentBundle:
        if locale.code not in SUPPORTED_LOCALES:
            raise ValueError(f"unsupported locale {locale.code!r}")
        path = self._locales_dir / f"{locale.code}.ftl"
        if not path.is_file():
            raise FileNotFoundError(f"locale file not found: {path}")
        bundle = FluentBundle([locale.code])
        bundle.add_resource(FluentResource(path.read_text(encoding="utf-8")))
        return bundle


__all__ = ["FluentMessageBundle"]
