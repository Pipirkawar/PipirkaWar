"""Реализация `IEnchantHistoryReader` поверх таблицы `audit_log` (Спринт 3.4-C, C.5).

Используется trip-wire-ом анти-чита `EnchantItem`-use-case-а. Один SELECT
последних N=`SCAN_LIMIT` `ITEM_ENCHANT_ATTEMPT`-записей по игроку, отсортированных
DESC по `occurred_at`; фильтрация по `after.old_level ∈ [tier_min, tier_max]`
делается **в Python** (а не в SQL — портабельность с SQLite в тестах: JSON-path
операторы DB-specific). Таких попыток у одного игрока за день — единицы;
сканировать ≤ `SCAN_LIMIT` строк дешёво.

`IEnchantHistoryReader.get_recent_high_tier_outcomes` возвращает success-флаги
в DESC-порядке; success/success_1/success_2 → True.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import select

from pipirik_wars.domain.inventory import IEnchantHistoryReader
from pipirik_wars.domain.shared.ports.audit import AuditAction
from pipirik_wars.infrastructure.db.models import AuditLogORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

__all__ = ["SqlAlchemyEnchantHistoryReader"]


_SUCCESS_VALUES: Final[frozenset[str]] = frozenset(
    {"success", "success_1", "success_2"},
)
"""Outcome-значения, считающиеся успехом для trip-wire-а."""


_SCAN_LIMIT: Final[int] = 200
"""Сколько последних `ITEM_ENCHANT_ATTEMPT`-записей просматривать
для каждого запроса. Берём с запасом (×20 от `ANOMALY_WINDOW_SIZE=10`),
чтобы покрыть кейс «10 попыток на тире `+18 → +25` среди 200 общих»."""


class SqlAlchemyEnchantHistoryReader(IEnchantHistoryReader):
    """Чтение истории заточек из `audit_log`."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def get_recent_high_tier_outcomes(
        self,
        *,
        player_id: int,
        tier_min: int,
        tier_max: int,
        limit: int,
    ) -> tuple[bool, ...]:
        if player_id <= 0:
            raise ValueError(f"player_id must be > 0, got {player_id}")
        if tier_min < 0 or tier_max < tier_min:
            raise ValueError(
                f"invalid tier range: [{tier_min}, {tier_max}]",
            )
        if limit <= 0:
            raise ValueError(f"limit must be > 0, got {limit}")

        stmt = (
            select(AuditLogORM.after)
            .where(
                AuditLogORM.action == AuditAction.ITEM_ENCHANT_ATTEMPT.value,
                AuditLogORM.target_kind == "player",
                AuditLogORM.target_id == str(player_id),
            )
            .order_by(AuditLogORM.occurred_at.desc(), AuditLogORM.id.desc())
            .limit(_SCAN_LIMIT)
        )
        result = await self._uow.session.execute(stmt)
        rows = result.scalars().all()

        outcomes: list[bool] = []
        for after in rows:
            if not isinstance(after, dict):
                continue
            old_level_raw = after.get("old_level")
            if not isinstance(old_level_raw, int):
                continue
            if not (tier_min <= old_level_raw <= tier_max):
                continue
            outcome_raw = after.get("outcome")
            outcomes.append(
                isinstance(outcome_raw, str) and outcome_raw in _SUCCESS_VALUES,
            )
            if len(outcomes) >= limit:
                break

        return tuple(outcomes)
