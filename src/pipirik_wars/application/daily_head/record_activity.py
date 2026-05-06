"""Use-case `RecordPlayerActivity` (Спринт 2.3.F.1).

Bot-middleware `DailyActivityMiddleware` зовёт этот use-case на каждое
входящее Telegram-сообщение от игрока в групповом чате клана. Use-case
делает lookup игрока по `tg_user_id` через `IPlayerRepository.get_by_tg_id`:

- если игрок не зарегистрирован (`get_by_tg_id` вернул `None`) — тихий
  no-op без ошибки (новый пользователь напишет в чат до того, как пройдёт
  через `/start`-onboarding — это нормально);
- если игрок есть, но в статусе `FROZEN` или `BANNED` — тоже no-op
  (`list_active_member_ids` всё равно отфильтрует таких игроков, так
  что писать запись бесполезно);
- иначе — `daily_activity.record_active(user_id, last_at, moscow_date)`
  с временем по `IClock`.

Всё внутри одного `IUnitOfWork`-а. Ошибки записи в `daily_active`
пробрасываются наверх — middleware ловит их и логирует, но не падает
команду пользователя (см. `DailyActivityMiddleware`).
"""

from __future__ import annotations

from pipirik_wars.application.dto.inputs import RecordPlayerActivityInput
from pipirik_wars.domain.daily_head import IDailyActivityRepository
from pipirik_wars.domain.player import IPlayerRepository, PlayerStatus
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


class RecordPlayerActivity:
    """Use-case записи активности игрока в `daily_active`."""

    __slots__ = ("_clock", "_daily_activity", "_players", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        daily_activity: IDailyActivityRepository,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._daily_activity = daily_activity
        self._clock = clock

    async def execute(self, input_dto: RecordPlayerActivityInput) -> bool:
        """Записать активность игрока. Возвращает `True`, если запись была.

        - `False` означает no-op (игрок не зарегистрирован / заморожен /
          забанен) — middleware просто пропускает результат.
        - `True` означает, что был сделан UPSERT в `daily_active`.
        """
        async with self._uow:
            player = await self._players.get_by_tg_id(input_dto.tg_user_id)
            if player is None or player.id is None:
                return False
            if player.status is not PlayerStatus.ACTIVE:
                return False

            await self._daily_activity.record_active(
                user_id=player.id,
                last_at=self._clock.now(),
                moscow_date=self._clock.moscow_date(),
            )
            return True


__all__ = ["RecordPlayerActivity"]
