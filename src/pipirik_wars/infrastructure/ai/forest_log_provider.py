"""AI-провайдер каталога forest-log-шаблонов (Спринт 4.1-M).

Аналогично `AiOracleTemplateProvider`: in-memory кэш, async-refresh
через LLM, fallback на `JsonForestLogTemplateProvider` при пустом кэше
или сбое генерации.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from pipirik_wars.application.ai.ports import AiGenerationError, IAiTextGenerator
from pipirik_wars.application.forest.log_templates import IForestLogTemplateProvider
from pipirik_wars.domain.forest import ForestLogTemplate

logger = logging.getLogger(__name__)


class AiForestLogTemplateProvider(IForestLogTemplateProvider):
    """In-memory кэш AI-сгенерированных forest-log-шаблонов + fallback."""

    __slots__ = ("_batch_size", "_cache", "_fallback", "_generator")

    def __init__(
        self,
        *,
        generator: IAiTextGenerator,
        fallback: IForestLogTemplateProvider,
        batch_size: int = 30,
    ) -> None:
        self._generator = generator
        self._fallback = fallback
        self._batch_size = batch_size
        self._cache: dict[str, tuple[ForestLogTemplate, ...]] = {}

    def get_templates(self, *, locale: str) -> Sequence[ForestLogTemplate]:
        cached = self._cache.get(locale)
        if cached:
            return cached
        return self._fallback.get_templates(locale=locale)

    async def refresh(self, *, locale: str) -> bool:
        try:
            texts = await self._generator.generate_forest_logs(
                locale=locale,
                count=self._batch_size,
            )
        except AiGenerationError as exc:
            logger.warning(
                "ai.forest.refresh_failed locale=%s err=%s; keeping previous cache",
                locale,
                exc,
            )
            return False

        templates = tuple(
            ForestLogTemplate(id=f"ai.{locale}.{idx:04d}", text=text)
            for idx, text in enumerate(texts, start=1)
        )
        self._cache[locale] = templates
        logger.info(
            "ai.forest.refresh_ok locale=%s count=%d",
            locale,
            len(templates),
        )
        return True

    @property
    def cached_locales(self) -> frozenset[str]:
        return frozenset(self._cache.keys())


__all__ = ["AiForestLogTemplateProvider"]
