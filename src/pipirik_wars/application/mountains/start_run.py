"""Use-case `StartMountainRun` (Спринт 3.1-B, ГДД §8).

Игрок отправляет `/mountains`. Use-case (зеркало `StartForestRun`):

1. Находит `Player` по `tg_id`. Нет — `PlayerNotFoundError`.
2. Проверяет требования входа (ГДД §8, §3.1):
   - `thickness.level >= balance.thickness.unlock_levels.mountains` (по
     умолчанию `3`); иначе — `MountainsRequirementError(requirement="thickness")`.
   - `length.cm >= MIN_LENGTH_AFTER_SPEND_CM` (`20` см, ГДД §3.1
     «Правило 20 см» — порог входа). Иначе —
     `MountainsRequirementError(requirement="length")`. Loss-исход
     может опустить длину ниже 20 см после применения (clamped к 0) —
     это by design (как в PvP, см. `application/pvp/apply_outcome.py`).
3. Берёт `activity_lock(player_id, MOUNTAINS, ttl=cooldown_minutes)`.
   Уже взят — `AlreadyInMountainsError`.
4. Ролит cooldown ∈ `[mountains.cooldown_min_minutes,
   mountains.cooldown_max_minutes]` через `IRandom.randint`.
5. Сразу ролит исход через `pick_pve_outcome(MOUNTAINS, balance, random)`
   и записывает `branch_name`/`length_delta_cm`/`drops` на старте — это
   устойчиво к рестарту воркера и к hot-reload-у баланса (тот же приём,
   что и в `StartForestRun`).
6. Создаёт `mountain_runs(status=in_progress, ...)`.
7. Планирует `FinishMountainRun(run_id)` на `ends_at` через
   `IDelayedJobScheduler.schedule_finish_mountain_run`.
8. Пишет `audit_log(action=MOUNTAIN_RUN_STARTED)` с
   `idempotency_key=f"mountain_run_started:{run.id}"`.
9. Возвращает `MountainRunStarted(run, cooldown_minutes)`.

Транзакция: всё внутри одного `IUnitOfWork`. Любая ошибка → rollback,
лок не остаётся.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from pipirik_wars.application.dto.inputs import StartMountainRunInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance import BalanceConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.mountains import (
    AlreadyInMountainsError,
    IMountainRunRepository,
    MountainRun,
    MountainsRequirementError,
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
class MountainRunStarted:
    """Результат успешного старта похода в горы.

    `cooldown_minutes` — фактически выпавшее значение, нужно handler-у
    для сообщения «ушёл в горы, вернётся через X минут» (ГДД §8.2).
    """

    run: MountainRun
    cooldown_minutes: int


class StartMountainRun:
    """Use-case «игрок ушёл в горы»."""

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
        runs: IMountainRunRepository,
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

    async def execute(self, input_dto: StartMountainRunInput) -> MountainRunStarted:
        """Стартовать поход в горы. См. docstring модуля для контракта."""
        async with self._uow:
            player = await self._fetch_player(tg_id=input_dto.tg_id)
            cfg = self._balance.get()
            self._check_requirements(player=player, balance=cfg)

            cooldown_minutes = self._random.randint(
                cfg.mountains.cooldown_min_minutes,
                cfg.mountains.cooldown_max_minutes,
            )
            cooldown = timedelta(minutes=cooldown_minutes)
            await self._acquire_lock(player_id=self._require_id(player), cooldown=cooldown)

            now = self._clock.now()
            ends_at = now + cooldown
            outcome = pick_pve_outcome(
                location=PveLocationKind.MOUNTAINS,
                balance=cfg,
                random=self._random,
            )
            run = MountainRun.starting(
                player_id=self._require_id(player),
                outcome=outcome,
                started_at=now,
                ends_at=ends_at,
            )
            saved = await self._runs.add(run)

            assert saved.id is not None  # repo гарантирует id после add()
            await self._scheduler.schedule_finish_mountain_run(
                run_id=saved.id,
                run_at=saved.ends_at,
            )

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.MOUNTAIN_RUN_STARTED,
                    actor_id=player.tg_id,
                    target_kind="mountain_run",
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
                    reason="mountain_run_started",
                    idempotency_key=f"mountain_run_started:{saved.id}",
                    occurred_at=now,
                )
            )
        return MountainRunStarted(run=saved, cooldown_minutes=cooldown_minutes)

    async def _fetch_player(self, *, tg_id: int) -> Player:
        player = await self._players.get_by_tg_id(tg_id)
        if player is None:
            raise PlayerNotFoundError(tg_id=tg_id)
        return player

    @staticmethod
    def _require_id(player: Player) -> int:
        if player.id is None:  # repository.get_by_tg_id всегда возвращает с id
            raise RuntimeError(
                f"Player tg_id={player.tg_id} loaded without id; repository contract violation"
            )
        return player.id

    @staticmethod
    def _check_requirements(*, player: Player, balance: BalanceConfig) -> None:
        required_thickness = balance.thickness.unlock_levels["mountains"]
        if player.thickness.level < required_thickness:
            assert player.id is not None
            raise MountainsRequirementError(
                player_id=player.id,
                requirement="thickness",
                required=required_thickness,
                actual=player.thickness.level,
            )
        if player.length.cm < MIN_LENGTH_AFTER_SPEND_CM:
            assert player.id is not None
            raise MountainsRequirementError(
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
                reason=LockReason.MOUNTAINS,
                ttl=cooldown,
            )
        except LockAlreadyHeldError as exc:
            raise AlreadyInMountainsError(player_id=player_id) from exc
