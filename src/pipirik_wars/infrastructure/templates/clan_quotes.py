"""JSON-провайдер каталога цитат «Главы клана дня»
(`config/templates/clan_quotes_<locale>.json`, Спринт 2.3.D).

Формат файла:

```json
{
  "version": 1,
  "templates": [
    {
      "id": "clan_quote.ru.0001",
      "text": "Тебя короновали, {user}. Носи корону, не теряй.",
      "tags": ["statham"]
    },
    {
      "id": "clan_quote.ru.0042",
      "text": "{user} — глава дня. По понятиям, это надо отметить.",
      "tags": ["vk_pablik", "profanity"]
    }
  ]
}
```

- ``version`` — целое число (на будущее, для миграций формата).
- ``templates[].id`` — стабильный машинный идентификатор; не должен
  меняться между деплоями (audit-payload + аналитика).
- ``templates[].text`` — текст цитаты; может содержать ``{user}``.
- ``templates[].tags`` — список тегов из `ALLOWED_QUOTE_TAGS`
  (`statham` / `vk_pablik` / `auf` / `meme` / `profanity`).

Адаптер кэширует загруженный каталог per-локаль на время жизни
инстанса (т.е. на всё время работы бота). Hot-reload каталога без
перезапуска — задача отдельного спринта (см. `IBalanceReloader`-паттерн
1.5.G для backlog).

Если запрошенной локали нет — fallback на ``"ru"``. Если и `"ru"`-
каталог пуст или отсутствует — `ClanQuoteCatalogEmptyError`
(прод-инвариант: RU-каталог должен быть всегда, ≥ 100 цитат, ПД 2.3.4).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pipirik_wars.application.daily_head import IClanQuoteTemplateProvider
from pipirik_wars.domain.daily_head import (
    ClanQuoteCatalogEmptyError,
    ClanQuoteTemplate,
)
from pipirik_wars.shared.errors import ConfigError

_FALLBACK_LOCALE = "ru"


class JsonClanQuoteTemplateProvider(IClanQuoteTemplateProvider):
    """Lazy-кэширующий загрузчик каталога цитат из JSON-файлов.

    `templates_dir` — каталог, в котором лежат файлы вида
    ``clan_quotes_<locale>.json``. Файлы валидируются при первом
    обращении к локали и потом кэшируются (до перезапуска процесса).
    """

    __slots__ = ("_cache", "_templates_dir")

    def __init__(self, *, templates_dir: Path) -> None:
        self._templates_dir = templates_dir
        self._cache: dict[str, tuple[ClanQuoteTemplate, ...]] = {}

    def get_templates(self, *, locale: str) -> Sequence[ClanQuoteTemplate]:
        cached = self._cache.get(locale)
        if cached is not None:
            return cached

        templates = self._try_load(locale)
        if templates is None and locale != _FALLBACK_LOCALE:
            templates = self._try_load(_FALLBACK_LOCALE)
        if templates is None or len(templates) == 0:
            raise ClanQuoteCatalogEmptyError(locale=locale)

        self._cache[locale] = templates
        return templates

    def _try_load(self, locale: str) -> tuple[ClanQuoteTemplate, ...] | None:
        path = self._templates_dir / f"clan_quotes_{locale}.json"
        if not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise ConfigError(f"failed to read {path}: {e}") from e
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as e:
            raise ConfigError(f"invalid JSON in {path}: {e}") from e
        return _parse_payload(raw, source=path)


def _parse_payload(raw: object, *, source: Path) -> tuple[ClanQuoteTemplate, ...]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: root must be a JSON object, got {type(raw).__name__}")
    templates_raw = raw.get("templates")
    if not isinstance(templates_raw, list):
        raise ConfigError(f"{source}: 'templates' must be a list")
    seen_ids: set[str] = set()
    parsed: list[ClanQuoteTemplate] = []
    for idx, entry in enumerate(templates_raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"{source}: templates[{idx}] must be an object")
        tid = entry.get("id")
        text = entry.get("text")
        tags_raw = entry.get("tags")
        if not isinstance(tid, str) or not isinstance(text, str):
            raise ConfigError(f"{source}: templates[{idx}] must have string 'id' and 'text'")
        if not isinstance(tags_raw, list) or not all(isinstance(t, str) for t in tags_raw):
            raise ConfigError(f"{source}: templates[{idx}] must have 'tags' as a list of strings")
        if tid in seen_ids:
            raise ConfigError(f"{source}: duplicate template id={tid!r}")
        seen_ids.add(tid)
        try:
            parsed.append(ClanQuoteTemplate(id=tid, text=text, tags=tuple(tags_raw)))
        except ValueError as e:
            raise ConfigError(f"{source}: templates[{idx}] invalid: {e}") from e
    return tuple(parsed)


__all__ = ["JsonClanQuoteTemplateProvider"]
