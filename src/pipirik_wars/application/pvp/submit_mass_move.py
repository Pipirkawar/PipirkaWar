"""Use-case `SubmitMassMove` (Спринт 2.2.E, ГДД §7.2).

Игрок отправляет ход (атака+блок) в активном массовом бое:

1. Загружает `MassDuel`. Нет — `MassDuelNotFoundError`.
2. Загружает `Player` отправителя по `tg_id`. Нет — `PlayerNotFoundError`.
3. `MassDuel.submit_move(player_id, choice, now)` — доменный мутатор:
   * валидирует `state == IN_PROGRESS`, `is_participant`, отсутствие
     повторного выбора (`MassMoveAlreadySubmittedError`).
4. `IMassDuelRepository.save(...)` — атомарный коммит изменений.

В отличие от 1×1-`SubmitMove` use-case **не резолвит** бой при
последнем submit-е. Резолв — отдельный `ResolveMassDuel` use-case,
который вызывается:

* шедулером — по таймеру боя (Спринт 2.2.F);
* handler-ом — если он сам видит `is_ready_to_resolve` и хочет
  немедленно разрешить.

Транзакция — ambient `IUnitOfWork`. Доменные ошибки (`InvalidMassDuelStateError`,
`NotAMassDuelParticipantError`, `MassMoveAlreadySubmittedError`)
пробрасываются — handler сам решает, что показать пользователю.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import SubmitMassMoveInput
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.pvp import (
    IMassDuelRepository,
    MassDuel,
    MassDuelNotFoundError,
    MassRoundChoice,
    Position,
)
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


@dataclass(frozen=True, slots=True)
class MassMoveSubmitted:
    """Результат отправки хода в массовом бою."""

    duel: MassDuel
    is_ready_to_resolve: bool
    """True — все участники отправили выбор, можно звать `ResolveMassDuel`."""


class SubmitMassMove:
    """Use-case «отправить ход в массовом PvP-бою»."""

    __slots__ = (
        "_clock",
        "_duels",
        "_players",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        duels: IMassDuelRepository,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._duels = duels
        self._clock = clock

    async def execute(self, input_dto: SubmitMassMoveInput) -> MassMoveSubmitted:
        """Отправить ход. Бросает:

        - `MassDuelNotFoundError` — боя с таким `duel_id` нет;
        - `PlayerNotFoundError` — отправителя нет в БД;
        - `InvalidMassDuelStateError` — бой не в `IN_PROGRESS`;
        - `NotAMassDuelParticipantError` — игрок не участник боя;
        - `MassMoveAlreadySubmittedError` — игрок уже отправил выбор.
        """

        async with self._uow:
            duel = await self._duels.get_by_id(duel_id=input_dto.duel_id)
            if duel is None:
                raise MassDuelNotFoundError(duel_id=input_dto.duel_id)

            mover = await self._fetch_player(tg_id=input_dto.tg_id)
            mover_id = self._require_id(mover)
            now = self._clock.now()

            choice = MassRoundChoice(
                player_id=mover_id,
                attack=Position(input_dto.attack),
                block=Position(input_dto.block),
            )
            mutated = duel.submit_move(
                player_id=mover_id,
                choice=choice,
                now=now,
            )
            saved = await self._duels.save(mutated)
            return MassMoveSubmitted(
                duel=saved,
                is_ready_to_resolve=saved.is_ready_to_resolve,
            )

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
    "MassMoveSubmitted",
    "SubmitMassMove",
]
