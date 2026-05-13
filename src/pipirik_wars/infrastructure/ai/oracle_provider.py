"""AI-провайдер каталога oracle-предсказаний с in-memory кэшем и fallback (Спринт 4.1-M).

`AiOracleTemplateProvider` реализует `IOracleTemplateProvider`, но
вместо JSON-файлов берёт шаблоны из in-memory кэша, который наполняется
async-методом `refresh()` через `IAiTextGenerator`. Если кэш пуст для
запрошенной локали — fallback на `JsonOracleTemplateProvider`.

Жизненный цикл:
- На старте бота (`bot/main.py`) запускается background-task, который
  периодически вызывает `refresh(locale=...)` для каждой целевой локали.
- При первом вызове `get_templates(locale=...)` до завершения refresh —
  возвращаются static-шаблоны (zero-downtime).
- При неудаче LLM (`AiGenerationError`) — кэш для этой локали НЕ
  обновляется, но и не очищается; продолжаем использовать предыдущий
  AI-кэш либо static-fallback.

Контракт `get_templates()`:
- Возвращает `Sequence[OracleTemplate]` (как обычный JSON-провайдер).
- Никогда не бросает (fallback на static — это инвариант).
- ID-ы AI-шаблонов префиксованы `ai.<locale>.<index>` (стабильны в рамках
  одного refresh-а; меняются между refresh-ами).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from pipirik_wars.application.ai.ports import AiGenerationError, IAiTextGenerator
from pipirik_wars.application.oracle.templates import IOracleTemplateProvider
from pipirik_wars.domain.oracle import OracleTemplate

logger = logging.getLogger(__name__)


class AiOracleTemplateProvider(IOracleTemplateProvider):
    """In-memory кэш AI-сгенерированных oracle-шаблонов + fallback.

    Параметры:
    - `generator` — LLM-адаптер (`OpenAiTextGenerator` в проде,
      fake-stub в тестах).
    - `fallback` — статический JSON-провайдер; используется когда
      AI-кэш пуст или ещё не наполнен.
    - `batch_size` — сколько шаблонов запрашивать у LLM за один
      refresh-вызов на локаль.
    """

    __slots__ = ("_batch_size", "_cache", "_fallback", "_generator")

    def __init__(
        self,
        *,
        generator: IAiTextGenerator,
        fallback: IOracleTemplateProvider,
        batch_size: int = 30,
    ) -> None:
        self._generator = generator
        self._fallback = fallback
        self._batch_size = batch_size
        self._cache: dict[str, tuple[OracleTemplate, ...]] = {}

    def get_templates(self, *, locale: str) -> Sequence[OracleTemplate]:
        """Sync-доступ к шаблонам: AI-кэш если есть, иначе static fallback."""
        cached = self._cache.get(locale)
        if cached:
            return cached
        return self._fallback.get_templates(locale=locale)

    async def refresh(self, *, locale: str) -> bool:
        """Перегенерировать AI-кэш для локали через LLM.

        Возвращает `True` если кэш успешно обновлён; `False` при
        `AiGenerationError` (предыдущий кэш сохраняется).
        """
        try:
            texts = await self._generator.generate_oracle_predictions(
                locale=locale,
                count=self._batch_size,
            )
        except AiGenerationError as exc:
            logger.warning(
                "ai.oracle.refresh_failed locale=%s err=%s; keeping previous cache",
                locale,
                exc,
            )
            return False

        templates = tuple(
            OracleTemplate(id=f"ai.{locale}.{idx:04d}", text=text)
            for idx, text in enumerate(texts, start=1)
        )
        self._cache[locale] = templates
        logger.info(
            "ai.oracle.refresh_ok locale=%s count=%d",
            locale,
            len(templates),
        )
        return True

    @property
    def cached_locales(self) -> frozenset[str]:
        """Локали, для которых уже есть AI-кэш (для тестов/метрик)."""
        return frozenset(self._cache.keys())


__all__ = ["AiOracleTemplateProvider"]
