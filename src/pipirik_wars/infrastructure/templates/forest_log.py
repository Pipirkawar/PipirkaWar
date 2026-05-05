"""JSON-провайдер каталога забавных логов леса
(`config/templates/forest_logs_<locale>.json`).

Формат файла зеркальный к oracle-каталогу:

```json
{
  "version": 1,
  "templates": [
    {"id": "forest.ru.0001", "text": "{user} зацепился за корягу и нашёл {delta} в кустах!"},
    ...
  ]
}
```

- `version` — целое число (на будущее, для миграций формата).
- `templates[].id` — стабильный машинный идентификатор; не должен
  меняться между деплоями (audit / аналитика).
- `templates[].text` — текст лога; может содержать плейсхолдеры
  `{user}` (полный ник «Титул Название Имя») и `{delta}` (+N см).

Адаптер кэширует загруженный каталог per-локаль на время жизни
инстанса (т.е. на всё время работы бота). Перезагрузка каталога без
перезапуска — задача будущих спринтов (i18n + hot-reload).

Если запрошенной локали нет — fallback на `"ru"`. Если и `"ru"`-каталог
пуст или отсутствует — `ForestLogNoTemplatesError` (prod-инвариант:
RU-каталог должен быть всегда и содержать ≥ 300 шаблонов).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pipirik_wars.application.forest.log_templates import IForestLogTemplateProvider
from pipirik_wars.domain.forest import ForestLogNoTemplatesError, ForestLogTemplate
from pipirik_wars.shared.errors import ConfigError

_FALLBACK_LOCALE = "ru"


class JsonForestLogTemplateProvider(IForestLogTemplateProvider):
    """Lazy-кэширующий загрузчик каталога forest-логов из JSON-файлов.

    `templates_dir` — каталог, в котором лежат файлы вида
    `forest_logs_<locale>.json`. Файлы валидируются при первом обращении
    к локали и потом кэшируются (до перезапуска процесса).
    """

    __slots__ = ("_cache", "_templates_dir")

    def __init__(self, *, templates_dir: Path) -> None:
        self._templates_dir = templates_dir
        self._cache: dict[str, tuple[ForestLogTemplate, ...]] = {}

    def get_templates(self, *, locale: str) -> Sequence[ForestLogTemplate]:
        cached = self._cache.get(locale)
        if cached is not None:
            return cached

        templates = self._try_load(locale)
        if templates is None and locale != _FALLBACK_LOCALE:
            templates = self._try_load(_FALLBACK_LOCALE)
        if templates is None or len(templates) == 0:
            raise ForestLogNoTemplatesError()

        self._cache[locale] = templates
        return templates

    def _try_load(self, locale: str) -> tuple[ForestLogTemplate, ...] | None:
        path = self._templates_dir / f"forest_logs_{locale}.json"
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


def _parse_payload(raw: object, *, source: Path) -> tuple[ForestLogTemplate, ...]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: root must be a JSON object, got {type(raw).__name__}")
    templates_raw = raw.get("templates")
    if not isinstance(templates_raw, list):
        raise ConfigError(f"{source}: 'templates' must be a list")
    seen_ids: set[str] = set()
    parsed: list[ForestLogTemplate] = []
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
            parsed.append(ForestLogTemplate(id=tid, text=text))
        except ValueError as e:
            raise ConfigError(f"{source}: templates[{idx}] invalid: {e}") from e
    return tuple(parsed)


__all__ = ["JsonForestLogTemplateProvider"]
