"""Use-case `JoinBossLobby` (Спринт 3.3-B, ГДД §10.1, §10.3).

Игрок жмёт «Вступить в рейд» под объявлением вызова рейд-босса:

1. Открывается ambient-`IUnitOfWork` (всё ниже — в одной транзакции).
2. Резолвится рейд-бой (`IBossFightRepository.get_by_id`):
   - не найден → `BossFightNotFoundError`;
   - `status != LOBBY` → `BossFightLobbyClosedError`.
3. Резолвится игрок (`IPlayerRepository.get_by_tg_id`):
   - не найден → `PlayerNotFoundError`;
   - `FROZEN`/`BANNED` → `PlayerFrozenError`.
4. Игрок ещё не участник этого боя — иначе `AlreadyInBossFightError`
   (саммонер уже вступил в `SummonBoss`; обычный рейдер не может
   повторно вступить — это ловится UNIQUE-индексом, но мы проверяем
   заранее, чтобы дать понятную ошибку до `IntegrityError`).
5. Игрок не является самим боссом этого рейда (`boss_player_id`).
   Иначе — `AlreadyInBossFightError(player_id=...)` (босс уже
   «занят» в этом бою как сам босс — повторно зайти рейдером
   нельзя).
6. Валидируются требования к рейдеру (ГДД §10.1):
   - `thickness.level >= bosses.min_thickness_level_raider` (=4);
   - `length.cm >= bosses.min_length_cm` (=20).
7. Берётся `activity_lock(player, RAID, ttl)` (TTL = `lobby_ends_at - now`,
   но не меньше `1` секунды). `LockAlreadyHeldError` →
   `AlreadyInBossFightError`.
8. Сохраняется `BossParticipant.raider(is_summoner=False, ...)` через
   `IBossParticipantRepository.add(...)`. БД-инвариант UNIQUE
   `(boss_fight_id, player_id)` — последний рубеж против
   повторного входа.
9. Audit `BOSS_RAIDER_JOINED` (idempotency-key
   `boss_raider_joined:{boss_fight_id}:{player_id}`).
10. Возвращается `BossLobbyJoined(boss_fight, participant)`.

Длина рейдера на вступлении **не списывается** — рейд-бой длинами
торгует только на финише (3.3-C, `FinishBossFight`); пока в лобби,
длина игрока остаётся прежней. Снапшот `length_at_join_cm` нужен,
чтобы `FinishBossFight` мог посчитать «сколько забрал босс»
именно на момент вступления (ГДД §10.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pipirik_wars.application.dto.inputs import JoinBossLobbyInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.bosses import (
    AlreadyInBossFightError,
    BossFight,
    BossFightLobbyClosedError,
    BossFightNotFoundError,
    BossFightRequirementError,
    BossParticipant,
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
    IUnitOfWork,
)

_MIN_LOCK_TTL = timedelta(seconds=1)


@dataclass(frozen=True, slots=True)
class BossLobbyJoined:
    """Результат успешного `JoinBossLobby`."""

    boss_fight: BossFight
    participant: BossParticipant


class JoinBossLobby:
    """Use-case «игрок вступил в лобби рейд-боя» (ГДД §10.1, §10.3)."""

    __slots__ = (
        "_audit",
        "_balance",
        "_boss_fights",
        "_boss_participants",
        "_clock",
        "_locks",
        "_players",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        boss_fights: IBossFightRepository,
        boss_participants: IBossParticipantRepository,
        players: IPlayerRepository,
        locks: ActivityLockService,
        balance: IBalanceConfig,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._boss_fights = boss_fights
        self._boss_participants = boss_participants
        self._players = players
        self._locks = locks
        self._balance = balance
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: JoinBossLobbyInput) -> BossLobbyJoined:
        """Вступить в лобби рейд-боя. См. docstring модуля для контракта."""
        async with self._uow:
            cfg = self._balance.get().bosses
            now = self._clock.now()

            boss_fight = await self._fetch_boss_fight(boss_fight_id=input_dto.boss_fight_id)
            self._ensure_lobby(boss_fight=boss_fight)

            player = await self._fetch_player(tg_id=input_dto.tg_id)
            assert player.id is not None
            self._ensure_player_active(player=player)
            self._ensure_not_boss(boss_fight=boss_fight, player_id=player.id)

            assert boss_fight.id is not None
            await self._ensure_not_yet_participant(
                boss_fight_id=boss_fight.id,
                player_id=player.id,
            )

            self._ensure_thickness(player=player, required=cfg.min_thickness_level_raider)
            self._ensure_length(player=player, required=cfg.min_length_cm)

            await self._acquire_lock(
                player_id=player.id,
                ttl=self._lock_ttl(boss_fight=boss_fight, now=now),
            )

            participant = BossParticipant.raider(
                boss_fight_id=boss_fight.id,
                player_id=player.id,
                is_summoner=False,
                length_at_join_cm=player.length.cm,
                joined_at=now,
            )
            stored = await self._boss_participants.add(participant)

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.BOSS_RAIDER_JOINED,
                    actor_id=player.tg_id,
                    target_kind="boss_fight",
                    target_id=str(boss_fight.id),
                    before=None,
                    after={
                        "boss_fight_id": boss_fight.id,
                        "player_id": player.id,
                        "length_at_join_cm": stored.length_at_join_cm,
                        "is_summoner": stored.is_summoner,
                    },
                    reason="boss_raider_joined",
                    idempotency_key=f"boss_raider_joined:{boss_fight.id}:{player.id}",
                    occurred_at=now,
                )
            )

        return BossLobbyJoined(boss_fight=boss_fight, participant=stored)

    # -------- helpers --------

    async def _fetch_boss_fight(self, *, boss_fight_id: int) -> BossFight:
        boss_fight = await self._boss_fights.get_by_id(boss_fight_id=boss_fight_id)
        if boss_fight is None:
            raise BossFightNotFoundError(boss_fight_id=boss_fight_id)
        if boss_fight.id is None:  # pragma: no cover — защитный invariant
            raise RuntimeError("boss_fight loaded without id; repository contract violation")
        return boss_fight

    @staticmethod
    def _ensure_lobby(*, boss_fight: BossFight) -> None:
        if not boss_fight.is_in_lobby:
            assert boss_fight.id is not None
            raise BossFightLobbyClosedError(
                boss_fight_id=boss_fight.id,
                status=boss_fight.status.value,
            )

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
    def _ensure_not_boss(*, boss_fight: BossFight, player_id: int) -> None:
        if boss_fight.boss_player_id == player_id:
            raise AlreadyInBossFightError(player_id=player_id)

    async def _ensure_not_yet_participant(
        self,
        *,
        boss_fight_id: int,
        player_id: int,
    ) -> None:
        existing = await self._boss_participants.get_by_boss_fight_and_player(
            boss_fight_id=boss_fight_id,
            player_id=player_id,
        )
        if existing is not None:
            raise AlreadyInBossFightError(player_id=player_id)

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

    @staticmethod
    def _lock_ttl(*, boss_fight: BossFight, now: datetime) -> timedelta:
        # Лок держим до конца лобби; если игрок зашёл в самые
        # последние секунды лобби, остаток до `lobby_ends_at` стремится
        # к 0 — клампим минимумом, чтобы lock-репо не получил
        # `ttl <= 0`-валидационную ошибку.
        remaining = boss_fight.lobby_ends_at - now
        if remaining < _MIN_LOCK_TTL:
            return _MIN_LOCK_TTL
        return remaining

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


__all__ = [
    "BossLobbyJoined",
    "JoinBossLobby",
]
