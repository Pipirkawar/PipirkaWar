"""Integration-тесты `JsonForestLogTemplateProvider` и реальных файлов
`config/templates/forest_logs_<locale>.json` (Спринт 1.5.G, ПД 1.5.3).

Зеркало `tests/integration/templates/test_oracle_loader.py`. Покрывает:

- прод-каталоги ≥ 300 шаблонов RU+EN,
- уникальность `id` внутри файла,
- `text` непуст и без лидирующих/трейлинговых пробелов,
- допустимые плейсхолдеры — только `{user}` и `{delta}`,
- lazy-кэш per-locale (повторный вызов отдаёт тот же tuple-инстанс),
- fallback на `"ru"`, если файла под запрошенную локаль нет,
- ошибки загрузки (пустой каталог, дубликаты id, битый JSON, корень не
  объект) — `ForestLogNoTemplatesError` / `ConfigError`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipirik_wars.domain.forest import ForestLogNoTemplatesError, ForestLogTemplate
from pipirik_wars.infrastructure.templates import JsonForestLogTemplateProvider
from pipirik_wars.shared.errors import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = REPO_ROOT / "config" / "templates"

_ALLOWED_PLACEHOLDERS = frozenset({"{user}", "{delta}"})
_PLACEHOLDER_RE = re.compile(r"\{[^}]+\}")


class TestJsonForestLogTemplateProviderShippedFiles:
    """Прод-каталоги: ≥ 300 шаблонов RU и EN, валидный JSON, валидные плейсхолдеры."""

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_at_least_300_templates(self, locale: str) -> None:
        provider = JsonForestLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        assert len(templates) >= 300

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_ids_are_unique(self, locale: str) -> None:
        provider = JsonForestLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        ids = [t.id for t in templates]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_texts_are_nonempty_and_trimmed(self, locale: str) -> None:
        provider = JsonForestLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        for tpl in templates:
            assert tpl.text != ""
            assert tpl.text == tpl.text.strip()

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_only_allowed_placeholders(self, locale: str) -> None:
        provider = JsonForestLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        for tpl in templates:
            found = set(_PLACEHOLDER_RE.findall(tpl.text))
            illegal = found - _ALLOWED_PLACEHOLDERS
            assert not illegal, f"template {tpl.id} has illegal placeholders {illegal}"

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_placeholders_render_without_error(self, locale: str) -> None:
        """`str.format` должен пройти без исключения при подстановке `user`/`delta`."""
        provider = JsonForestLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        for tpl in templates:
            tpl.text.format(user="Alice", delta="+3 см")

    def test_caches_per_locale(self) -> None:
        provider = JsonForestLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        first = provider.get_templates(locale="ru")
        second = provider.get_templates(locale="ru")
        assert first is second

    def test_falls_back_to_ru_when_locale_missing(self) -> None:
        provider = JsonForestLogTemplateProvider(templates_dir=TEMPLATES_DIR)
        ru = provider.get_templates(locale="ru")
        unknown = provider.get_templates(locale="zz")
        # Фолбэк должен отдать тот же набор, что и RU.
        assert tuple(unknown) == tuple(ru)


class TestJsonForestLogTemplateProviderLoadingErrors:
    def _write(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_falls_back_to_ru_when_locale_file_missing(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "forest_logs_ru.json",
            {
                "version": 1,
                "templates": [{"id": "x", "text": "y {user}"}],
            },
        )
        provider = JsonForestLogTemplateProvider(templates_dir=tmp_path)
        out = provider.get_templates(locale="es")
        assert len(out) == 1
        assert out[0].id == "x"

    def test_raises_when_no_files_exist(self, tmp_path: Path) -> None:
        provider = JsonForestLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ForestLogNoTemplatesError):
            provider.get_templates(locale="ru")

    def test_raises_on_empty_file(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "forest_logs_ru.json",
            {"version": 1, "templates": []},
        )
        provider = JsonForestLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ForestLogNoTemplatesError):
            provider.get_templates(locale="ru")

    def test_raises_on_duplicate_ids(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "forest_logs_ru.json",
            {
                "version": 1,
                "templates": [
                    {"id": "x", "text": "1"},
                    {"id": "x", "text": "2"},
                ],
            },
        )
        provider = JsonForestLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "forest_logs_ru.json"
        path.write_text("{ not valid json", encoding="utf-8")
        provider = JsonForestLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_on_root_not_object(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "forest_logs_ru.json",
            [{"id": "x", "text": "y"}],
        )
        provider = JsonForestLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_when_templates_not_list(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "forest_logs_ru.json",
            {"version": 1, "templates": "oops"},
        )
        provider = JsonForestLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_when_entry_missing_text(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "forest_logs_ru.json",
            {"version": 1, "templates": [{"id": "x"}]},
        )
        provider = JsonForestLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_when_entry_not_object(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "forest_logs_ru.json",
            {"version": 1, "templates": ["oops"]},
        )
        provider = JsonForestLogTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_loads_valid_payload(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "forest_logs_en.json",
            {
                "version": 1,
                "templates": [
                    {"id": "forest.en.0001", "text": "Hi {user} +{delta}"},
                    {"id": "forest.en.0002", "text": "bye"},
                ],
            },
        )
        provider = JsonForestLogTemplateProvider(templates_dir=tmp_path)
        templates = provider.get_templates(locale="en")
        assert tuple(templates) == (
            ForestLogTemplate(id="forest.en.0001", text="Hi {user} +{delta}"),
            ForestLogTemplate(id="forest.en.0002", text="bye"),
        )
