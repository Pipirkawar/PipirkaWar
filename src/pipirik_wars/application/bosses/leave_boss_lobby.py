"""Use-case `LeaveBossLobby` (Спринт 3.3-B, ГДД §10.3).

Игрок жмёт «Выйти» в лобби рейд-боя:

1. Открывается ambient-`IUnitOfWork`.
2. Резолвится рейд-бой (`IBossFightRepository.get_by_id`):
   - не найден → `BossFightNotFoundError`;
   - `status != LOBBY` → `BossFightLobbyClosedError` (после `LOBBY →
     IN_BATTLE` выход уже невозможен — это уже выбывание в раунде).
3. Резолвится игрок (`IPlayerRepository.get_by_tg_id`):
   - не найден → `PlayerNotFoundError`.
4. Игрок должен быть участником этого боя — иначе
   `NotInBossFightError(boss_fight_id=..., player_id=...)`.
5. `IBossParticipantRepository.remove(boss_fight_id, player_id)`.
6. Снимается `activity_lock(player, RAID)` через
   `ActivityLockService.release` (NO-OP, если лока нет).
7. Audit `BOSS_RAIDER_LEFT` (idempotency-key
   `boss_raider_left:{boss_fight_id}:{player_id}:{joined_at_iso}`).
8. Возвращается `BossLobbyLeft(boss_fight, removed_participant)`.

ВАЖНО (по решению cyan91 на старте 3.3-A):

- Саммонер выйти из лобби **может** — use-case не отказывает по
  `is_summoner=True`. Это эквивалентно отмене рейда для саммонера,
  но в 3.3-B мы НЕ переводим бой в `CANCELLED` автоматически:
  bot-handler в 3.3-D отдельно вызовет `CancelBossFight` (use-case
  3.3-C), если после ухода саммонера рейдеров больше нет.
- Глобальный кулдаун саммонера **НЕ сбрасывается** на leave —
  4-часовой кулдаун рейд-боя стартует с `started_at` боя в `LOBBY`,
  и отменённый/распущенный бой тоже «съедает» кулдаун. Это
  предотвращает чит «призвал, вышел, призвал ещё раз через минуту».
- Длина игрока **не возвращается**, потому что взноса в рейд-боях
  нет (в отличие от каравана). Здесь нет `returned_contribution_cm`-
  поля.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import LeaveBossLobbyInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightLobbyClosedError,
    BossFightNotFoundError,
    BossParticipant,
    IBossFightRepository,
    IBossParticipantRepository,
    NotInBossFightError,
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
class BossLobbyLeft:
    """Результат успешного `LeaveBossLobby`."""

    boss_fight: BossFight
    removed_participant: BossParticipant


class LeaveBossLobby:
    """Use-case «игрок вышел из лобби рейд-боя» (ГДД §10.3)."""

    __slots__ = (
        "_audit",
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
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._boss_fights = boss_fights
        self._boss_participants = boss_participants
        self._players = players
        self._locks = locks
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: LeaveBossLobbyInput) -> BossLobbyLeft:
        """Выйти из лобби рейд-боя. См. docstring модуля для контракта."""
        async with self._uow:
            now = self._clock.now()

            boss_fight = await self._fetch_boss_fight(boss_fight_id=input_dto.boss_fight_id)
            self._ensure_lobby(boss_fight=boss_fight)

            player = await self._fetch_player(tg_id=input_dto.tg_id)
            assert player.id is not None

            assert boss_fight.id is not None
            participant = await self._fetch_participant(
                boss_fight_id=boss_fight.id,
                player_id=player.id,
            )

            await self._boss_participants.remove(
                boss_fight_id=boss_fight.id,
                player_id=player.id,
            )
            await self._locks.release(
                actor_kind="player",
                actor_id=player.id,
            )

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.BOSS_RAIDER_LEFT,
                    actor_id=player.tg_id,
                    target_kind="boss_fight",
                    target_id=str(boss_fight.id),
                    before={
                        "boss_fight_id": boss_fight.id,
                        "player_id": player.id,
                        "is_summoner": participant.is_summoner,
                        "length_at_join_cm": participant.length_at_join_cm,
                    },
                    after=None,
                    reason="boss_raider_left",
                    idempotency_key=(
                        f"boss_raider_left:{boss_fight.id}:{player.id}:"
                        f"{participant.joined_at.isoformat()}"
                    ),
                    occurred_at=now,
                )
            )

        return BossLobbyLeft(
            boss_fight=boss_fight,
            removed_participant=participant,
        )

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

    async def _fetch_participant(
        self,
        *,
        boss_fight_id: int,
        player_id: int,
    ) -> BossParticipant:
        participant = await self._boss_participants.get_by_boss_fight_and_player(
            boss_fight_id=boss_fight_id,
            player_id=player_id,
        )
        if participant is None:
            raise NotInBossFightError(
                boss_fight_id=boss_fight_id,
                player_id=player_id,
            )
        return participant


__all__ = [
    "BossLobbyLeft",
    "LeaveBossLobby",
]
