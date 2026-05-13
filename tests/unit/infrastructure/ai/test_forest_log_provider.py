"""Unit-тесты `AiForestLogTemplateProvider` (Спринт 4.1-M, шаг M.5)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from pipirik_wars.application.ai.ports import (
    AiGenerationError,
    DuelLogKind,
    IAiTextGenerator,
)
from pipirik_wars.application.forest.log_templates import IForestLogTemplateProvider
from pipirik_wars.domain.forest import ForestLogTemplate
from pipirik_wars.infrastructure.ai.forest_log_provider import (
    AiForestLogTemplateProvider,
)

pytestmark = pytest.mark.asyncio


class _FakeGenerator(IAiTextGenerator):
    def __init__(self) -> None:
        self.forest_responses: dict[str, Sequence[str] | BaseException] = {}
        self.calls: list[tuple[str, int]] = []

    async def generate_oracle_predictions(self, *, locale: str, count: int) -> Sequence[str]:
        return ()

    async def generate_forest_logs(self, *, locale: str, count: int) -> Sequence[str]:
        self.calls.append((locale, count))
        value = self.forest_responses.get(locale)
        if isinstance(value, BaseException):
            raise value
        if value is None:
            return ()
        return value

    async def generate_duel_logs(
        self, *, locale: str, count: int, kind: DuelLogKind
    ) -> Sequence[str]:
        return ()


class _StaticFallback(IForestLogTemplateProvider):
    def __init__(self, templates: Sequence[ForestLogTemplate]) -> None:
        self._templates = tuple(templates)

    def get_templates(self, *, locale: str) -> Sequence[ForestLogTemplate]:
        return self._templates


@pytest.fixture
def fallback_templates() -> tuple[ForestLogTemplate, ...]:
    return (ForestLogTemplate(id="static.ru.0001", text="static {user}"),)


class TestAiForestLogTemplateProvider:
    async def test_empty_cache_returns_fallback(
        self, fallback_templates: tuple[ForestLogTemplate, ...]
    ) -> None:
        provider = AiForestLogTemplateProvider(
            generator=_FakeGenerator(),
            fallback=_StaticFallback(fallback_templates),
        )
        assert tuple(provider.get_templates(locale="ru")) == fallback_templates

    async def test_refresh_populates_cache(
        self, fallback_templates: tuple[ForestLogTemplate, ...]
    ) -> None:
        gen = _FakeGenerator()
        gen.forest_responses["ru"] = ("{user} в лесу.", "{user} нашёл орех.")
        provider = AiForestLogTemplateProvider(
            generator=gen,
            fallback=_StaticFallback(fallback_templates),
            batch_size=2,
        )
        ok = await provider.refresh(locale="ru")
        assert ok is True
        cached = provider.get_templates(locale="ru")
        assert tuple(t.text for t in cached) == ("{user} в лесу.", "{user} нашёл орех.")
        assert tuple(t.id for t in cached) == ("ai.ru.0001", "ai.ru.0002")

    async def test_refresh_failure_returns_false(
        self, fallback_templates: tuple[ForestLogTemplate, ...]
    ) -> None:
        gen = _FakeGenerator()
        gen.forest_responses["ru"] = AiGenerationError("LLM down")
        provider = AiForestLogTemplateProvider(
            generator=gen,
            fallback=_StaticFallback(fallback_templates),
        )
        ok = await provider.refresh(locale="ru")
        assert ok is False
        assert tuple(provider.get_templates(locale="ru")) == fallback_templates
