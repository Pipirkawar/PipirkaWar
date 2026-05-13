"""Use-case `CancelBossFight` (Спринт 3.3-D, ГДД §10.3).

Саммонер нажал «Отменить рейд» в лобби:

1. Открывается ambient-`IUnitOfWork` (всё ниже — в одной транзакции).
2. Резолвится рейд-бой (`IBossFightRepository.get_by_id`):
   - не найден → :class:`BossFightNotFoundError`;
   - `status == CANCELLED` → идемпотентный no-op
     (`BossFightCancelled(was_already_cancelled=True)`);
   - `status in {IN_BATTLE, FINISHED}` → :class:`InvalidBossFightStateError`
     (отмена возможна только из `LOBBY` — после старта раундов уже
     поздно, рейдеры играют).
3. Резолвится игрок (`IPlayerRepository.get_by_tg_id`):
   - не найден → :class:`PlayerNotFoundError`.
4. Сверка авторизации: `boss_fight.summoner_player_id == player.id`.
   - не саммонер → :class:`NotAuthorizedToCancelBossError`. Обычные
     рейдеры могут только выйти из лобби (`LeaveBossLobby`), но не
     отменить весь рейд.
5. `BossFight.mark_cancelled(cancelled_at=now)` + `IBossFightRepository.save`.
6. Снимаются `activity_lock(player, *)` для **всех** участников
   (саммонер + рейдеры через `IBossParticipantRepository.list_by_boss_fight`,
   плюс босс — `boss_fight.boss_player_id`). Идемпотентно: NO-OP, если
   лок уже снят.
7. Отзывается APScheduler-job:
   `IDelayedJobScheduler.cancel_boss_lobby_close(boss_fight_id)`.
   Round-tick + finish-job ещё не запланированы — их ставит
   `CloseBossLobby` при переходе `LOBBY → IN_BATTLE` (Спринт 3.3-B).
   Дополнительно best-effort cancel-им `cancel_boss_round_tick` /
   `cancel_boss_fight_finish` на случай race-а с lobby-close-callback
   (если бы он успел перевести в `IN_BATTLE` между шагами 2 и 5,
   шаг 2 поймал бы `InvalidBossFightStateError` — но best-effort
   cancel дешёвый и защищает от любого экзотического race-а).
8. Audit `BOSS_FIGHT_CANCELLED` (idempotency-key
   `boss_fight_cancelled:{boss_fight_id}`).
9. Возвращается `BossFightCancelled`.

Длины игроков НЕ восстанавливаются — на этапе лобби они и не
списывались (списание происходит только в `FinishBossFight`,
Спринт 3.3-C + raider-loss-вычеты в 3.3-D D.2).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import CancelBossFightInput
from pipirik_wars.application.observability import IBusinessMetrics, NullBusinessMetrics
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightNotFoundError,
    BossFightStatus,
    BossParticipant,
    IBossFightRepository,
    IBossParticipantRepository,
    InvalidBossFightStateError,
    NotAuthorizedToCancelBossError,
)
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class BossFightCancelled:
    """Результат `CancelBossFight`.

    `was_already_cancelled=True` — повторный вызов на уже-`CANCELLED`
    рейд-бое (no-op, аудит не писался, локи и job не трогались).
    """

    boss_fight: BossFight
    was_already_cancelled: bool


class CancelBossFight:
    """Use-case «саммонер отменяет рейд из лобби» (ГДД §10.3)."""

    __slots__ = (
        "_audit",
        "_boss_fights",
        "_boss_participants",
        "_business_metrics",
        "_clock",
        "_locks",
        "_players",
        "_scheduler",
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
        scheduler: IDelayedJobScheduler,
        business_metrics: IBusinessMetrics | None = None,
    ) -> None:
        self._uow = uow
        self._boss_fights = boss_fights
        self._boss_participants = boss_participants
        self._players = players
        self._locks = locks
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler
        self._business_metrics: IBusinessMetrics = business_metrics or NullBusinessMetrics()

    async def execute(self, input_dto: CancelBossFightInput) -> BossFightCancelled:
        """Отменить рейд-бой. См. docstring модуля для контракта."""
        async with self._uow:
            now = self._clock.now()

            boss_fight = await self._fetch_boss_fight(boss_fight_id=input_dto.boss_fight_id)

            if boss_fight.status is BossFightStatus.CANCELLED:
                return BossFightCancelled(
                    boss_fight=boss_fight,
                    was_already_cancelled=True,
                )
            self._ensure_lobby(boss_fight=boss_fight)

            player = await self._fetch_player(tg_id=input_dto.tg_id)
            assert player.id is not None
            self._ensure_summoner(boss_fight=boss_fight, player=player)

            cancelled = boss_fight.mark_cancelled(cancelled_at=now)
            saved = await self._boss_fights.save(cancelled)
            assert saved.id is not None

            participants = await self._boss_participants.list_by_boss_fight(
                boss_fight_id=saved.id,
            )
            await self._release_locks(boss_fight=saved, participants=participants)

            await self._scheduler.cancel_boss_lobby_close(boss_fight_id=saved.id)
            await self._scheduler.cancel_boss_round_tick(boss_fight_id=saved.id)
            await self._scheduler.cancel_boss_fight_finish(boss_fight_id=saved.id)

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.BOSS_FIGHT_CANCELLED,
                    actor_id=player.tg_id,
                    target_kind="boss_fight",
                    target_id=str(saved.id),
                    before={"status": boss_fight.status.value},
                    after={
                        "status": saved.status.value,
                        "cancelled_at": now.isoformat(),
                        "participants_count": len(participants),
                    },
                    reason="boss_fight_cancelled_by_summoner",
                    idempotency_key=f"boss_fight_cancelled:{saved.id}",
                    occurred_at=now,
                )
            )

        self._business_metrics.dec_raid_active()
        self._business_metrics.inc_raid_outcome("cancelled")
        return BossFightCancelled(boss_fight=saved, was_already_cancelled=False)

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
        if boss_fight.status is BossFightStatus.LOBBY:
            return
        assert boss_fight.id is not None
        raise InvalidBossFightStateError(
            boss_fight_id=boss_fight.id,
            expected=BossFightStatus.LOBBY.value,
            actual=boss_fight.status.value,
        )

    async def _fetch_player(self, *, tg_id: int) -> Player:
        player = await self._players.get_by_tg_id(tg_id)
        if player is None:
            raise PlayerNotFoundError(tg_id=tg_id)
        return player

    @staticmethod
    def _ensure_summoner(*, boss_fight: BossFight, player: Player) -> None:
        assert player.id is not None
        assert boss_fight.id is not None
        if boss_fight.summoner_player_id != player.id:
            raise NotAuthorizedToCancelBossError(
                boss_fight_id=boss_fight.id,
                player_id=player.id,
                summoner_player_id=boss_fight.summoner_player_id,
            )

    async def _release_locks(
        self,
        *,
        boss_fight: BossFight,
        participants: tuple[BossParticipant, ...],
    ) -> None:
        seen: set[int] = set()
        for participant in participants:
            if participant.player_id in seen:
                continue
            seen.add(participant.player_id)
            await self._locks.release(
                actor_kind="player",
                actor_id=participant.player_id,
            )
        if boss_fight.boss_player_id not in seen:
            await self._locks.release(
                actor_kind="player",
                actor_id=boss_fight.boss_player_id,
            )


__all__ = [
    "BossFightCancelled",
    "CancelBossFight",
]
