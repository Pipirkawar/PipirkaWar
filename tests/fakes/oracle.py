"""In-memory реализации портов `/oracle` для unit-тестов."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from pipirik_wars.application.oracle import IOracleTemplateProvider
from pipirik_wars.domain.oracle import (
    IOracleHistoryRepository,
    OracleInvocation,
    OracleTemplate,
)
from pipirik_wars.shared.errors import IntegrityError


@dataclass
class FakeOracleHistoryRepository(IOracleHistoryRepository):
    """In-memory эмулятор `oracle_invocations` с UNIQUE-индексом
    по `(player_id, moscow_date)`.
    """

    rows: list[OracleInvocation] = field(default_factory=list)

    async def add(self, invocation: OracleInvocation) -> None:
        for row in self.rows:
            if row.player_id == invocation.player_id and row.moscow_date == invocation.moscow_date:
                raise IntegrityError(
                    f"player_id={invocation.player_id} already has /oracle "
                    f"on {invocation.moscow_date.isoformat()}"
                )
        self.rows.append(invocation)

    async def get_for_day(
        self,
        *,
        player_id: int,
        moscow_date: date,
    ) -> OracleInvocation | None:
        for row in self.rows:
            if row.player_id == player_id and row.moscow_date == moscow_date:
                return row
        return None


@dataclass
class FakeOracleTemplateProvider(IOracleTemplateProvider):
    """In-memory provider шаблонов: per-locale заранее заданный список."""

    catalog: dict[str, tuple[OracleTemplate, ...]] = field(default_factory=dict)

    def get_templates(self, *, locale: str) -> Sequence[OracleTemplate]:
        if locale in self.catalog:
            return self.catalog[locale]
        # Fallback на ru, как реальный JSON-провайдер.
        if "ru" in self.catalog:
            return self.catalog["ru"]
        return ()


__all__ = [
    "FakeOracleHistoryRepository",
    "FakeOracleTemplateProvider",
]
