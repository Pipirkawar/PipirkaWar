"""Use-case `CancelCaravan` (Спринт 3.2-D, ГДД §9.3).

Лидер каравана нажал «Отменить караван» в лобби:

1. Открывается ambient-`IUnitOfWork` (всё ниже — в одной транзакции).
2. Резолвится караван (`ICaravanRepository.get_by_id`):
   - не найден → :class:`CaravanNotFoundError`;
   - `status == CANCELLED` → идемпотентный no-op
     (`CaravanCancelled(was_already_cancelled=True)`);
   - `status in {IN_BATTLE, FINISHED}` → :class:`InvalidCaravanStateError`
     (отмена возможна только из `LOBBY`).
3. Резолвится игрок (`IPlayerRepository.get_by_tg_id`):
   - не найден → :class:`PlayerNotFoundError`.
4. Сверка лидерства: `caravan.leader_player_id == player.id`.
   - не лидер → :class:`CaravanRoleConflictError(attempted_role="cancel")`.
5. `Caravan.mark_cancelled(cancelled_at=now)` + `ICaravanRepository.save`.
6. Снимаются `activity_lock(player, CARAVAN)` для **всех** участников
   (включая лидера). Идемпотентно: NO-OP, если лок уже снят.
7. Отзывается APScheduler-job:
   `IDelayedJobScheduler.cancel_caravan_lobby_close(caravan_id)`.
   Battle-finish-job ещё не запланирован — его ставит
   `CloseCaravanLobby` при переходе `LOBBY → IN_BATTLE` (Спринт 3.2-C).
   На случай race-а (lobby-close-callback успел перевести в `IN_BATTLE`
   между шагами 2 и 5) шаг 2 ловится `InvalidCaravanStateError`-ом.
8. Audit `CARAVAN_CANCELLED` (idempotency-key `caravan_cancelled:{caravan_id}`).
9. Возвращается `CaravanCancelled`.

Длины игроков НЕ восстанавливаются — на этапе лобби они и не
списывались (списание происходит только в `FinishCaravanBattle`,
Спринт 3.2-C).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import CancelCaravanInput
from pipirik_wars.application.observability import IBusinessMetrics, NullBusinessMetrics
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanNotFoundError,
    CaravanParticipant,
    CaravanRoleConflictError,
    CaravanStatus,
    ICaravanParticipantRepository,
    ICaravanRepository,
    InvalidCaravanStateError,
)
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class CaravanCancelled:
    """Результат `CancelCaravan`.

    `was_already_cancelled=True` — повторный вызов на уже-`CANCELLED`
    караване (no-op, аудит не писался, локи и job не трогались).
    """

    caravan: Caravan
    was_already_cancelled: bool


class CancelCaravan:
    """Use-case «лидер отменяет караван из лобби» (ГДД §9.3)."""

    __slots__ = (
        "_audit",
        "_business_metrics",
        "_caravan_participants",
        "_caravans",
        "_clock",
        "_locks",
        "_players",
        "_scheduler",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        caravans: ICaravanRepository,
        caravan_participants: ICaravanParticipantRepository,
        players: IPlayerRepository,
        locks: ActivityLockService,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler,
        business_metrics: IBusinessMetrics | None = None,
    ) -> None:
        self._uow = uow
        self._caravans = caravans
        self._caravan_participants = caravan_participants
        self._players = players
        self._locks = locks
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler
        self._business_metrics: IBusinessMetrics = business_metrics or NullBusinessMetrics()

    async def execute(self, input_dto: CancelCaravanInput) -> CaravanCancelled:
        """Отменить караван. См. docstring модуля для контракта."""
        async with self._uow:
            now = self._clock.now()

            caravan = await self._fetch_caravan(caravan_id=input_dto.caravan_id)

            if caravan.status is CaravanStatus.CANCELLED:
                return CaravanCancelled(caravan=caravan, was_already_cancelled=True)
            self._ensure_lobby(caravan=caravan)

            player = await self._fetch_player(tg_id=input_dto.tg_id)
            assert player.id is not None
            self._ensure_leader(caravan=caravan, player=player)

            cancelled = caravan.mark_cancelled(cancelled_at=now)
            saved = await self._caravans.save(cancelled)
            assert saved.id is not None

            participants = await self._caravan_participants.list_by_caravan(
                caravan_id=saved.id,
            )
            await self._release_locks(participants=participants)

            await self._scheduler.cancel_caravan_lobby_close(caravan_id=saved.id)

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.CARAVAN_CANCELLED,
                    actor_id=player.tg_id,
                    target_kind="caravan",
                    target_id=str(saved.id),
                    before={"status": caravan.status.value},
                    after={
                        "status": saved.status.value,
                        "cancelled_at": now.isoformat(),
                        "participants_count": len(participants),
                    },
                    reason="caravan_cancelled_by_leader",
                    idempotency_key=f"caravan_cancelled:{saved.id}",
                    occurred_at=now,
                )
            )

        self._business_metrics.dec_caravan_active()
        self._business_metrics.inc_caravan_outcome("cancelled")
        return CaravanCancelled(caravan=saved, was_already_cancelled=False)

    # -------- helpers --------

    async def _fetch_caravan(self, *, caravan_id: int) -> Caravan:
        caravan = await self._caravans.get_by_id(caravan_id=caravan_id)
        if caravan is None:
            raise CaravanNotFoundError(caravan_id=caravan_id)
        if caravan.id is None:  # pragma: no cover — защитный invariant
            raise RuntimeError("caravan loaded without id; repository contract violation")
        return caravan

    @staticmethod
    def _ensure_lobby(*, caravan: Caravan) -> None:
        if caravan.status is CaravanStatus.LOBBY:
            return
        assert caravan.id is not None
        raise InvalidCaravanStateError(
            caravan_id=caravan.id,
            expected=CaravanStatus.LOBBY.value,
            actual=caravan.status.value,
        )

    async def _fetch_player(self, *, tg_id: int) -> Player:
        player = await self._players.get_by_tg_id(tg_id)
        if player is None:
            raise PlayerNotFoundError(tg_id=tg_id)
        return player

    @staticmethod
    def _ensure_leader(*, caravan: Caravan, player: Player) -> None:
        assert player.id is not None
        if caravan.leader_player_id != player.id:
            raise CaravanRoleConflictError(
                player_id=player.id,
                attempted_role="cancel",
                reason=(
                    f"only leader (player_id={caravan.leader_player_id}) "
                    f"can cancel caravan, got player_id={player.id}"
                ),
            )

    async def _release_locks(self, *, participants: tuple[CaravanParticipant, ...]) -> None:
        for participant in participants:
            await self._locks.release(
                actor_kind="player",
                actor_id=participant.player_id,
            )


__all__ = [
    "CancelCaravan",
    "CaravanCancelled",
]
