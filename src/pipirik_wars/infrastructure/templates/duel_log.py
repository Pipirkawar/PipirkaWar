"""JSON-провайдер каталога забавных раунд-логов PvP
(`config/templates/duel_logs_<locale>.json`).

Формат файла зеркальный к `forest_logs_<locale>.json` и
`oracle_<locale>.json`, но с дополнительным полем `kind` для категории
исхода раунда (см. `RoundOutcomeKind` в `domain/pvp/log_template.py`):

```json
{
  "version": 1,
  "templates": [
    {"id": "pvp.ru.both_hit.0001", "kind": "both_hit",
     "text": "🥊 {p1} и {p2} оба пробили!"},
    ...
  ]
}
```

- `version` — целое число (на будущее, для миграций формата).
- `templates[].id` — стабильный машинный идентификатор; не должен
  меняться между деплоями (audit / аналитика).
- `templates[].kind` — одна из категорий `RoundOutcomeKind`
  (`"both_hit"` / `"single_hit"` / `"both_blocked"`).
- `templates[].text` — текст лога; может содержать только
  плейсхолдеры, разрешённые для соответствующей `kind`:
  - `BOTH_HIT` / `BOTH_BLOCKED` → `{p1}`, `{p2}`;
  - `SINGLE_HIT` → `{attacker}`, `{defender}`.
  Любые другие плейсхолдеры (и `{p1}` в `single_hit` и т. п.) —
  `ConfigError` при первой загрузке.

Адаптер кэширует загруженный каталог per-локаль на время жизни
инстанса. Перезагрузка без рестарта — задача будущих спринтов.

Если запрошенной локали нет — fallback на `"ru"`. Если и `"ru"`-каталог
пуст или отсутствует — `DuelLogNoTemplatesError` (prod-инвариант:
RU-каталог должен быть всегда и содержать ≥ 50 шаблонов).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

from pipirik_wars.application.pvp import IDuelLogTemplateProvider
from pipirik_wars.domain.pvp import (
    DuelLogNoTemplatesError,
    DuelLogTemplate,
    RoundOutcomeKind,
)
from pipirik_wars.shared.errors import ConfigError

_FALLBACK_LOCALE = "ru"

# Допустимые плейсхолдеры по категориям. Любой `{...}` в `text`,
# не входящий в этот набор, приведёт к `ConfigError` при загрузке.
_ALLOWED_PLACEHOLDERS: dict[RoundOutcomeKind, frozenset[str]] = {
    RoundOutcomeKind.BOTH_HIT: frozenset({"p1", "p2"}),
    RoundOutcomeKind.BOTH_BLOCKED: frozenset({"p1", "p2"}),
    RoundOutcomeKind.SINGLE_HIT: frozenset({"attacker", "defender"}),
}

_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


class JsonDuelLogTemplateProvider(IDuelLogTemplateProvider):
    """Lazy-кэширующий загрузчик каталога раунд-логов PvP из JSON-файлов.

    `templates_dir` — каталог, в котором лежат файлы вида
    `duel_logs_<locale>.json`. Файлы валидируются при первом обращении
    к локали и потом кэшируются (до перезапуска процесса).
    """

    __slots__ = ("_cache", "_templates_dir")

    def __init__(self, *, templates_dir: Path) -> None:
        self._templates_dir = templates_dir
        self._cache: dict[str, tuple[DuelLogTemplate, ...]] = {}

    def get_templates(self, *, locale: str) -> Sequence[DuelLogTemplate]:
        cached = self._cache.get(locale)
        if cached is not None:
            return cached

        templates = self._try_load(locale)
        if templates is None and locale != _FALLBACK_LOCALE:
            templates = self._try_load(_FALLBACK_LOCALE)
        if templates is None or len(templates) == 0:
            raise DuelLogNoTemplatesError()

        self._cache[locale] = templates
        return templates

    def _try_load(self, locale: str) -> tuple[DuelLogTemplate, ...] | None:
        path = self._templates_dir / f"duel_logs_{locale}.json"
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


def _parse_payload(raw: object, *, source: Path) -> tuple[DuelLogTemplate, ...]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: root must be a JSON object, got {type(raw).__name__}")
    templates_raw = raw.get("templates")
    if not isinstance(templates_raw, list):
        raise ConfigError(f"{source}: 'templates' must be a list")
    seen_ids: set[str] = set()
    parsed: list[DuelLogTemplate] = []
    for idx, entry in enumerate(templates_raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"{source}: templates[{idx}] must be an object")
        tid = entry.get("id")
        text = entry.get("text")
        kind_raw = entry.get("kind")
        if not isinstance(tid, str) or not isinstance(text, str):
            raise ConfigError(f"{source}: templates[{idx}] must have string 'id' and 'text'")
        if not isinstance(kind_raw, str):
            raise ConfigError(f"{source}: templates[{idx}] must have string 'kind'")
        try:
            kind = RoundOutcomeKind(kind_raw)
        except ValueError as e:
            raise ConfigError(f"{source}: templates[{idx}] invalid kind={kind_raw!r}: {e}") from e
        if tid in seen_ids:
            raise ConfigError(f"{source}: duplicate template id={tid!r}")
        seen_ids.add(tid)
        _validate_placeholders(text, kind=kind, source=source, idx=idx)
        try:
            parsed.append(DuelLogTemplate(id=tid, text=text, kind=kind))
        except ValueError as e:
            raise ConfigError(f"{source}: templates[{idx}] invalid: {e}") from e
    return tuple(parsed)


def _validate_placeholders(text: str, *, kind: RoundOutcomeKind, source: Path, idx: int) -> None:
    allowed = _ALLOWED_PLACEHOLDERS[kind]
    found = set(_PLACEHOLDER_RE.findall(text))
    extra = found - allowed
    if extra:
        raise ConfigError(
            f"{source}: templates[{idx}] (kind={kind.value}) "
            f"has disallowed placeholders {sorted(extra)}; "
            f"allowed: {sorted(allowed)}",
        )


__all__ = ["JsonDuelLogTemplateProvider"]
