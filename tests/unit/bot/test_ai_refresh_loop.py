"""Unit-тесты `_ai_refresh_loop` (Спринт 4.1-M, шаг M.6).

Фоновый refresh-таск: пробегает по `SUPPORTED_LOCALES`, на каждом
AI-провайдере вызывает `await provider.refresh(locale=...)`. После
полного прохода — `asyncio.sleep(interval_seconds)`. Цикл бесконечен,
прерывается извне через `task.cancel()`.

Контракт-проверки:
* Если все три AI-провайдера = None → функция возвращается мгновенно
  (важно для пути с `AI_ENABLED=False`).
* На каждой итерации refresh вызывается ровно по одному разу per
  (locale, provider).
* `cancel()` корректно завершает таск.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pipirik_wars.application.i18n import SUPPORTED_LOCALES
from pipirik_wars.bot.main import _ai_refresh_loop

pytestmark = pytest.mark.asyncio


@dataclass(slots=True)
class _RefreshCall:
    locale: str
    provider_name: str


class _FakeAiProvider:
    def __init__(self, name: str, log: list[_RefreshCall]) -> None:
        self._name = name
        self._log = log

    async def refresh(self, *, locale: str) -> bool:
        self._log.append(_RefreshCall(locale=locale, provider_name=self._name))
        return True


@dataclass(slots=True)
class _FakeContainer:
    ai_oracle_provider: object | None
    ai_forest_provider: object | None
    ai_duel_provider: object | None


class TestAiRefreshLoopDisabled:
    async def test_returns_immediately_when_all_providers_none(self) -> None:
        container = _FakeContainer(
            ai_oracle_provider=None,
            ai_forest_provider=None,
            ai_duel_provider=None,
        )
        # Должен завершиться мгновенно без ошибок.
        await asyncio.wait_for(
            _ai_refresh_loop(container, interval_seconds=999.0),  # type: ignore[arg-type]
            timeout=1.0,
        )


class TestAiRefreshLoopEnabled:
    async def test_refreshes_every_locale_for_every_provider(self) -> None:
        """Запускаем loop, ждём одну полную итерацию, отменяем."""
        log: list[_RefreshCall] = []
        oracle = _FakeAiProvider("oracle", log)
        forest = _FakeAiProvider("forest", log)
        duel = _FakeAiProvider("duel", log)
        container = _FakeContainer(
            ai_oracle_provider=oracle,
            ai_forest_provider=forest,
            ai_duel_provider=duel,
        )
        # interval=300 секунд — после первого прохода loop засядет в sleep,
        # мы его cancel-нём.
        task = asyncio.create_task(
            _ai_refresh_loop(container, interval_seconds=300.0)  # type: ignore[arg-type]
        )
        # Даём loop-у время сделать первый полный проход. SUPPORTED_LOCALES
        # содержит 8 локалей × 3 провайдера = 24 вызова refresh; они
        # async, без I/O, отрабатывают мгновенно.
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Проверяем, что каждый (locale, provider) встретился ровно 1 раз.
        expected_pairs = {
            (locale, name) for locale in SUPPORTED_LOCALES for name in ("oracle", "forest", "duel")
        }
        actual_pairs = {(call.locale, call.provider_name) for call in log}
        assert actual_pairs == expected_pairs

    async def test_skips_none_providers(self) -> None:
        """Если только один провайдер не None, остальные skip-аются."""
        log: list[_RefreshCall] = []
        oracle = _FakeAiProvider("oracle", log)
        container = _FakeContainer(
            ai_oracle_provider=oracle,
            ai_forest_provider=None,
            ai_duel_provider=None,
        )
        task = asyncio.create_task(
            _ai_refresh_loop(container, interval_seconds=300.0)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Только oracle refresh-ы, по одному на локаль.
        assert {call.provider_name for call in log} == {"oracle"}
        assert {call.locale for call in log} == set(SUPPORTED_LOCALES)
