"""Use-case `SubmitMove` (Спринт 2.1.D, ГДД §7.1).

Игрок отправляет ход (атака+блок) в активной дуэли:

1. Загружает `Duel`. Нет — `DuelNotFoundError`.
2. Загружает `Player` отправителя (по `tg_id`). Нет — `PlayerNotFoundError`.
3. `Duel.submit_move(player_id, choice, now)` — доменный мутатор:
   * валидирует `state == IN_PROGRESS`, `is_participant`, отсутствие
     повторного выбора (`MoveAlreadySubmittedError`);
   * если этим вызовом раунд закрылся (оба выбрали) — авторазрешает
     раунд через `_resolve_pending_round` (внутри домена), сдвигает
     либо к следующему раунду, либо в `COMPLETED`.
4. `IDuelRepository.save(...)` — единый коммит изменений.
5. Если состояние перешло в `COMPLETED` (это был последний раунд) —
   зовёт `apply_duel_outcome(...)`:
   * прибавка победителю через `ILengthGranter.grant(source=PVP_REWARD)`
     с anti-cheat-cap-ом из 1.6;
   * списание проигравшему — прямой `with_length` + audit `LENGTH_REVOKE`.
6. Если COMPLETED — снимает activity-locks обоих игроков и пишет
   audit `PVP_DUEL_COMPLETED` со снимком итога.

Транзакция — ambient `IUnitOfWork`. Если apply_outcome бросает
`AnticheatSoftBanError` (например, кто-то получил soft-ban между
ходами через cap-trip-wire), вся транзакция откатывается — дуэль
остаётся в IN_PROGRESS на предыдущем шаге, без частичного
mutate-state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pipirik_wars.application.dto.inputs import SubmitMoveInput
from pipirik_wars.application.observability import (
    DuelResolvedOutcome,
    IBusinessMetrics,
    NullBusinessMetrics,
)
from pipirik_wars.application.pvp.apply_outcome import apply_duel_outcome
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.pvp import (
    Duel,
    DuelNotFoundError,
    DuelWinner,
    IDuelRepository,
    Position,
    RoundChoice,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class MoveSubmitted:
    """Результат отправки хода."""

    duel: Duel
    duel_completed: bool


class SubmitMove:
    """Use-case «отправить ход в PvP-дуэли»."""

    __slots__ = (
        "_audit",
        "_balance",
        "_business_metrics",
        "_clock",
        "_duels",
        "_length_granter",
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
        length_granter: ILengthGranter,
        audit: IAuditLogger,
        clock: IClock,
        balance: IBalanceConfig | None = None,
        scheduler: IDelayedJobScheduler | None = None,
        business_metrics: IBusinessMetrics | None = None,
    ) -> None:
        self._uow = uow
        self._players = players
        self._duels = duels
        self._locks = locks
        self._length_granter = length_granter
        self._audit = audit
        self._clock = clock
        self._balance = balance
        self._scheduler = scheduler
        self._business_metrics: IBusinessMetrics = business_metrics or NullBusinessMetrics()

    async def execute(self, input_dto: SubmitMoveInput) -> MoveSubmitted:
        """Отправить ход. Бросает:

        - `DuelNotFoundError` — дуэли с таким `duel_id` нет;
        - `PlayerNotFoundError` — отправителя нет в БД;
        - `InvalidDuelStateError` — дуэль не в `IN_PROGRESS`;
        - `NotADuelParticipantError` — игрок не участник дуэли;
        - `MoveAlreadySubmittedError` — игрок уже выбрал в этом раунде;
        - `AnticheatSoftBanError` — кто-то из игроков влетел в soft-ban
          (только при apply_outcome, при `duel_completed=True`).
        """

        async with self._uow:
            duel = await self._duels.get_by_id(duel_id=input_dto.duel_id)
            if duel is None:
                raise DuelNotFoundError(duel_id=input_dto.duel_id)

            mover = await self._fetch_player(tg_id=input_dto.tg_id)
            now = self._clock.now()

            choice = RoundChoice(
                attack=Position(input_dto.attack),
                block=Position(input_dto.block),
            )
            # Снимок `pending_round.round_num` до мутации: если этим
            # вызовом раунд закрывается, нужно будет отменить AFK-таймер
            # этого именно раунда (значение будет использовано снаружи UoW).
            prev_round_num = duel.pending_round.round_num if duel.pending_round else None

            mutated = duel.submit_move(
                player_id=self._require_id(mover),
                choice=choice,
                now=now,
            )
            saved = await self._duels.save(mutated)

            if not saved.is_completed:
                duel_completed = False
            else:
                await apply_duel_outcome(
                    duel=saved,
                    players=self._players,
                    length_granter=self._length_granter,
                    audit=self._audit,
                    now=now,
                )
                await self._release_locks(saved)
                await self._audit_completed(duel=saved, now=now)
                duel_completed = True
                self._business_metrics.inc_duel_resolved(_duel_outcome_label(saved))

        # AFK-таймер раунда — снаружи UoW (идемпотентные операции
        # шедулера). Алгоритм (Спринт 2.1.G):
        # * раунд не закрылся (тот же round_num после mutate) — nothing;
        # * раунд закрылся, дуэль в IN_PROGRESS — cancel предыдущий + schedule новый;
        # * раунд закрылся, дуэль COMPLETED — cancel предыдущий, больше ничего.
        if self._scheduler is not None and prev_round_num is not None:
            saved_round_num = saved.pending_round.round_num if saved.pending_round else None
            round_closed = saved_round_num != prev_round_num
            if round_closed:
                assert saved.id is not None
                await self._scheduler.cancel_round_afk_resolution(
                    duel_id=saved.id,
                    round_num=prev_round_num,
                )
                if not duel_completed and saved_round_num is not None:
                    assert self._balance is not None  # scheduler+balance провязываются вместе
                    cfg = self._balance.get().pvp.duel_1v1
                    await self._scheduler.schedule_round_afk_resolution(
                        duel_id=saved.id,
                        round_num=saved_round_num,
                        run_at=now + timedelta(seconds=cfg.round_timer_seconds),
                    )
        return MoveSubmitted(duel=saved, duel_completed=duel_completed)

    async def _release_locks(self, duel: Duel) -> None:
        # challenger всегда задан, challenged_id выставлен при `accept`-е
        # — оба ID валидны на момент COMPLETED.
        assert duel.challenged_id is not None
        await self._locks.release(
            actor_kind="player",
            actor_id=duel.challenger_id,
        )
        await self._locks.release(
            actor_kind="player",
            actor_id=duel.challenged_id,
        )

    async def _audit_completed(self, *, duel: Duel, now: datetime) -> None:
        outcome = duel.final_outcome
        assert outcome is not None
        assert duel.id is not None
        await self._audit.record(
            AuditEntry(
                action=AuditAction.PVP_DUEL_COMPLETED,
                actor_id=None,  # системное событие, не действие игрока
                target_kind="pvp_duel",
                target_id=str(duel.id),
                before=None,
                after={
                    "winner": outcome.winner.value,
                    "p1_total_dealt": outcome.p1_total_dealt,
                    "p2_total_dealt": outcome.p2_total_dealt,
                    "p1_delta_cm": outcome.p1_delta_cm,
                    "p2_delta_cm": outcome.p2_delta_cm,
                },
                reason="pvp_duel_completed",
                idempotency_key=f"pvp_duel_completed:{duel.id}",
                occurred_at=now,
            )
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


def _duel_outcome_label(duel: Duel) -> DuelResolvedOutcome:
    """Маппинг `DuelWinner` -> метрика-label для `SubmitMove`-резолва.

    В этой ветке (не AFK) фактический победитель определяется суммой
    нанесённого урона — поэтому метрика отражает чистый исход, без
    маркировки AFK.
    """
    outcome = duel.final_outcome
    assert outcome is not None
    if outcome.winner is DuelWinner.P1:
        return "p1_win"
    if outcome.winner is DuelWinner.P2:
        return "p2_win"
    return "draw"


__all__ = [
    "MoveSubmitted",
    "SubmitMove",
]
