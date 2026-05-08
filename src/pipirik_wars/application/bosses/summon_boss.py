"""Use-case `SummonBoss` (Спринт 3.3-B, ГДД §10.1 — §10.3).

Игрок-саммонер инициирует рейд через `/boss`-команду (handler — 3.3-D):

1. Открывается ambient-`IUnitOfWork` (всё ниже — в одной транзакции).
2. Резолвится игрок (`IPlayerRepository.get_by_tg_id`):
   - не найден → `PlayerNotFoundError`;
   - `FROZEN`/`BANNED` → `PlayerFrozenError`.
3. Валидируются требования к саммонеру (ГДД §10.1):
   - `thickness.level >= bosses.min_thickness_level_summoner` (=9);
   - `length.cm >= bosses.min_length_cm` (=20).
4. Проверяется глобальный 4-часовой кулдаун (ГДД §10.1: «1 раз в 4 часа
   (глобальный)») через `IBossFightRepository.get_last_global_started_at`.
   Кулдаун — на весь сервер (по решению cyan91 на старте 3.3-A);
   `CANCELLED`-бои тоже «съедают» кулдаун. Не истёк →
   `BossSummonOnGlobalCooldownError(actual_remaining_seconds=…)`.
5. Берётся `activity_lock(player, RAID, ttl=lobby_minutes)` для саммонера;
   `LockAlreadyHeldError` → `AlreadyInBossFightError`.
6. Резолвится пул кандидатов в боссы:
   `IPlayerRepository.list_top_by_length(limit=bosses.top_n_pool)`.
   Из пула выбрасывается сам саммонер; пустой результат →
   `BossPlayerPoolEmptyError`. Босс выбирается через
   `IRandom.choice(...)`.
7. Создаётся `BossFight.starting(...)` (`status=LOBBY`,
   `current_boss_length_cm=initial_boss_length_cm` — снапшот длины
   босса в момент призыва), сохраняется (`add` → `id`).
8. Создаётся первый `BossParticipant.raider(is_summoner=True, ...)`
   (саммонер — всегда первый рейдер; ГДД §10.3 «минимум 1 рейдер»).
9. Шедулится `boss_lobby_close(boss_fight_id, run_at=lobby_ends_at)`
   через `IDelayedJobScheduler`.
10. Audit `BOSS_FIGHT_SUMMONED` (idempotency-key
    `boss_fight_summoned:{boss_fight_id}`).

Транзакция — единая: любая ошибка откатывает запись рейд-боя,
саммонера-рейдера и активити-лок целиком.

Длина саммонера на старте призыва **не списывается** — рейд-бой
не имеет «взноса» (в отличие от каравана). Длины забираются/раздаются
только в `FinishBossFight` (3.3-C) по итогам боя.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pipirik_wars.application.dto.inputs import SummonBossInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.bosses import (
    AlreadyInBossFightError,
    BossFight,
    BossFightRequirementError,
    BossKind,
    BossParticipant,
    BossPlayerPoolEmptyError,
    BossSummonOnGlobalCooldownError,
    IBossFightRepository,
    IBossParticipantRepository,
)
from pipirik_wars.domain.player import IPlayerRepository, Player, PlayerStatus
from pipirik_wars.domain.player.errors import (
    PlayerFrozenError,
    PlayerNotFoundError,
)
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
class BossSummoned:
    """Результат успешного `SummonBoss`."""

    boss_fight: BossFight
    summoner_participant: BossParticipant


class SummonBoss:
    """Use-case «игрок призвал рейд-босса» (ГДД §10.1 — §10.3)."""

    __slots__ = (
        "_audit",
        "_balance",
        "_boss_fights",
        "_boss_participants",
        "_clock",
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
        boss_fights: IBossFightRepository,
        boss_participants: IBossParticipantRepository,
        locks: ActivityLockService,
        balance: IBalanceConfig,
        random: IRandom,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler,
    ) -> None:
        self._uow = uow
        self._players = players
        self._boss_fights = boss_fights
        self._boss_participants = boss_participants
        self._locks = locks
        self._balance = balance
        self._random = random
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler

    async def execute(self, input_dto: SummonBossInput) -> BossSummoned:
        """Призвать рейд-босса. См. docstring модуля для контракта."""
        async with self._uow:
            cfg = self._balance.get().bosses
            now = self._clock.now()

            summoner = await self._fetch_player(tg_id=input_dto.summoner_tg_id)
            assert summoner.id is not None
            self._ensure_player_active(player=summoner)
            self._ensure_thickness(
                player=summoner,
                required=cfg.min_thickness_level_summoner,
            )
            self._ensure_length(player=summoner, required=cfg.min_length_cm)

            await self._ensure_cooldown_expired(
                cooldown_hours=cfg.summon_cooldown_hours,
                now=now,
            )

            lobby_ends_at = now + timedelta(minutes=cfg.lobby_minutes)
            await self._acquire_lock(
                player_id=summoner.id,
                ttl=lobby_ends_at - now,
            )

            boss = await self._pick_boss(
                summoner_id=summoner.id,
                top_n_pool=cfg.top_n_pool,
            )
            assert boss.id is not None

            random_seed = self._random.randint(0, 2**31 - 1)
            boss_fight = BossFight.starting(
                kind=BossKind.RAID,
                summoner_player_id=summoner.id,
                boss_player_id=boss.id,
                started_at=now,
                lobby_ends_at=lobby_ends_at,
                random_seed=random_seed,
                initial_boss_length_cm=boss.length.cm,
            )
            saved = await self._boss_fights.add(boss_fight)
            assert saved.id is not None

            summoner_participant = BossParticipant.raider(
                boss_fight_id=saved.id,
                player_id=summoner.id,
                is_summoner=True,
                length_at_join_cm=summoner.length.cm,
                joined_at=now,
            )
            stored_summoner = await self._boss_participants.add(summoner_participant)

            await self._scheduler.schedule_boss_lobby_close(
                boss_fight_id=saved.id,
                run_at=saved.lobby_ends_at,
            )

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.BOSS_FIGHT_SUMMONED,
                    actor_id=summoner.tg_id,
                    target_kind="boss_fight",
                    target_id=str(saved.id),
                    before=None,
                    after={
                        "kind": saved.kind.value,
                        "summoner_player_id": saved.summoner_player_id,
                        "boss_player_id": saved.boss_player_id,
                        "started_at": saved.started_at.isoformat(),
                        "lobby_ends_at": saved.lobby_ends_at.isoformat(),
                        "random_seed": saved.random_seed,
                        "initial_boss_length_cm": saved.initial_boss_length_cm,
                    },
                    reason="boss_fight_summoned",
                    idempotency_key=f"boss_fight_summoned:{saved.id}",
                    occurred_at=now,
                )
            )

        return BossSummoned(
            boss_fight=saved,
            summoner_participant=stored_summoner,
        )

    # -------- helpers --------

    async def _fetch_player(self, *, tg_id: int) -> Player:
        player = await self._players.get_by_tg_id(tg_id)
        if player is None:
            raise PlayerNotFoundError(tg_id=tg_id)
        return player

    @staticmethod
    def _ensure_player_active(*, player: Player) -> None:
        if player.status is not PlayerStatus.ACTIVE:
            raise PlayerFrozenError(tg_id=player.tg_id)

    @staticmethod
    def _ensure_thickness(*, player: Player, required: int) -> None:
        if player.thickness.level < required:
            assert player.id is not None
            raise BossFightRequirementError(
                player_id=player.id,
                requirement="thickness",
                required=required,
                actual=player.thickness.level,
            )

    @staticmethod
    def _ensure_length(*, player: Player, required: int) -> None:
        if player.length.cm < required:
            assert player.id is not None
            raise BossFightRequirementError(
                player_id=player.id,
                requirement="length_total",
                required=required,
                actual=player.length.cm,
            )

    async def _ensure_cooldown_expired(
        self,
        *,
        cooldown_hours: int,
        now: datetime,
    ) -> None:
        if cooldown_hours <= 0:
            return
        last_started_at = await self._boss_fights.get_last_global_started_at()
        if last_started_at is None:
            return
        threshold = last_started_at + timedelta(hours=cooldown_hours)
        if now < threshold:
            remaining = int((threshold - now).total_seconds())
            raise BossSummonOnGlobalCooldownError(
                actual_remaining_seconds=remaining,
            )

    async def _acquire_lock(self, *, player_id: int, ttl: timedelta) -> None:
        try:
            await self._locks.acquire(
                actor_kind="player",
                actor_id=player_id,
                reason=LockReason.RAID,
                ttl=ttl,
            )
        except LockAlreadyHeldError as exc:
            raise AlreadyInBossFightError(player_id=player_id) from exc

    async def _pick_boss(self, *, summoner_id: int, top_n_pool: int) -> Player:
        candidates = await self._players.list_top_by_length(limit=top_n_pool)
        eligible = tuple(p for p in candidates if p.id is not None and p.id != summoner_id)
        if not eligible:
            raise BossPlayerPoolEmptyError(pool_size=len(candidates))
        return self._random.choice(eligible)


__all__ = [
    "BossSummoned",
    "SummonBoss",
]
