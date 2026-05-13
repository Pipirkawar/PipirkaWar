"""AI-провайдер каталога duel-log-шаблонов (Спринт 4.1-M).

В отличие от oracle/forest, шаблоны дуэли разбиты на 3 категории
(`RoundOutcomeKind.BOTH_HIT` / `SINGLE_HIT` / `BOTH_BLOCKED`), поэтому
`refresh()` делает 3 LLM-вызова на локаль — по одному на категорию.

Если какая-то категория не сгенерировалась — для неё сохраняется
fallback на static-шаблоны через объединение с уже накопленным кэшем
(see `get_templates`). Если генерация прошла полностью — кэш содержит
все 3 категории.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from pipirik_wars.application.ai.ports import (
    AiGenerationError,
    DuelLogKind,
    IAiTextGenerator,
)
from pipirik_wars.application.pvp.log_templates import IDuelLogTemplateProvider
from pipirik_wars.domain.pvp import DuelLogTemplate
from pipirik_wars.domain.pvp.log_template import RoundOutcomeKind

logger = logging.getLogger(__name__)

_KIND_TO_PORT: dict[RoundOutcomeKind, DuelLogKind] = {
    RoundOutcomeKind.BOTH_HIT: "both_hit",
    RoundOutcomeKind.SINGLE_HIT: "single_hit",
    RoundOutcomeKind.BOTH_BLOCKED: "both_blocked",
}


class AiDuelLogTemplateProvider(IDuelLogTemplateProvider):
    """In-memory кэш AI-сгенерированных duel-log-шаблонов + fallback.

    Кэш организован per-`(locale, kind)`. На `refresh(locale)` делается
    три LLM-вызова (по одному на kind). Сбой одного вызова не очищает
    кэш других категорий и не блокирует возврат шаблонов (fallback на
    static при пустом кэше).
    """

    __slots__ = ("_batch_size", "_cache", "_fallback", "_generator")

    def __init__(
        self,
        *,
        generator: IAiTextGenerator,
        fallback: IDuelLogTemplateProvider,
        batch_size: int = 20,
    ) -> None:
        self._generator = generator
        self._fallback = fallback
        self._batch_size = batch_size
        self._cache: dict[str, tuple[DuelLogTemplate, ...]] = {}

    def get_templates(self, *, locale: str) -> Sequence[DuelLogTemplate]:
        cached = self._cache.get(locale)
        if cached:
            return cached
        return self._fallback.get_templates(locale=locale)

    async def refresh(self, *, locale: str) -> bool:
        """Перегенерировать кэш для всех 3 kind-категорий. True при полном успехе."""
        collected: list[DuelLogTemplate] = []
        all_ok = True
        for domain_kind, port_kind in _KIND_TO_PORT.items():
            try:
                texts = await self._generator.generate_duel_logs(
                    locale=locale,
                    count=self._batch_size,
                    kind=port_kind,
                )
            except AiGenerationError as exc:
                logger.warning(
                    "ai.duel.refresh_failed locale=%s kind=%s err=%s",
                    locale,
                    port_kind,
                    exc,
                )
                all_ok = False
                continue

            for idx, text in enumerate(texts, start=1):
                collected.append(
                    DuelLogTemplate(
                        id=f"ai.{locale}.{port_kind}.{idx:04d}",
                        text=text,
                        kind=domain_kind,
                    )
                )

        if collected:
            self._cache[locale] = tuple(collected)
            logger.info(
                "ai.duel.refresh_ok locale=%s count=%d kinds_complete=%s",
                locale,
                len(collected),
                all_ok,
            )
        return all_ok

    @property
    def cached_locales(self) -> frozenset[str]:
        return frozenset(self._cache.keys())


__all__ = ["AiDuelLogTemplateProvider"]
