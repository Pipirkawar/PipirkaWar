"""Use-case `RunDailyHeadCron` (Спринт 2.3.C, cron-trigger).

APScheduler в `random_offset(0..24h)`-час с 00:00 МСК (Спринт 2.3.F)
зовёт этот use-case по каждому `clan_id`. Use-case (всё внутри одного
`IUnitOfWork`):

1. Резолвит клан по `clan_id` (внутренний id; шедулер уже знает его).
   Нет — `IntegrityError` (бывший клан удалён, но шедулер не успел
   снять job — bias to safe no-op через ошибку, шедулер логирует).
2. Если `clan.is_frozen` — тихий `return` без побочных эффектов
   (frozen-клан не должен получать главу; не нужно бросать ошибку,
   потому что cron — это автомат, а не пользовательский ввод).
3. Зовёт общий хелпер `_resolve_or_create_assignment(...,
   source=CRON, actor_tg_id=None)` (см. `_common.py`).
4. Возвращает `DailyHeadResolved` (с `was_new=True` если впервые
   за день, иначе `False` — кнопка успела раньше).

Идемпотентен по `(clan_id, moscow_date)`: если кнопка уже сработала
раньше cron-а, мы корректно вернём существующего главу без новых
side-effects.

Cron-callback в шедулере (2.3.F) поглощает все исключения через
try/except (как обычно для job-callback-ов APScheduler), так что
`DailyHeadInsufficientActivityError` тут логируется и не падает шедулер.
"""

from __future__ import annotations

from pipirik_wars.application.daily_head._common import (
    _resolve_or_create_assignment,
)
from pipirik_wars.application.daily_head.dto import DailyHeadResolved
from pipirik_wars.application.dto.inputs import RunDailyHeadCronInput
from pipirik_wars.domain.clan import IClanRepository
from pipirik_wars.domain.daily_head import (
    DailyHeadService,
    DailyHeadSource,
    IDailyHeadRepository,
)
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork
from pipirik_wars.domain.shared.ports.audit import IAuditLogger
from pipirik_wars.shared.errors import IntegrityError


class RunDailyHeadCron:
    """Use-case cron-триггера «Главы клана дня»."""

    __slots__ = (
        "_audit",
        "_clans",
        "_clock",
        "_daily_head_service",
        "_heads",
        "_length_granter",
        "_players",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        clans: IClanRepository,
        players: IPlayerRepository,
        heads: IDailyHeadRepository,
        daily_head_service: DailyHeadService,
        length_granter: ILengthGranter,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._clans = clans
        self._players = players
        self._heads = heads
        self._daily_head_service = daily_head_service
        self._length_granter = length_granter
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: RunDailyHeadCronInput) -> DailyHeadResolved | None:
        """Назначить главу клана дня по cron-триггеру.

        Возвращает `None`, если клан заморожен — это **не ошибка**, а
        ожидаемый no-op для frozen-кланов в фоновом cron-режиме. Все
        остальные ситуации (не зарегистрирован, недостаточно активных)
        — исключения, которые шедулер логирует и поглощает.

        :raises IntegrityError: если клана с таким `clan_id` нет в `clans`.
        :raises DailyHeadInsufficientActivityError: если в клане
            меньше `min_active_members` активных.
        """
        async with self._uow:
            clan = await self._clans.get_by_id(input_dto.clan_id)
            if clan is None:
                raise IntegrityError(
                    f"clan_id={input_dto.clan_id} not found",
                )
            if clan.is_frozen:
                return None
            assert clan.id is not None  # repo гарантирует id

            return await _resolve_or_create_assignment(
                clan_id=clan.id,
                source=DailyHeadSource.CRON,
                actor_tg_id=None,
                daily_head_service=self._daily_head_service,
                heads=self._heads,
                players=self._players,
                length_granter=self._length_granter,
                audit=self._audit,
                clock=self._clock,
            )


__all__ = ["RunDailyHeadCron"]
