"""Unit-тесты `AiDuelLogTemplateProvider` (Спринт 4.1-M, шаг M.5).

Duel-провайдер уникален: на `refresh(locale)` делает 3 LLM-вызова —
по одному на `RoundOutcomeKind`-категорию. Тесты проверяют:
* Все 3 категории при успехе попадают в кэш с правильным `kind` полем.
* Сбой одной категории → `all_ok=False`, но кэш содержит остальные.
* Сбой всех трёх → `all_ok=False`, кэш не наполняется → fallback.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from pipirik_wars.application.ai.ports import (
    AiGenerationError,
    DuelLogKind,
    IAiTextGenerator,
)
from pipirik_wars.application.pvp.log_templates import IDuelLogTemplateProvider
from pipirik_wars.domain.pvp import DuelLogTemplate
from pipirik_wars.domain.pvp.log_template import RoundOutcomeKind
from pipirik_wars.infrastructure.ai.duel_log_provider import AiDuelLogTemplateProvider

pytestmark = pytest.mark.asyncio


class _FakeGenerator(IAiTextGenerator):
    def __init__(self) -> None:
        # Ключ: (locale, kind) → Sequence[str] либо BaseException.
        self.duel_responses: dict[tuple[str, DuelLogKind], Sequence[str] | BaseException] = {}
        self.calls: list[tuple[str, int, DuelLogKind]] = []

    async def generate_oracle_predictions(self, *, locale: str, count: int) -> Sequence[str]:
        return ()

    async def generate_forest_logs(self, *, locale: str, count: int) -> Sequence[str]:
        return ()

    async def generate_duel_logs(
        self, *, locale: str, count: int, kind: DuelLogKind
    ) -> Sequence[str]:
        self.calls.append((locale, count, kind))
        value = self.duel_responses.get((locale, kind))
        if isinstance(value, BaseException):
            raise value
        if value is None:
            return ()
        return value


class _StaticFallback(IDuelLogTemplateProvider):
    def __init__(self, templates: Sequence[DuelLogTemplate]) -> None:
        self._templates = tuple(templates)

    def get_templates(self, *, locale: str) -> Sequence[DuelLogTemplate]:
        return self._templates


@pytest.fixture
def fallback_templates() -> tuple[DuelLogTemplate, ...]:
    return (
        DuelLogTemplate(
            id="static.ru.both_hit.0001",
            text="static {p1} {p2}",
            kind=RoundOutcomeKind.BOTH_HIT,
        ),
    )


class TestAiDuelLogTemplateProviderRefresh:
    async def test_refresh_calls_three_kinds(
        self, fallback_templates: tuple[DuelLogTemplate, ...]
    ) -> None:
        gen = _FakeGenerator()
        gen.duel_responses[("ru", "both_hit")] = ("{p1} ↔ {p2} обмен.",)
        gen.duel_responses[("ru", "single_hit")] = ("{attacker} > {defender}.",)
        gen.duel_responses[("ru", "both_blocked")] = ("{p1} и {p2} в защите.",)
        provider = AiDuelLogTemplateProvider(
            generator=gen,
            fallback=_StaticFallback(fallback_templates),
            batch_size=1,
        )
        ok = await provider.refresh(locale="ru")
        assert ok is True
        assert len(gen.calls) == 3
        kinds_called = {call[2] for call in gen.calls}
        assert kinds_called == {"both_hit", "single_hit", "both_blocked"}

    async def test_cached_templates_have_correct_kind(
        self, fallback_templates: tuple[DuelLogTemplate, ...]
    ) -> None:
        gen = _FakeGenerator()
        gen.duel_responses[("ru", "both_hit")] = ("{p1} ↔ {p2}.",)
        gen.duel_responses[("ru", "single_hit")] = ("{attacker} > {defender}.",)
        gen.duel_responses[("ru", "both_blocked")] = ("{p1} = {p2}.",)
        provider = AiDuelLogTemplateProvider(
            generator=gen,
            fallback=_StaticFallback(fallback_templates),
            batch_size=1,
        )
        await provider.refresh(locale="ru")
        cached = provider.get_templates(locale="ru")
        kinds = {t.kind for t in cached}
        assert kinds == {
            RoundOutcomeKind.BOTH_HIT,
            RoundOutcomeKind.SINGLE_HIT,
            RoundOutcomeKind.BOTH_BLOCKED,
        }


class TestAiDuelLogTemplateProviderFailures:
    async def test_one_kind_fails_others_cached(
        self, fallback_templates: tuple[DuelLogTemplate, ...]
    ) -> None:
        gen = _FakeGenerator()
        gen.duel_responses[("ru", "both_hit")] = ("{p1} ↔ {p2}.",)
        gen.duel_responses[("ru", "single_hit")] = AiGenerationError("LLM down")
        gen.duel_responses[("ru", "both_blocked")] = ("{p1} = {p2}.",)
        provider = AiDuelLogTemplateProvider(
            generator=gen,
            fallback=_StaticFallback(fallback_templates),
            batch_size=1,
        )
        ok = await provider.refresh(locale="ru")
        assert ok is False
        cached = provider.get_templates(locale="ru")
        assert len(cached) == 2  # 2 успешных kind-а
        kinds = {t.kind for t in cached}
        assert kinds == {RoundOutcomeKind.BOTH_HIT, RoundOutcomeKind.BOTH_BLOCKED}

    async def test_all_kinds_fail_fallback_used(
        self, fallback_templates: tuple[DuelLogTemplate, ...]
    ) -> None:
        gen = _FakeGenerator()
        gen.duel_responses[("ru", "both_hit")] = AiGenerationError("e1")
        gen.duel_responses[("ru", "single_hit")] = AiGenerationError("e2")
        gen.duel_responses[("ru", "both_blocked")] = AiGenerationError("e3")
        provider = AiDuelLogTemplateProvider(
            generator=gen,
            fallback=_StaticFallback(fallback_templates),
            batch_size=1,
        )
        ok = await provider.refresh(locale="ru")
        assert ok is False
        # Кэш пуст → fallback
        assert tuple(provider.get_templates(locale="ru")) == fallback_templates

    async def test_empty_cache_returns_fallback(
        self, fallback_templates: tuple[DuelLogTemplate, ...]
    ) -> None:
        provider = AiDuelLogTemplateProvider(
            generator=_FakeGenerator(),
            fallback=_StaticFallback(fallback_templates),
        )
        assert tuple(provider.get_templates(locale="ru")) == fallback_templates
