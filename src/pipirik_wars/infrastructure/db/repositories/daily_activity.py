"""Реализация `IDailyActivityRepository` поверх таблицы `daily_active` (Спринт 2.3.B)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import select

from pipirik_wars.domain.clan import ClanStatus
from pipirik_wars.domain.daily_head import IDailyActivityRepository
from pipirik_wars.domain.player import PlayerStatus
from pipirik_wars.domain.shared.ports import IClock
from pipirik_wars.infrastructure.db.models import (
    ClanMemberORM,
    ClanORM,
    DailyActiveORM,
    UserORM,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyDailyActivityRepository(IDailyActivityRepository):
    """`list_active_member_ids(*, clan_id, within_days)` через JOIN.

    «Активный участник клана за последние N дней по МСК» означает:

    1. Игрок состоит в `clan_members` указанного клана.
    2. Игрок имеет статус ``active`` (не frozen / banned).
    3. Клан имеет статус ``active`` (frozen-клан вообще не получает
       триггер главы дня — см. ПД задача 2.3.8).
    4. Существует запись в ``daily_active`` с ``date`` в окне
       ``[clock.moscow_date() - (within_days - 1), clock.moscow_date()]``
       (включительно — «сегодня и предыдущие N-1 дней»).

    Именно этот фильтр обеспечивает «не выбираем главу из неактивных»
    (ПД задача 2.3.7). Запись в `daily_active` делает middleware
    (Спринт 2.3.E) на каждое сообщение от игрока.

    `IClock` инъектится в конструктор — реализация сама знает «сегодня
    по МСК», вызывающему доменному сервису не нужно прокидывать `as_of`
    параметром (порт намеренно его не имеет, см. контракт
    `IDailyActivityRepository`). Альтернатива (вызывать
    `func.current_date()` в SQL) была бы привязана к TZ-сессии БД,
    что хрупко.
    """

    __slots__ = ("_clock", "_uow")

    def __init__(self, *, uow: SqlAlchemyUnitOfWork, clock: IClock) -> None:
        self._uow = uow
        self._clock = clock

    async def list_active_member_ids(
        self,
        *,
        clan_id: int,
        within_days: int,
    ) -> Sequence[int]:
        if within_days < 1:
            raise ValueError(f"within_days must be >= 1, got {within_days}")
        # Окно: [today - (within_days - 1) ... today] включительно.
        # Пример: within_days=7, today=2026-05-06 → дни 2026-04-30..2026-05-06.
        as_of = self._clock.moscow_date()
        window_start = as_of - timedelta(days=within_days - 1)
        stmt = (
            select(UserORM.id)
            .distinct()
            .join(ClanMemberORM, ClanMemberORM.player_id == UserORM.id)
            .join(ClanORM, ClanORM.id == ClanMemberORM.clan_id)
            .join(DailyActiveORM, DailyActiveORM.user_id == UserORM.id)
            .where(
                ClanMemberORM.clan_id == clan_id,
                ClanORM.status == ClanStatus.ACTIVE.value,
                UserORM.status == PlayerStatus.ACTIVE.value,
                DailyActiveORM.date >= window_start,
                DailyActiveORM.date <= as_of,
            )
            .order_by(UserORM.id.asc())
        )
        result = await self._uow.session.execute(stmt)
        return tuple(int(row.id) for row in result.all())
