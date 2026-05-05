"""Unit-тесты `ForestLogTemplate` + `pick_forest_log_template(...)` (Спринт 1.5.G)."""

from __future__ import annotations

import pytest

from pipirik_wars.domain.forest import (
    ForestLogNoTemplatesError,
    ForestLogTemplate,
    pick_forest_log_template,
)
from tests.fakes import FakeRandom


class TestForestLogTemplateValidation:
    def test_accepts_minimal_valid_payload(self) -> None:
        tpl = ForestLogTemplate(id="forest.ru.0001", text="Лог")
        assert tpl.id == "forest.ru.0001"
        assert tpl.text == "Лог"

    def test_rejects_empty_id(self) -> None:
        with pytest.raises(ValueError):
            ForestLogTemplate(id="", text="Лог")

    def test_rejects_whitespace_id(self) -> None:
        with pytest.raises(ValueError):
            ForestLogTemplate(id=" forest.ru.0001 ", text="Лог")

    def test_rejects_empty_text(self) -> None:
        with pytest.raises(ValueError):
            ForestLogTemplate(id="forest.ru.0001", text="")

    def test_rejects_whitespace_text(self) -> None:
        with pytest.raises(ValueError):
            ForestLogTemplate(id="forest.ru.0001", text=" Лог ")


def _build_templates(n: int = 10) -> list[ForestLogTemplate]:
    return [ForestLogTemplate(id=f"forest.ru.{i:04d}", text=f"text {i}") for i in range(n)]


class TestPickForestLogTemplate:
    def test_returns_template_from_pool(self) -> None:
        templates = _build_templates(5)
        random = FakeRandom(seed=42)

        picked = pick_forest_log_template(random=random, templates=templates)

        assert picked in templates

    def test_deterministic_with_same_seed(self) -> None:
        templates = _build_templates(20)

        a = pick_forest_log_template(random=FakeRandom(seed=7), templates=templates)
        b = pick_forest_log_template(random=FakeRandom(seed=7), templates=templates)

        assert a == b

    def test_empty_templates_raises(self) -> None:
        with pytest.raises(ForestLogNoTemplatesError):
            pick_forest_log_template(random=FakeRandom(seed=0), templates=[])
