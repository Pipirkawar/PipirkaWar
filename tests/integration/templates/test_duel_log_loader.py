"""Integration-тесты `JsonDuelLogTemplateProvider` и реальных файлов
`config/templates/duel_logs_<locale>.json` (Спринт 2.1.H, ПД 2.1.5).

Зеркало `test_forest_log_loader.py`. Покрывает:

- прод-каталоги ≥ 50 шаблонов RU+EN с ≥ 1 шаблоном на каждую категорию,
- уникальность `id` внутри файла,
- `text` непуст и без лидирующих/трейлинговых пробелов,
- допустимые плейсхолдеры по категориям (`{p1}`, `{p2}` для `BOTH_*`;
  `{attacker}`, `{defender}` для `SINGLE_HIT`),
- lazy-кэш per-locale,
- fallback на `"ru"`,
- ошибки загрузки (пустой каталог, дубликаты id, битый JSON, невалидный
  kind, дисалоw-ed-плейсхолдер) — `DuelLogNoTemplatesError` / `ConfigError`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipirik_wars.domain.pvp import (
    DuelLogNoTemplatesError,
    DuelLogTemplate,
    RoundOutcomeKind,
)
from pipirik_wars.infrastructure.templates import JsonDuelLogTemplateProvider
from pipirik_wars.shared.errors import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = REPO_ROOT / "config" / "templates"

_PLACEHOLDER_RE = re.compile(r"\{[^}]+\}")
_ALLOWED_BY_KIND: dict[RoundOutcomeKind, frozenset[str]] = {
    RoundOutcomeKind.BOTH_HIT: frozenset({"{p1}", "{p2}"}),
    RoundOutcomeKind.BOTH_BLOCKED: frozenset({"{p1}", "{p2}"}),
    RoundOutcomeKind.SINGLE_HIT: frozenset({"{attacker}", "{defender}"}),
}


class TestJsonDuelLogTemplateProviderShippedFiles:
    """Прод-каталоги: ≥ 50 шаблонов RU и EN."""

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_at_least_50_templates(self, locale: str) -> None:
        provider = JsonDuelLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        assert len(templates) >= 50

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_at_least_one_per_kind(self, locale: str) -> None:
        provider = JsonDuelLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        kinds = {t.kind for t in templates}
        assert kinds == {
            RoundOutcomeKind.BOTH_HIT,
            RoundOutcomeKind.SINGLE_HIT,
            RoundOutcomeKind.BOTH_BLOCKED,
        }

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_ids_are_unique(self, locale: str) -> None:
        provider = JsonDuelLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        ids = [t.id for t in templates]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_texts_are_nonempty_and_trimmed(self, locale: str) -> None:
        provider = JsonDuelLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        for tpl in templates:
            assert tpl.text != ""
            assert tpl.text == tpl.text.strip()

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_only_allowed_placeholders_per_kind(self, locale: str) -> None:
        provider = JsonDuelLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        for tpl in templates:
            allowed = _ALLOWED_BY_KIND[tpl.kind]
            found = set(_PLACEHOLDER_RE.findall(tpl.text))
            illegal = found - allowed
            assert not illegal, (
                f"template {tpl.id} (kind={tpl.kind}) has illegal placeholders {illegal}"
            )

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_placeholders_render_without_error(self, locale: str) -> None:
        provider = JsonDuelLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        for tpl in templates:
            tpl.text.format(p1="Alice", p2="Bob", attacker="Alice", defender="Bob")

    def test_caches_per_locale(self) -> None:
        provider = JsonDuelLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        first = provider.get_templates(locale="ru")
        second = provider.get_templates(locale="ru")
        assert first is second

    def test_falls_back_to_ru_when_locale_missing(self) -> None:
        provider = JsonDuelLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        ru = provider.get_templates(locale="ru")
        unknown = provider.get_templates(locale="zz")
        assert tuple(unknown) == tuple(ru)


class TestJsonDuelLogTemplateProviderLoadingErrors:
    def _write(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_falls_back_to_ru_when_locale_file_missing(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "duel_logs_ru.json",
            {
                "version": 1,
                "templates": [{"id": "x", "kind": "both_hit", "text": "{p1} vs {p2}"}],
            },
        )
        provider = JsonDuelLogTemplateProvider(templates_dir=tmp_path)
        out = provider.get_templates(locale="es")
        assert len(out) == 1
        assert out[0].id == "x"

    def test_raises_when_no_files_exist(self, tmp_path: Path) -> None:
        provider = JsonDuelLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(DuelLogNoTemplatesError):
            provider.get_templates(locale="ru")

    def test_raises_on_empty_file(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "duel_logs_ru.json",
            {"version": 1, "templates": []},
        )
        provider = JsonDuelLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(DuelLogNoTemplatesError):
            provider.get_templates(locale="ru")

    def test_raises_on_duplicate_ids(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "duel_logs_ru.json",
            {
                "version": 1,
                "templates": [
                    {"id": "x", "kind": "both_hit", "text": "1"},
                    {"id": "x", "kind": "both_hit", "text": "2"},
                ],
            },
        )
        provider = JsonDuelLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "duel_logs_ru.json"
        path.write_text("{ not valid json", encoding="utf-8")
        provider = JsonDuelLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_on_root_not_object(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "duel_logs_ru.json",
            [{"id": "x", "kind": "both_hit", "text": "y"}],
        )
        provider = JsonDuelLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_when_templates_not_list(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "duel_logs_ru.json",
            {"version": 1, "templates": "oops"},
        )
        provider = JsonDuelLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_when_entry_not_object(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "duel_logs_ru.json",
            {"version": 1, "templates": ["oops"]},
        )
        provider = JsonDuelLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_on_invalid_kind(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "duel_logs_ru.json",
            {
                "version": 1,
                "templates": [
                    {"id": "x", "kind": "bogus", "text": "y"},
                ],
            },
        )
        provider = JsonDuelLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError, match="invalid kind"):
            provider.get_templates(locale="ru")

    def test_raises_on_disallowed_placeholder(self, tmp_path: Path) -> None:
        # `{attacker}` НЕ разрешён в `both_hit`.
        self._write(
            tmp_path / "duel_logs_ru.json",
            {
                "version": 1,
                "templates": [
                    {
                        "id": "x",
                        "kind": "both_hit",
                        "text": "{attacker} hit {p2}",
                    },
                ],
            },
        )
        provider = JsonDuelLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError, match="disallowed placeholders"):
            provider.get_templates(locale="ru")

    def test_loads_valid_payload(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "duel_logs_en.json",
            {
                "version": 1,
                "templates": [
                    {
                        "id": "pvp.en.both_hit.0001",
                        "kind": "both_hit",
                        "text": "{p1} hit {p2}",
                    },
                    {
                        "id": "pvp.en.single_hit.0001",
                        "kind": "single_hit",
                        "text": "{attacker} broke through {defender}",
                    },
                ],
            },
        )
        provider = JsonDuelLogTemplateProvider(templates_dir=tmp_path)
        templates = provider.get_templates(locale="en")
        assert tuple(templates) == (
            DuelLogTemplate(
                id="pvp.en.both_hit.0001",
                kind=RoundOutcomeKind.BOTH_HIT,
                text="{p1} hit {p2}",
            ),
            DuelLogTemplate(
                id="pvp.en.single_hit.0001",
                kind=RoundOutcomeKind.SINGLE_HIT,
                text="{attacker} broke through {defender}",
            ),
        )
