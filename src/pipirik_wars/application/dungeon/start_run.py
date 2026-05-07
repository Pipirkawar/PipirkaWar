"""Use-case `StartDungeonRun` (Спринт 3.1-B, ГДД §8).

Зеркало `StartMountainRun` со следующими отличиями:

- `LockReason.DUNGEON` вместо `MOUNTAINS`.
- `pick_pve_outcome(location=DUNGEON, ...)` — данжон имеет другие
  ветки исходов и `max_drops=3` (горы — `max_drops=1`).
- `cooldown ∈ [40, 60]` минут (горы — 20–40).
- Требование уровня: `thickness >= unlock_levels.dungeon` (по умолчанию `6`).
- `AuditAction.DUNGEON_RUN_STARTED`.
- `IDelayedJobScheduler.schedule_finish_dungeon_run(...)`.

Структура и контракт идентичны: транзакционность, идемпотентность,
проверка правила 20 см на входе. См. docstring `StartMountainRun`
для полного описания.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from pipirik_wars.application.dto.inputs import StartDungeonRunInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance import BalanceConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.dungeon import (
    AlreadyInDungeonError,
    DungeonRequirementError,
    DungeonRun,
    IDungeonRunRepository,
)
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression import MIN_LENGTH_AFTER_SPEND_CM
from pipirik_wars.domain.pve import PveLocationKind, pick_pve_outcome
from pipirik_wars.domain.security import LockAlreadyHeldError, LockReason
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IRandom,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class DungeonRunStarted:
    """Результат успешного старта похода в данжон."""

    run: DungeonRun
    cooldown_minutes: int


class StartDungeonRun:
    """Use-case «игрок ушёл в данжон»."""

    __slots__ = (
        "_audit",
        "_balance",
        "_clock",
        "_locks",
        "_players",
        "_random",
        "_runs",
        "_scheduler",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        runs: IDungeonRunRepository,
        locks: ActivityLockService,
        balance: IBalanceConfig,
        random: IRandom,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler,
    ) -> None:
        self._uow = uow
        self._players = players
        self._runs = runs
        self._locks = locks
        self._balance = balance
        self._random = random
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler

    async def execute(self, input_dto: StartDungeonRunInput) -> DungeonRunStarted:
        """Стартовать поход в данжон. См. docstring модуля для контракта."""
        async with self._uow:
            player = await self._fetch_player(tg_id=input_dto.tg_id)
            cfg = self._balance.get()
            self._check_requirements(player=player, balance=cfg)

            cooldown_minutes = self._random.randint(
                cfg.dungeon.cooldown_min_minutes,
                cfg.dungeon.cooldown_max_minutes,
            )
            cooldown = timedelta(minutes=cooldown_minutes)
            await self._acquire_lock(player_id=self._require_id(player), cooldown=cooldown)

            now = self._clock.now()
            ends_at = now + cooldown
            outcome = pick_pve_outcome(
                location=PveLocationKind.DUNGEON,
                balance=cfg,
                random=self._random,
            )
            run = DungeonRun.starting(
                player_id=self._require_id(player),
                outcome=outcome,
                started_at=now,
                ends_at=ends_at,
            )
            saved = await self._runs.add(run)

            assert saved.id is not None
            await self._scheduler.schedule_finish_dungeon_run(
                run_id=saved.id,
                run_at=saved.ends_at,
            )

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.DUNGEON_RUN_STARTED,
                    actor_id=player.tg_id,
                    target_kind="dungeon_run",
                    target_id=str(saved.id),
                    before=None,
                    after={
                        "player_id": saved.player_id,
                        "branch_name": saved.branch_name,
                        "length_delta_cm": saved.length_delta_cm,
                        "drops_count": len(saved.drops),
                        "cooldown_minutes": cooldown_minutes,
                        "ends_at": saved.ends_at.isoformat(),
                    },
                    reason="dungeon_run_started",
                    idempotency_key=f"dungeon_run_started:{saved.id}",
                    occurred_at=now,
                )
            )
        return DungeonRunStarted(run=saved, cooldown_minutes=cooldown_minutes)

    async def _fetch_player(self, *, tg_id: int) -> Player:
        player = await self._players.get_by_tg_id(tg_id)
        if player is None:
            raise PlayerNotFoundError(tg_id=tg_id)
        return player

    @staticmethod
    def _require_id(player: Player) -> int:
        if player.id is None:
            raise RuntimeError(
                f"Player tg_id={player.tg_id} loaded without id; repository contract violation"
            )
        return player.id

    @staticmethod
    def _check_requirements(*, player: Player, balance: BalanceConfig) -> None:
        required_thickness = balance.thickness.unlock_levels["dungeon"]
        if player.thickness.level < required_thickness:
            assert player.id is not None
            raise DungeonRequirementError(
                player_id=player.id,
                requirement="thickness",
                required=required_thickness,
                actual=player.thickness.level,
            )
        if player.length.cm < MIN_LENGTH_AFTER_SPEND_CM:
            assert player.id is not None
            raise DungeonRequirementError(
                player_id=player.id,
                requirement="length",
                required=MIN_LENGTH_AFTER_SPEND_CM,
                actual=player.length.cm,
            )

    async def _acquire_lock(self, *, player_id: int, cooldown: timedelta) -> None:
        try:
            await self._locks.acquire(
                actor_kind="player",
                actor_id=player_id,
                reason=LockReason.DUNGEON,
                ttl=cooldown,
            )
        except LockAlreadyHeldError as exc:
            raise AlreadyInDungeonError(player_id=player_id) from exc
