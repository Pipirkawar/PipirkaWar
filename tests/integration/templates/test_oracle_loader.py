"""Integration-тесты `JsonOracleTemplateProvider` и реальных файлов
`config/templates/oracle_<locale>.json` (Спринт 1.4.B, ПД 1.4.5).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipirik_wars.domain.oracle import OracleNoTemplatesError, OracleTemplate
from pipirik_wars.infrastructure.templates import JsonOracleTemplateProvider
from pipirik_wars.shared.errors import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = REPO_ROOT / "config" / "templates"


class TestJsonOracleTemplateProviderShippedFiles:
    """Прод-каталоги: 200+ шаблонов RU и EN, валидный JSON, format(`{user}`)."""

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_at_least_200_templates(self, locale: str) -> None:
        provider = JsonOracleTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        assert len(templates) >= 200

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_ids_are_unique(self, locale: str) -> None:
        provider = JsonOracleTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        ids = [t.id for t in templates]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_user_placeholder_renders(self, locale: str) -> None:
        provider = JsonOracleTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        for tpl in templates:
            # `{user}` — единственный плейсхолдер; format должен пройти.
            tpl.text.format(user="Alice")

    def test_caches_per_locale(self) -> None:
        provider = JsonOracleTemplateProvider(templates_dir=TEMPLATES_DIR)
        first = provider.get_templates(locale="ru")
        second = provider.get_templates(locale="ru")
        assert first is second  # тот же кэшированный объект


class TestJsonOracleTemplateProviderLoadingErrors:
    def _write(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_falls_back_to_ru_when_locale_missing(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "oracle_ru.json",
            {
                "version": 1,
                "templates": [{"id": "x", "text": "y"}],
            },
        )
        provider = JsonOracleTemplateProvider(templates_dir=tmp_path)
        out = provider.get_templates(locale="es")
        assert len(out) == 1
        assert out[0].id == "x"

    def test_raises_when_no_files_exist(self, tmp_path: Path) -> None:
        provider = JsonOracleTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(OracleNoTemplatesError):
            provider.get_templates(locale="ru")

    def test_raises_on_empty_file(self, tmp_path: Path) -> None:
        self._write(tmp_path / "oracle_ru.json", {"version": 1, "templates": []})
        provider = JsonOracleTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(OracleNoTemplatesError):
            provider.get_templates(locale="ru")

    def test_raises_on_duplicate_ids(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "oracle_ru.json",
            {
                "version": 1,
                "templates": [
                    {"id": "x", "text": "1"},
                    {"id": "x", "text": "2"},
                ],
            },
        )
        provider = JsonOracleTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "oracle_ru.json"
        path.write_text("{ not valid json", encoding="utf-8")
        provider = JsonOracleTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_raises_on_root_not_object(self, tmp_path: Path) -> None:
        self._write(tmp_path / "oracle_ru.json", [{"id": "x", "text": "y"}])
        provider = JsonOracleTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError):
            provider.get_templates(locale="ru")

    def test_loads_valid_payload(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "oracle_en.json",
            {
                "version": 1,
                "templates": [
                    {"id": "oracle.en.0001", "text": "Hi {user}"},
                    {"id": "oracle.en.0002", "text": "Bye"},
                ],
            },
        )
        provider = JsonOracleTemplateProvider(templates_dir=tmp_path)
        templates = provider.get_templates(locale="en")
        assert tuple(templates) == (
            OracleTemplate(id="oracle.en.0001", text="Hi {user}"),
            OracleTemplate(id="oracle.en.0002", text="Bye"),
        )
