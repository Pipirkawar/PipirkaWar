"""Use-case `CancelDuel` (Спринт 2.1.D, ГДД §7.1).

Отмена pending-вызова до его принятия. Сценарии вызова:

* челленджер сам отменил («передумал», нажал кнопку «Отменить»);
* шедулер 2.1.F истёк TTL вызова (3 мин в чате / 10 мин в глобале)
  и зовёт `CancelDuel` для авто-отмены.

После принятия (`IN_PROGRESS`) и завершения (`COMPLETED` / уже
`CANCELLED`) — `Duel.cancel` бросает `InvalidDuelStateError` из домена.

Алгоритм:

1. Загружает `Duel`. Нет — `DuelNotFoundError`.
2. Загружает `Player` по `tg_id` инициатора отмены.
3. Проверяет, что инициатор — `challenger_id` (только челленджер
   может отменить свой вызов до accept-а). Иначе —
   `NotADuelParticipantError`. Системный шедулер передаёт `tg_id`
   челленджера автоматически.
4. `Duel.cancel(now=...)` (идемпотентно для уже `CANCELLED`).
5. `IDuelRepository.save(...)`.
6. Снимает activity-lock челленджера (`ActivityLockService.release`).
7. Audit `PVP_DUEL_CANCELLED`.

Транзакция — ambient `IUnitOfWork`. Если кто-то одновременно принял
дуэль (race), то на шаге 4 `Duel.cancel` бросит `InvalidDuelStateError`,
транзакция откатится — лок останется на челленджере (для
продолжающейся теперь IN_PROGRESS-дуэли).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import CancelDuelInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelNotFoundError,
    DuelState,
    IDuelRepository,
    NotADuelParticipantError,
)
from pipirik_wars.domain.pvp.lobby import IGlobalLobbyRepository
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class DuelCancelled:
    """Результат отмены вызова."""

    duel: Duel
    was_already_cancelled: bool


class CancelDuel:
    """Use-case «отменить pending PvP-вызов»."""

    __slots__ = (
        "_audit",
        "_clock",
        "_duels",
        "_lobby",
        "_locks",
        "_players",
        "_scheduler",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        duels: IDuelRepository,
        locks: ActivityLockService,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler | None = None,
        lobby: IGlobalLobbyRepository | None = None,
    ) -> None:
        self._uow = uow
        self._players = players
        self._duels = duels
        self._locks = locks
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler
        self._lobby = lobby

    async def execute(self, input_dto: CancelDuelInput) -> DuelCancelled:
        """Отменить вызов. Бросает:

        - `DuelNotFoundError` — дуэли с таким `duel_id` нет;
        - `PlayerNotFoundError` — игрока с таким `tg_id` нет;
        - `NotADuelParticipantError` — отменяющий не челленджер;
        - `InvalidDuelStateError` — дуэль уже принята/завершена.
        """

        async with self._uow:
            duel = await self._duels.get_by_id(duel_id=input_dto.duel_id)
            if duel is None:
                raise DuelNotFoundError(duel_id=input_dto.duel_id)

            canceller = await self._fetch_player(tg_id=input_dto.tg_id)
            canceller_id = self._require_id(canceller)
            if canceller_id != duel.challenger_id:
                raise NotADuelParticipantError(player_id=canceller_id)

            if duel.state is DuelState.CANCELLED:
                return DuelCancelled(duel=duel, was_already_cancelled=True)

            now = self._clock.now()
            cancelled = duel.cancel(now=now)
            saved = await self._duels.save(cancelled)

            await self._locks.release(
                actor_kind="player",
                actor_id=duel.challenger_id,
            )

            assert saved.id is not None
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PVP_DUEL_CANCELLED,
                    actor_id=canceller.tg_id,
                    target_kind="pvp_duel",
                    target_id=str(saved.id),
                    before={"state": duel.state.value},
                    after={"state": saved.state.value},
                    reason="pvp_duel_cancelled",
                    idempotency_key=f"pvp_duel_cancelled:{saved.id}",
                    occurred_at=now,
                )
            )

            duel_id_for_cleanup = saved.id
            mode_was_chat_then_global = duel.mode is DuelMode.CHAT_THEN_GLOBAL
            mode_was_global_only = duel.mode is DuelMode.GLOBAL_ONLY
            # удаляем запись из лобби, если была (для GLOBAL_ONLY).
            if self._lobby is not None and mode_was_global_only:
                await self._lobby.remove(duel_id=duel_id_for_cleanup)

        # Снимаем scheduled-job-ы вне UoW (idempotent).
        if self._scheduler is not None:
            if mode_was_chat_then_global:
                await self._scheduler.cancel_chat_to_global_escalation(
                    duel_id=duel_id_for_cleanup,
                )
            elif mode_was_global_only:
                await self._scheduler.cancel_global_lobby_expiration(
                    duel_id=duel_id_for_cleanup,
                )
        return DuelCancelled(duel=saved, was_already_cancelled=False)

    async def _fetch_player(self, *, tg_id: int) -> Player:
        player = await self._players.get_by_tg_id(tg_id)
        if player is None:
            raise PlayerNotFoundError(tg_id=tg_id)
        return player

    @staticmethod
    def _require_id(player: Player) -> int:
        if player.id is None:
            raise RuntimeError(
                f"Player tg_id={player.tg_id} loaded without id; repository contract violation",
            )
        return player.id


__all__ = [
    "CancelDuel",
    "DuelCancelled",
]
