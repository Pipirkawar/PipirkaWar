"""Доменный сервис «Глава клана дня» (ГДД §6.1, ПД §6 / Спринт 2.3.A).

`DailyHeadService` инкапсулирует чистую часть логики:

1. Чтение из репозитория, есть ли уже глава на `(clan_id, moscow_date)`
   (если есть — возвращаем существующего, идемпотентность по сутка-кланам).
2. Запрос «активные за `active_within_days` дней» из
   `IDailyActivityRepository`.
3. Проверка `min_active_members` (если меньше —
   `DailyHeadInsufficientActivityError`).
4. Anti-repeat-фильтр: исключаем `avoid_last_n` свежих глав; если после
   фильтра пул пуст — берём всех активных (правило fail-open: лучше
   повтор, чем «не назначить»).
5. `IRandom.choice(...)` из оставшегося пула.
6. `IRandom.randint(bonus_min, bonus_max)` — прибавка длины.
7. Возврат `DailyHeadAssignment` (без записи в БД — это делает
   `IDailyHeadRepository.add(...)` use-case-уровня).

Не пишет ни в БД, ни в audit, ни в length_granter — это всё side-effects,
их выполняет use-case (Спринт 2.3.C). Сервис чистый — детерминированно
тестируется на `FakeRandom(seed=...)` и in-memory репах.

Возвращает `DailyHeadAssignment` с `id=None` (PK ставит репо при
`add()`-е) и `assigned_at=now` (timezone-aware UTC от `IClock`).
"""

from __future__ import annotations

from collections.abc import Sequence

from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.daily_head.entities import (
    DailyHeadAssignment,
    DailyHeadSource,
)
from pipirik_wars.domain.daily_head.errors import (
    DailyHeadInsufficientActivityError,
)
from pipirik_wars.domain.daily_head.repositories import (
    IDailyActivityRepository,
    IDailyHeadRepository,
)
from pipirik_wars.domain.shared.ports import IClock, IRandom


class DailyHeadService:
    """Чистая логика выбора главы клана дня."""

    def __init__(
        self,
        *,
        balance: BalanceConfig,
        clock: IClock,
        random: IRandom,
        heads: IDailyHeadRepository,
        activity: IDailyActivityRepository,
    ) -> None:
        self._balance = balance
        self._clock = clock
        self._random = random
        self._heads = heads
        self._activity = activity

    async def assign_or_get(
        self,
        *,
        clan_id: int,
        source: DailyHeadSource,
    ) -> DailyHeadAssignment:
        """Получить главу клана на сегодня или назначить нового.

        Идемпотентен по `(clan_id, moscow_date)`: если глава уже
        назначен — возвращает существующую запись (с её исходным
        `source`-полем; повторный триггер не перезаписывает аналитику).

        Не пишет в БД сам — выбирает кандидата и формирует
        `DailyHeadAssignment` с `id=None`. Use-case 2.3.C обернёт
        этот вызов в UoW и сделает `heads.add(...)`.
        """
        moscow_date = self._clock.moscow_date()

        existing = await self._heads.get_by_clan_and_date(
            clan_id=clan_id,
            moscow_date=moscow_date,
        )
        if existing is not None:
            return existing

        cfg = self._balance.daily_head
        active_ids = await self._activity.list_active_member_ids(
            clan_id=clan_id,
            within_days=cfg.active_within_days,
        )
        if len(active_ids) < cfg.min_active_members:
            raise DailyHeadInsufficientActivityError(
                clan_id=clan_id,
                active_count=len(active_ids),
                required=cfg.min_active_members,
            )

        candidate_ids = await self._filter_avoid_repeat(
            clan_id=clan_id,
            active_ids=active_ids,
            avoid_last_n=cfg.avoid_last_n,
        )
        # При исключении всех активных — fail-open: лучше повтор,
        # чем «никого». На практике эта ветка не срабатывает, потому
        # что `min_active_members >= 5` и `avoid_last_n <= 3` обычно.
        candidate_pool = candidate_ids if candidate_ids else tuple(active_ids)

        chosen_id = self._random.choice(candidate_pool)
        bonus_cm = self._random.randint(cfg.bonus_min, cfg.bonus_max)

        return DailyHeadAssignment(
            id=None,
            clan_id=clan_id,
            player_id=chosen_id,
            moscow_date=moscow_date,
            source=source,
            bonus_cm=bonus_cm,
            assigned_at=self._clock.now(),
        )

    async def _filter_avoid_repeat(
        self,
        *,
        clan_id: int,
        active_ids: Sequence[int],
        avoid_last_n: int,
    ) -> tuple[int, ...]:
        """Исключить из пула свежих глав (последние `avoid_last_n` назначений)."""
        if avoid_last_n <= 0:
            return tuple(active_ids)
        recent = await self._heads.list_recent_for_clan(
            clan_id=clan_id,
            limit=avoid_last_n,
        )
        recent_ids = {entry.player_id for entry in recent}
        return tuple(pid for pid in active_ids if pid not in recent_ids)


__all__ = ["DailyHeadService"]
