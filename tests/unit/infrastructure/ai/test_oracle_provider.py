"""Unit-тесты `AiOracleTemplateProvider` (Спринт 4.1-M, шаг M.4).

Контракт:
* Пока кэш пуст — `get_templates(locale)` возвращает fallback (static).
* После `refresh(locale)` — кэш содержит AI-шаблоны; `get_templates()`
  возвращает их.
* При `AiGenerationError` от LLM `refresh()` возвращает `False`, кэш
  не очищается (если был наполнен — остаётся), fallback продолжает
  работать для непопулярных локалей.
* ID-ы AI-шаблонов имеют префикс `ai.<locale>.NNNN`.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from pipirik_wars.application.ai.ports import (
    AiGenerationError,
    DuelLogKind,
    IAiTextGenerator,
)
from pipirik_wars.application.oracle.templates import IOracleTemplateProvider
from pipirik_wars.domain.oracle import OracleTemplate
from pipirik_wars.infrastructure.ai.oracle_provider import AiOracleTemplateProvider

pytestmark = pytest.mark.asyncio


class _FakeGenerator(IAiTextGenerator):
    """Подделка `IAiTextGenerator` с настраиваемым ответом per locale."""

    def __init__(self) -> None:
        self.oracle_responses: dict[str, Sequence[str] | BaseException] = {}
        self.calls: list[tuple[str, int]] = []

    async def generate_oracle_predictions(self, *, locale: str, count: int) -> Sequence[str]:
        self.calls.append((locale, count))
        value = self.oracle_responses.get(locale)
        if isinstance(value, BaseException):
            raise value
        if value is None:
            return ()
        return value

    async def generate_forest_logs(self, *, locale: str, count: int) -> Sequence[str]:
        return ()

    async def generate_duel_logs(
        self, *, locale: str, count: int, kind: DuelLogKind
    ) -> Sequence[str]:
        return ()


class _StaticFallback(IOracleTemplateProvider):
    """Подделка JsonOracleTemplateProvider: возвращает фиксированный список."""

    def __init__(self, templates: Sequence[OracleTemplate]) -> None:
        self._templates = tuple(templates)

    def get_templates(self, *, locale: str) -> Sequence[OracleTemplate]:
        return self._templates


@pytest.fixture
def fallback_templates() -> tuple[OracleTemplate, ...]:
    return (
        OracleTemplate(id="static.ru.0001", text="static-1 {user}"),
        OracleTemplate(id="static.ru.0002", text="static-2 {user}"),
    )


class TestGetTemplatesFallback:
    async def test_empty_cache_returns_fallback(
        self, fallback_templates: tuple[OracleTemplate, ...]
    ) -> None:
        provider = AiOracleTemplateProvider(
            generator=_FakeGenerator(),
            fallback=_StaticFallback(fallback_templates),
        )
        result = provider.get_templates(locale="ru")
        assert tuple(result) == fallback_templates

    async def test_fallback_used_for_uncached_locale(
        self, fallback_templates: tuple[OracleTemplate, ...]
    ) -> None:
        # Кэш будем наполнять только для "en" в refresh-тесте; "ru" остаётся
        # на fallback.
        provider = AiOracleTemplateProvider(
            generator=_FakeGenerator(),
            fallback=_StaticFallback(fallback_templates),
        )
        assert tuple(provider.get_templates(locale="ru")) == fallback_templates


class TestRefreshSuccess:
    async def test_refresh_populates_cache(
        self, fallback_templates: tuple[OracleTemplate, ...]
    ) -> None:
        gen = _FakeGenerator()
        gen.oracle_responses["ru"] = ("Привет {user}!", "Удачи {user}.")
        provider = AiOracleTemplateProvider(
            generator=gen,
            fallback=_StaticFallback(fallback_templates),
            batch_size=2,
        )
        ok = await provider.refresh(locale="ru")
        assert ok is True
        result = provider.get_templates(locale="ru")
        texts = tuple(t.text for t in result)
        ids = tuple(t.id for t in result)
        assert texts == ("Привет {user}!", "Удачи {user}.")
        assert ids == ("ai.ru.0001", "ai.ru.0002")

    async def test_refresh_uses_batch_size(
        self, fallback_templates: tuple[OracleTemplate, ...]
    ) -> None:
        gen = _FakeGenerator()
        gen.oracle_responses["en"] = ("Hello {user}!",)
        provider = AiOracleTemplateProvider(
            generator=gen,
            fallback=_StaticFallback(fallback_templates),
            batch_size=7,
        )
        await provider.refresh(locale="en")
        assert gen.calls == [("en", 7)]

    async def test_cached_locales_property(
        self, fallback_templates: tuple[OracleTemplate, ...]
    ) -> None:
        gen = _FakeGenerator()
        gen.oracle_responses["ru"] = ("{user}!",)
        provider = AiOracleTemplateProvider(
            generator=gen,
            fallback=_StaticFallback(fallback_templates),
        )
        assert provider.cached_locales == frozenset()
        await provider.refresh(locale="ru")
        assert provider.cached_locales == frozenset({"ru"})


class TestRefreshFailure:
    async def test_refresh_returns_false_on_ai_error(
        self, fallback_templates: tuple[OracleTemplate, ...]
    ) -> None:
        gen = _FakeGenerator()
        gen.oracle_responses["ru"] = AiGenerationError("LLM down")
        provider = AiOracleTemplateProvider(
            generator=gen,
            fallback=_StaticFallback(fallback_templates),
        )
        ok = await provider.refresh(locale="ru")
        assert ok is False
        # Кэш пуст, get_templates падает на fallback.
        assert tuple(provider.get_templates(locale="ru")) == fallback_templates

    async def test_refresh_failure_preserves_previous_cache(
        self, fallback_templates: tuple[OracleTemplate, ...]
    ) -> None:
        gen = _FakeGenerator()
        provider = AiOracleTemplateProvider(
            generator=gen,
            fallback=_StaticFallback(fallback_templates),
        )
        # Первый успешный refresh
        gen.oracle_responses["ru"] = ("First {user}.",)
        await provider.refresh(locale="ru")
        # Второй — падает с AiGenerationError
        gen.oracle_responses["ru"] = AiGenerationError("transient")
        ok = await provider.refresh(locale="ru")
        assert ok is False
        # Старый кэш сохранён
        cached = provider.get_templates(locale="ru")
        assert tuple(t.text for t in cached) == ("First {user}.",)
