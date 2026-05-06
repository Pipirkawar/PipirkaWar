"""Use-case `RequestDailyHead` (Спринт 2.3.C, button-trigger).

Игрок нажал кнопку «🎲 Назначить главу дня» / ввёл `/clan_head` в
клан-чате. Use-case (всё внутри одного `IUnitOfWork`):

1. Резолвит клан по `chat_id`. Нет — `IntegrityError` (handler 2.3.E
   делает preflight-проверку и рендерит «not-registered», так что в
   норме сюда мы заходим только с зарегистрированным чатом).
2. Если `clan.is_frozen` — `ClanFrozenError` (frozen-кланы не
   получают триггер главы — ПД 2.3.8).
3. Зовёт общий хелпер `_resolve_or_create_assignment(...,
   source=BUTTON, actor_tg_id=...)` (см. `application/daily_head/_common.py`).
4. Возвращает `DailyHeadResolved` для рендера ответного сообщения
   handler-ом 2.3.E (карточка-розыгрыш или «уже назначена»).

Идемпотентен по `(clan_id, moscow_date)`: повторное нажатие в те же
сутки → `was_new=False`, без новых side-effects.
"""

from __future__ import annotations

from pipirik_wars.application.daily_head._common import (
    _resolve_or_create_assignment,
)
from pipirik_wars.application.daily_head.dto import DailyHeadResolved
from pipirik_wars.application.dto.inputs import RequestDailyHeadInput
from pipirik_wars.domain.clan import ClanFrozenError, IClanRepository
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


class RequestDailyHead:
    """Use-case button-триггера «Главы клана дня»."""

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

    async def execute(self, input_dto: RequestDailyHeadInput) -> DailyHeadResolved:
        """Назначить главу клана дня по button-триггеру.

        :raises IntegrityError: если клана с таким `chat_id` нет
            в `clans` (в норме handler делает preflight).
        :raises ClanFrozenError: если клан заморожен.
        :raises DailyHeadInsufficientActivityError: если в клане
            меньше `min_active_members` активных за `active_within_days`.
        """
        async with self._uow:
            clan = await self._clans.get_by_chat_id(input_dto.chat_id)
            if clan is None:
                raise IntegrityError(
                    f"chat_id={input_dto.chat_id} is not a registered clan",
                )
            if clan.is_frozen:
                raise ClanFrozenError(chat_id=clan.chat_id)
            assert clan.id is not None  # repo гарантирует id

            return await _resolve_or_create_assignment(
                clan_id=clan.id,
                source=DailyHeadSource.BUTTON,
                actor_tg_id=input_dto.actor_tg_id,
                daily_head_service=self._daily_head_service,
                heads=self._heads,
                players=self._players,
                length_granter=self._length_granter,
                audit=self._audit,
                clock=self._clock,
            )


__all__ = ["RequestDailyHead"]
