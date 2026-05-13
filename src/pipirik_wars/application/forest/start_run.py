"""Use-case `StartForestRun` (Спринт 1.3.B).

Игрок отправляет `/forest`. Use-case:

1. Находит `Player` по `tg_id`. Нет — `PlayerNotFoundError`.
2. Берёт `activity_lock(player_id, FOREST, ttl=cooldown_minutes)`. Если
   уже взят — `AlreadyInForestError` (это и есть ПД §1.3.9 «двойной
   `/forest` → вы заняты»).
3. Ролит cooldown ∈ `[forest.cooldown_min_minutes, forest.cooldown_max_minutes]`
   через `IRandom.randint` (ПД §1.3.2).
4. Сразу ролит исход через `compute_forest_outcome(balance, random)` —
   `branch / length_delta / drop` записываем в `forest_runs` уже на старте.
   Это устойчиво к рестарту воркера и к hot-reload-у баланса посреди
   похода: `FinishForestRun` (1.3.C) только применит уже сохранённый
   outcome, ничего не катая.
5. Создаёт запись `forest_runs(status=in_progress, started_at, ends_at,
   ...)`.
6. Пишет `audit_log(action=FOREST_RUN_STARTED)` с `before=None,
   after={branch, length_delta_cm, drop_kind, ends_at}`.
7. Возвращает `ForestRunStarted(run, cooldown_minutes)` для handler-а.

Транзакция: всё внутри одного `IUnitOfWork`. Если на любом шаге
бросается ошибка, лок (как и `forest_runs`-запись, и audit) откатывается
вместе с транзакцией — игрок не «застревает в лесу» из-за полу-сбоя.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from pipirik_wars.application.dto.inputs import StartForestRunInput
from pipirik_wars.application.observability import (
    IBusinessMetrics,
    NullBusinessMetrics,
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.forest import (
    AlreadyInForestError,
    ForestRun,
    IForestRunRepository,
    NameDrop,
    NoDrop,
    compute_forest_outcome,
)
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
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
class ForestRunStarted:
    """Результат успешного старта.

    `cooldown_minutes` — фактически выпавшее значение, нужно handler-у
    для сообщения «ушёл в лес, вернётся через X минут» (ПД §1.3.2).
    """

    run: ForestRun
    cooldown_minutes: int


class StartForestRun:
    """Use-case «игрок ушёл в лес»."""

    __slots__ = (
        "_audit",
        "_balance",
        "_business_metrics",
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
        runs: IForestRunRepository,
        locks: ActivityLockService,
        balance: IBalanceConfig,
        random: IRandom,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler,
        business_metrics: IBusinessMetrics | None = None,
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
        self._business_metrics: IBusinessMetrics = business_metrics or NullBusinessMetrics()

    async def execute(self, input_dto: StartForestRunInput) -> ForestRunStarted:
        """Стартовать поход. Бросает `PlayerNotFoundError`, если игрока
        нет в `users`, или `AlreadyInForestError`, если он уже в лесу.
        """
        async with self._uow:
            player = await self._fetch_player(tg_id=input_dto.tg_id)
            cfg = self._balance.get()
            cooldown_minutes = self._random.randint(
                cfg.forest.cooldown_min_minutes,
                cfg.forest.cooldown_max_minutes,
            )
            cooldown = timedelta(minutes=cooldown_minutes)
            await self._acquire_lock(player_id=self._require_id(player), cooldown=cooldown)

            now = self._clock.now()
            ends_at = now + cooldown
            outcome = compute_forest_outcome(balance=cfg, random=self._random)
            run = ForestRun.starting(
                player_id=self._require_id(player),
                outcome=outcome,
                started_at=now,
                ends_at=ends_at,
            )
            saved = await self._runs.add(run)

            assert saved.id is not None  # repo гарантирует id после add()
            await self._scheduler.schedule_finish_forest_run(
                run_id=saved.id,
                run_at=saved.ends_at,
            )

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.FOREST_RUN_STARTED,
                    actor_id=player.tg_id,
                    target_kind="forest_run",
                    target_id=str(saved.id),
                    before=None,
                    after={
                        "player_id": saved.player_id,
                        "branch_name": saved.branch_name,
                        "length_delta_cm": saved.length_delta_cm,
                        "drop_kind": _drop_kind(saved),
                        "cooldown_minutes": cooldown_minutes,
                        "ends_at": saved.ends_at.isoformat(),
                    },
                    reason="forest_run_started",
                    idempotency_key=f"forest_run_started:{saved.id}",
                    occurred_at=now,
                )
            )
        self._business_metrics.inc_forest_started()
        return ForestRunStarted(run=saved, cooldown_minutes=cooldown_minutes)

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

    async def _acquire_lock(self, *, player_id: int, cooldown: timedelta) -> None:
        try:
            await self._locks.acquire(
                actor_kind="player",
                actor_id=player_id,
                reason=LockReason.FOREST,
                ttl=cooldown,
            )
        except LockAlreadyHeldError as exc:
            raise AlreadyInForestError(player_id=player_id) from exc


def _drop_kind(run: ForestRun) -> str:
    """Сериализованное имя ADT-конструктора для audit-записи."""
    if isinstance(run.drop, NoDrop):
        return "none"
    if isinstance(run.drop, NameDrop):
        return "name"
    return "item"
