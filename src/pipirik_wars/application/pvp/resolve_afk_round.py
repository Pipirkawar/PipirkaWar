"""Use-case `ResolveAfkRound` (Спринт 2.1.D, ГДД §7.1).

AFK-фоллбэк раунда. Шедулер раунд-таймера (Спринт 2.1.G) вызывает
этот use-case по истечении 30–60 сек, если хотя бы один игрок не
отправил `submit_move`. Для каждого молчаливого игрока выбирается
случайный `RoundChoice(attack, block)` через `IRandom`, раунд
авто-разрешается через `Duel.force_complete_round`.

Алгоритм:

1. Загружает `Duel` по `duel_id`. Нет — `DuelNotFoundError`.
2. Сверяет `pending_round.round_num == input.round_num` —
   защита от устаревшего таймера (если кто-то уже отправил ход
   и раунд закрылся, шедулер мог не отменить таймер вовремя).
   Если не совпало или дуэль не в `IN_PROGRESS` — no-op (с пометкой
   в результате `was_already_resolved=True`).
3. Если оба игрока уже выбрали — no-op (то же).
4. Для отсутствующих сторон роллит `RoundChoice` через `IRandom.choice`.
5. `Duel.force_complete_round(p1_fallback, p2_fallback, now)`.
6. `IDuelRepository.save(...)`.
7. Если состояние перешло в `COMPLETED` (это был последний раунд) —
   `apply_duel_outcome(...)` (как в `SubmitMove`):
   * прибавка победителю через `ILengthGranter.grant(source=PVP_REWARD)`;
   * списание проигравшему — прямой `with_length` + audit `LENGTH_REVOKE`.
8. Если COMPLETED — снимает activity-locks обоих и audit
   `PVP_DUEL_COMPLETED`.

Транзакция — ambient `IUnitOfWork`. Любая ошибка (включая
`AnticheatSoftBanError` при apply_outcome) откатывает всё, дуэль
остаётся в IN_PROGRESS на предыдущем шаге.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pipirik_wars.application.dto.inputs import ResolveAfkRoundInput
from pipirik_wars.application.observability import (
    DuelResolvedOutcome,
    IBusinessMetrics,
    NullBusinessMetrics,
)
from pipirik_wars.application.pvp.apply_outcome import apply_duel_outcome
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import IPlayerRepository
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
    IRandom,
    IUnitOfWork,
)

# Все три позиции — единый pool для random.choice. Атака и блок
# независимы (даже если совпали — это валидный домен).
_POSITIONS: tuple[Position, ...] = (Position.HIGH, Position.MID, Position.LOW)


@dataclass(frozen=True, slots=True)
class AfkRoundResolved:
    """Результат AFK-фоллбэка."""

    duel: Duel
    duel_completed: bool
    was_already_resolved: bool
    """`True`, если шедулер опоздал — раунд уже закрыт реальными ходами."""


class ResolveAfkRound:
    """Use-case «AFK-таймер раунда: добить случайными выборами»."""

    __slots__ = (
        "_audit",
        "_balance",
        "_business_metrics",
        "_clock",
        "_duels",
        "_length_granter",
        "_locks",
        "_players",
        "_random",
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
        random: IRandom,
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
        self._random = random
        self._audit = audit
        self._clock = clock
        self._balance = balance
        self._scheduler = scheduler
        self._business_metrics: IBusinessMetrics = business_metrics or NullBusinessMetrics()

    async def execute(self, input_dto: ResolveAfkRoundInput) -> AfkRoundResolved:
        """AFK-резолв раунда. Бросает:

        - `DuelNotFoundError` — дуэли нет;
        - `AnticheatSoftBanError` — при apply_outcome (если кто-то
          получил soft-ban между ходами).

        Возвращает `was_already_resolved=True` без мутаций, если
        раунд уже закрыт (шедулер опоздал) — это идемпотентность.
        """

        async with self._uow:
            duel = await self._duels.get_by_id(duel_id=input_dto.duel_id)
            if duel is None:
                raise DuelNotFoundError(duel_id=input_dto.duel_id)

            if not duel.is_in_progress:
                return AfkRoundResolved(
                    duel=duel,
                    duel_completed=duel.is_completed,
                    was_already_resolved=True,
                )
            pending = duel.pending_round
            assert pending is not None  # инвариант IN_PROGRESS
            if pending.round_num != input_dto.round_num:
                return AfkRoundResolved(
                    duel=duel,
                    duel_completed=False,
                    was_already_resolved=True,
                )
            if pending.is_complete:
                return AfkRoundResolved(
                    duel=duel,
                    duel_completed=False,
                    was_already_resolved=True,
                )

            now = self._clock.now()
            p1_fallback = self._roll_choice() if pending.p1_choice is None else None
            p2_fallback = self._roll_choice() if pending.p2_choice is None else None

            mutated = duel.force_complete_round(
                p1_fallback=p1_fallback,
                p2_fallback=p2_fallback,
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
                self._business_metrics.inc_duel_resolved(
                    _afk_outcome_label(
                        saved,
                        p1_was_afk=p1_fallback is not None,
                        p2_was_afk=p2_fallback is not None,
                    )
                )

        # AFK-таймер следующего раунда (Спринт 2.1.G).
        # Только если дуэль осталась в IN_PROGRESS — schedule новый timer.
        # Предыдущий (только что сработавший) уже удалён APScheduler-ом
        # самостоятельно («date»-trigger одноразовый).
        if (
            self._scheduler is not None
            and self._balance is not None
            and not duel_completed
            and saved.pending_round is not None
        ):
            assert saved.id is not None
            cfg = self._balance.get().pvp.duel_1v1
            await self._scheduler.schedule_round_afk_resolution(
                duel_id=saved.id,
                round_num=saved.pending_round.round_num,
                run_at=now + timedelta(seconds=cfg.round_timer_seconds),
            )
        return AfkRoundResolved(
            duel=saved,
            duel_completed=duel_completed,
            was_already_resolved=False,
        )

    def _roll_choice(self) -> RoundChoice:
        return RoundChoice(
            attack=self._random.choice(_POSITIONS),
            block=self._random.choice(_POSITIONS),
        )

    async def _release_locks(self, duel: Duel) -> None:
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
                actor_id=None,
                target_kind="pvp_duel",
                target_id=str(duel.id),
                before=None,
                after={
                    "winner": outcome.winner.value,
                    "p1_total_dealt": outcome.p1_total_dealt,
                    "p2_total_dealt": outcome.p2_total_dealt,
                    "p1_delta_cm": outcome.p1_delta_cm,
                    "p2_delta_cm": outcome.p2_delta_cm,
                    "afk_fallback": True,
                },
                reason="pvp_duel_completed_afk",
                idempotency_key=f"pvp_duel_completed:{duel.id}",
                occurred_at=now,
            )
        )


def _afk_outcome_label(  # noqa: PLR0911
    duel: Duel,
    *,
    p1_was_afk: bool,
    p2_was_afk: bool,
) -> DuelResolvedOutcome:
    """Маппинг исхода + AFK-флагов в `DuelResolvedOutcome`-label.

    Семантика:
    * Если AFK был только у одной стороны — помечаем дуэль как
      `pN_afk` ("проигравший N был AFK"), даже если из-за случайного
      fallback она формально выиграла или вышла в ничью. Для аналитики
      важен сам факт AFK-фоллбэка, а не итоговый winner.
    * Если AFK были оба — это редкий вырожденный случай (оба не
      нажали кнопку до таймаута). Маркируем как сторону «более
      затянутой» проигрышем; при ничьей — `draw`.
    * AFK не было ни у одного (`force_complete_round` сработал, но
      оба уже отправили ходы) — маршрут реалистично невозможен (выше
      есть `pending.is_complete`-guard), но защищаемся.
    """
    outcome = duel.final_outcome
    assert outcome is not None

    if p1_was_afk and not p2_was_afk:
        return "p1_afk"
    if p2_was_afk and not p1_was_afk:
        return "p2_afk"
    if p1_was_afk and p2_was_afk:
        if outcome.winner is DuelWinner.P1:
            return "p2_afk"
        if outcome.winner is DuelWinner.P2:
            return "p1_afk"
        return "draw"
    if outcome.winner is DuelWinner.P1:
        return "p1_win"
    if outcome.winner is DuelWinner.P2:
        return "p2_win"
    return "draw"


__all__ = [
    "AfkRoundResolved",
    "ResolveAfkRound",
]
