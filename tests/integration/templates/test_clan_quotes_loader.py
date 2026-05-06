"""Integration-тесты `JsonClanQuoteTemplateProvider` и реальных файлов
`config/templates/clan_quotes_<locale>.json` (Спринт 2.3.D, ПД §5 / 2.3.4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipirik_wars.domain.daily_head import (
    ALLOWED_QUOTE_TAGS,
    ClanQuoteCatalogEmptyError,
    ClanQuoteTemplate,
)
from pipirik_wars.infrastructure.templates import JsonClanQuoteTemplateProvider
from pipirik_wars.shared.errors import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = REPO_ROOT / "config" / "templates"

_STYLE_TAGS: frozenset[str] = frozenset(ALLOWED_QUOTE_TAGS - {"profanity"})


class TestJsonClanQuoteTemplateProviderShippedFiles:
    """Прод-каталоги: ≥ 100 цитат RU и EN, валидный JSON, format(`{user}`),
    каждая цитата помечена ≥ 1 стилистическим тегом (statham / vk_pablik /
    auf / meme).
    """

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_at_least_100_templates(self, locale: str) -> None:
        provider = JsonClanQuoteTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        assert len(templates) >= 100

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_ids_are_unique(self, locale: str) -> None:
        provider = JsonClanQuoteTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        ids = [t.id for t in templates]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_user_placeholder_renders(self, locale: str) -> None:
        """Все шаблоны должны корректно format-иться плейсхолдером `{user}`."""
        provider = JsonClanQuoteTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        for tpl in templates:
            tpl.text.format(user="Alice")

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_every_template_has_at_least_one_style_tag(self, locale: str) -> None:
        """ПД 2.3.4: «теги стиля заполнены»: ≥ 1 из {statham, vk_pablik, auf, meme}."""
        provider = JsonClanQuoteTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        for tpl in templates:
            style = set(tpl.tags) & _STYLE_TAGS
            assert style, f"template {tpl.id!r} has no style tag, only {tpl.tags!r}"

    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_user_placeholder_present_in_every_template(self, locale: str) -> None:
        """Каждая цитата обращается к новому главе клана дня — `{user}` обязателен."""
        provider = JsonClanQuoteTemplateProvider(templates_dir=TEMPLATES_DIR)
        templates = provider.get_templates(locale=locale)
        for tpl in templates:
            assert "{user}" in tpl.text, f"template {tpl.id!r} missing {{user}} placeholder"

    def test_caches_per_locale(self) -> None:
        provider = JsonClanQuoteTemplateProvider(templates_dir=TEMPLATES_DIR)
        first = provider.get_templates(locale="ru")
        second = provider.get_templates(locale="ru")
        assert first is second  # тот же кэшированный объект


class TestJsonClanQuoteTemplateProviderLoadingErrors:
    def _write(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_falls_back_to_ru_when_locale_missing(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "clan_quotes_ru.json",
            {
                "version": 1,
                "templates": [{"id": "x", "text": "y {user}", "tags": ["statham"]}],
            },
        )
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        out = provider.get_templates(locale="es")
        assert len(out) == 1
        assert out[0].id == "x"

    def test_raises_when_no_files_exist(self, tmp_path: Path) -> None:
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ClanQuoteCatalogEmptyError):
            provider.get_templates(locale="ru")

    def test_raises_on_empty_file(self, tmp_path: Path) -> None:
        self._write(tmp_path / "clan_quotes_ru.json", {"version": 1, "templates": []})
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ClanQuoteCatalogEmptyError):
            provider.get_templates(locale="ru")

    def test_raises_on_duplicate_ids(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "clan_quotes_ru.json",
            {
                "version": 1,
                "templates": [
                    {"id": "x", "text": "1 {user}", "tags": ["statham"]},
                    {"id": "x", "text": "2 {user}", "tags": ["meme"]},
                ],
            },
        )
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError, match="duplicate template id"):
            provider.get_templates(locale="ru")

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "clan_quotes_ru.json"
        path.write_text("{ not valid json", encoding="utf-8")
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError, match="invalid JSON"):
            provider.get_templates(locale="ru")

    def test_raises_on_root_not_object(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "clan_quotes_ru.json", [{"id": "x", "text": "y", "tags": ["statham"]}]
        )
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError, match="root must be a JSON object"):
            provider.get_templates(locale="ru")

    def test_raises_on_templates_not_list(self, tmp_path: Path) -> None:
        self._write(tmp_path / "clan_quotes_ru.json", {"version": 1, "templates": "oops"})
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError, match="'templates' must be a list"):
            provider.get_templates(locale="ru")

    def test_raises_on_entry_not_object(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "clan_quotes_ru.json",
            {"version": 1, "templates": ["oops"]},
        )
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError, match="must be an object"):
            provider.get_templates(locale="ru")

    def test_raises_when_id_missing(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "clan_quotes_ru.json",
            {"version": 1, "templates": [{"text": "y {user}", "tags": ["statham"]}]},
        )
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError, match="must have string 'id' and 'text'"):
            provider.get_templates(locale="ru")

    def test_raises_when_tags_missing(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "clan_quotes_ru.json",
            {"version": 1, "templates": [{"id": "x", "text": "y {user}"}]},
        )
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError, match="must have 'tags' as a list of strings"):
            provider.get_templates(locale="ru")

    def test_raises_when_tags_not_list_of_strings(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "clan_quotes_ru.json",
            {"version": 1, "templates": [{"id": "x", "text": "y {user}", "tags": ["statham", 42]}]},
        )
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError, match="must have 'tags' as a list of strings"):
            provider.get_templates(locale="ru")

    def test_raises_on_unknown_tag(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "clan_quotes_ru.json",
            {"version": 1, "templates": [{"id": "x", "text": "y", "tags": ["unknown"]}]},
        )
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        with pytest.raises(ConfigError, match="unknown tags"):
            provider.get_templates(locale="ru")

    def test_loads_valid_payload_with_profanity(self, tmp_path: Path) -> None:
        self._write(
            tmp_path / "clan_quotes_en.json",
            {
                "version": 1,
                "templates": [
                    {"id": "clan_quote.en.0001", "text": "Hi {user}", "tags": ["statham"]},
                    {
                        "id": "clan_quote.en.0002",
                        "text": "By {user}",
                        "tags": ["vk_pablik", "profanity"],
                    },
                ],
            },
        )
        provider = JsonClanQuoteTemplateProvider(templates_dir=tmp_path)
        templates = provider.get_templates(locale="en")
        assert tuple(templates) == (
            ClanQuoteTemplate(id="clan_quote.en.0001", text="Hi {user}", tags=("statham",)),
            ClanQuoteTemplate(
                id="clan_quote.en.0002",
                text="By {user}",
                tags=("vk_pablik", "profanity"),
            ),
        )
        assert templates[1].has_profanity is True
