"""JSON-провайдер каталога предсказаний (`config/templates/oracle_<locale>.json`).

Формат файла:

```json
{
  "version": 1,
  "templates": [
    {"id": "oracle.ru.0001", "text": "Сегодня тебе повезёт, {user}!"},
    ...
  ]
}
```

- `version` — целое число (на будущее, для миграций формата).
- `templates[].id` — стабильный машинный идентификатор; не должен
  меняться между деплоями (audit / аналитика).
- `templates[].text` — текст предсказания; может содержать `{user}`.

Адаптер кэширует загруженный каталог per-локаль на время жизни
инстанса (т.е. на всё время работы бота). Перезагрузка каталога без
перезапуска — задача Спринта 1.5 (i18n + hot-reload).

Если запрошенной локали нет — fallback на `"ru"`. Если и `"ru"`-каталог
пуст или отсутствует — `OracleNoTemplatesError` (прод-инвариант:
RU-каталог должен быть всегда).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pipirik_wars.application.oracle.templates import IOracleTemplateProvider
from pipirik_wars.domain.oracle import OracleNoTemplatesError, OracleTemplate
from pipirik_wars.shared.errors import ConfigError

_FALLBACK_LOCALE = "ru"


class JsonOracleTemplateProvider(IOracleTemplateProvider):
    """Lazy-кэширующий загрузчик каталога предсказаний из JSON-файлов.

    `templates_dir` — каталог, в котором лежат файлы вида
    `oracle_<locale>.json`. Файлы валидируются при первом обращении к
    локали и потом кэшируются (до перезапуска процесса).
    """

    __slots__ = ("_cache", "_templates_dir")

    def __init__(self, *, templates_dir: Path) -> None:
        self._templates_dir = templates_dir
        self._cache: dict[str, tuple[OracleTemplate, ...]] = {}

    def get_templates(self, *, locale: str) -> Sequence[OracleTemplate]:
        cached = self._cache.get(locale)
        if cached is not None:
            return cached

        templates = self._try_load(locale)
        if templates is None and locale != _FALLBACK_LOCALE:
            templates = self._try_load(_FALLBACK_LOCALE)
        if templates is None or len(templates) == 0:
            raise OracleNoTemplatesError(locale=locale)

        self._cache[locale] = templates
        return templates

    def _try_load(self, locale: str) -> tuple[OracleTemplate, ...] | None:
        path = self._templates_dir / f"oracle_{locale}.json"
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


def _parse_payload(raw: object, *, source: Path) -> tuple[OracleTemplate, ...]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: root must be a JSON object, got {type(raw).__name__}")
    templates_raw = raw.get("templates")
    if not isinstance(templates_raw, list):
        raise ConfigError(f"{source}: 'templates' must be a list")
    seen_ids: set[str] = set()
    parsed: list[OracleTemplate] = []
    for idx, entry in enumerate(templates_raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"{source}: templates[{idx}] must be an object")
        tid = entry.get("id")
        text = entry.get("text")
        if not isinstance(tid, str) or not isinstance(text, str):
            raise ConfigError(f"{source}: templates[{idx}] must have string 'id' and 'text'")
        if tid in seen_ids:
            raise ConfigError(f"{source}: duplicate template id={tid!r}")
        seen_ids.add(tid)
        try:
            parsed.append(OracleTemplate(id=tid, text=text))
        except ValueError as e:
            raise ConfigError(f"{source}: templates[{idx}] invalid: {e}") from e
    return tuple(parsed)


__all__ = ["JsonOracleTemplateProvider"]
