"""Use-case `LeaveCaravanLobby` (Спринт 3.2-B, ГДД §9.3).

Игрок жмёт «Выйти» в лобби каравана:

1. Открывается ambient-`IUnitOfWork`.
2. Резолвится караван (`ICaravanRepository.get_by_id`):
   - не найден → `CaravanNotFoundError`;
   - `status != LOBBY` → `CaravanLobbyClosedError` (после старта боя
     выход уже невозможен).
3. Резолвится игрок (`IPlayerRepository.get_by_tg_id`):
   - не найден → `PlayerNotFoundError`.
4. Игрок должен быть участником этого каравана — иначе
   `CaravanRoleConflictError(reason="player is not a participant")`.
5. Лидер выйти не может (нужно отменять весь караван через
   `CancelCaravanLobby` — Спринт 3.2-C). Попытка лидера → `CaravanRoleConflictError`.
6. `ICaravanParticipantRepository.remove(caravan_id, player_id)`.
7. Снимается `activity_lock(player, CARAVAN)` (NO-OP при отсутствии).
8. Audit `CARAVAN_PLAYER_LEFT` (idempotency-key
   `caravan_player_left:{caravan_id}:{player_id}:{joined_at_iso}`).
9. Возвращается `LeftCaravanLobby(caravan, returned_contribution_cm=...)`.

ВАЖНО: `contribution_cm` НЕ возвращается обратно в длину игрока,
потому что списание длины происходит только в момент `LOBBY → IN_BATTLE`
(Спринт 3.2-C). На стадии лобби длина игрока ещё не списана.
Поле `returned_contribution_cm` в результате — для bot-handler-а
(в 3.2-D), чтобы показать «вы вышли, ваш потенциальный взнос: X см».
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import LeaveCaravanLobbyInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanLobbyClosedError,
    CaravanNotFoundError,
    CaravanParticipant,
    CaravanRoleConflictError,
    ICaravanParticipantRepository,
    ICaravanRepository,
)
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class LeftCaravanLobby:
    """Результат успешного `LeaveCaravanLobby`."""

    caravan: Caravan
    removed_participant: CaravanParticipant
    returned_contribution_cm: int


class LeaveCaravanLobby:
    """Use-case «игрок вышел из лобби каравана» (ГДД §9.3)."""

    __slots__ = (
        "_audit",
        "_caravan_participants",
        "_caravans",
        "_clock",
        "_locks",
        "_players",
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
    ) -> None:
        self._uow = uow
        self._caravans = caravans
        self._caravan_participants = caravan_participants
        self._players = players
        self._locks = locks
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: LeaveCaravanLobbyInput) -> LeftCaravanLobby:
        """Выйти из лобби каравана. См. docstring модуля для контракта."""
        async with self._uow:
            now = self._clock.now()

            caravan = await self._fetch_caravan(caravan_id=input_dto.caravan_id)
            self._ensure_lobby(caravan=caravan)

            player = await self._fetch_player(tg_id=input_dto.tg_id)
            assert player.id is not None

            participant = await self._fetch_participant(
                caravan_id=caravan.id,  # type: ignore[arg-type]
                player_id=player.id,
            )
            self._ensure_not_leader(participant=participant)

            await self._caravan_participants.remove(
                caravan_id=caravan.id,  # type: ignore[arg-type]
                player_id=player.id,
            )
            await self._locks.release(
                actor_kind="player",
                actor_id=player.id,
            )

            returned_cm = participant.contribution.cm if participant.contribution is not None else 0

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.CARAVAN_PLAYER_LEFT,
                    actor_id=player.tg_id,
                    target_kind="caravan",
                    target_id=str(caravan.id),
                    before={
                        "role": participant.role.value,
                        "contribution_cm": returned_cm,
                        "is_leader": participant.is_leader,
                    },
                    after=None,
                    reason="caravan_player_left",
                    idempotency_key=(
                        f"caravan_player_left:{caravan.id}:{player.id}:"
                        f"{participant.joined_at.isoformat()}"
                    ),
                    occurred_at=now,
                )
            )

        return LeftCaravanLobby(
            caravan=caravan,
            removed_participant=participant,
            returned_contribution_cm=returned_cm,
        )

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
        if not caravan.is_in_lobby:
            assert caravan.id is not None
            raise CaravanLobbyClosedError(
                caravan_id=caravan.id,
                status=caravan.status.value,
            )

    async def _fetch_player(self, *, tg_id: int) -> Player:
        player = await self._players.get_by_tg_id(tg_id)
        if player is None:
            raise PlayerNotFoundError(tg_id=tg_id)
        return player

    async def _fetch_participant(
        self,
        *,
        caravan_id: int,
        player_id: int,
    ) -> CaravanParticipant:
        existing = await self._caravan_participants.list_by_caravan(
            caravan_id=caravan_id,
        )
        for participant in existing:
            if participant.player_id == player_id:
                return participant
        raise CaravanRoleConflictError(
            player_id=player_id,
            attempted_role="leave",
            reason=f"player is not a participant of caravan_id={caravan_id}",
        )

    @staticmethod
    def _ensure_not_leader(*, participant: CaravanParticipant) -> None:
        if participant.is_leader:
            raise CaravanRoleConflictError(
                player_id=participant.player_id,
                attempted_role="leave",
                reason="leader cannot leave the lobby; cancel the caravan instead",
            )


__all__ = [
    "LeaveCaravanLobby",
    "LeftCaravanLobby",
]
