"""Use-case `CreateCaravan` (Спринт 3.2-B, ГДД §9.1 — §9.3).

Игрок-лидер клана-отправителя инициирует караван в чат
клана-получателя:

1. Открывается ambient-`IUnitOfWork` (всё ниже — в одной транзакции).
2. Резолвятся оба клана по `chat_id` (`IClanRepository.get_by_chat_id`):
   - не найден → `IntegrityError` (бот-handler должен сначала
     зарегистрировать клан);
   - `frozen` → `ClanFrozenError`.
3. Резолвится игрок (`IPlayerRepository.get_by_tg_id`):
   - не найден → `PlayerNotFoundError`;
   - `FROZEN`/`BANNED` → `PlayerFrozenError` (по DAU-gate).
4. Игрок должен состоять в клане-отправителе с `role=LEADER`
   (`IClanMembershipRepository.get_by_player`):
   - не состоит / другой клан / `MEMBER` → `CaravanRoleConflictError`.
5. У клана-отправителя нет другого активного каравана
   (`ICaravanRepository.get_active_by_clan`):
   - есть → `AlreadyInCaravanError(player_id=leader)`.
6. Кулдаун клана-отправителя истёк (ГДД §9.3 = 12 ч):
   `now - last_started_at >= clan_cooldown_hours`
   (`ICaravanRepository.get_last_finished_at_for_clan`).
   - не истёк → `CaravanCooldownError`.
7. Толщина игрока `>= caravans.min_thickness_level_leader` (ГДД §9.1 = 7).
8. Длина игрока ПОСЛЕ взноса `>= caravans.min_length_after_contribution_cm`
   (ГДД §9.2 = 20 см).
9. Берём `activity_lock(player, CARAVAN, ttl=lobby+battle minutes)`.
10. Создаём `Caravan.starting(...)`, сохраняем (`add` → `id`).
11. Создаём `CaravanParticipant.caravaneer(is_leader=True, contribution=...)`,
    сохраняем.
12. Планируем `caravan_lobby_close(caravan_id, run_at=lobby_ends_at)`.
13. Audit `CARAVAN_CREATED` (idempotency-key `caravan_created:{caravan_id}`).
14. Возвращаем `CaravanCreated`.

Транзакция — единая: любая ошибка откатывает запись каравана,
участника и активити-лок целиком.

Списание `contribution_cm` из длины игрока **не делается** на этом
шаге — это было сознательное решение (Спринт 3.2-A): длина списывается
только в момент `LOBBY → IN_BATTLE` через `CloseCaravanLobby` /
`FinishCaravanBattle` (Спринт 3.2-C). На стадии лобби лидер ещё может
выйти/отменить караван без штрафа.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pipirik_wars.application.dto.inputs import CreateCaravanInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.caravan import (
    AlreadyInCaravanError,
    Caravan,
    CaravanContribution,
    CaravanCooldownError,
    CaravanParticipant,
    CaravanRequirementError,
    CaravanRoleConflictError,
    ICaravanParticipantRepository,
    ICaravanRepository,
)
from pipirik_wars.domain.clan import (
    Clan,
    ClanFrozenError,
    ClanMemberRole,
    IClanMembershipRepository,
    IClanRepository,
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
from pipirik_wars.shared.errors import IntegrityError


@dataclass(frozen=True, slots=True)
class CaravanCreated:
    """Результат успешного `CreateCaravan`."""

    caravan: Caravan
    leader_participant: CaravanParticipant


class CreateCaravan:
    """Use-case «лидер клана создаёт караван» (ГДД §9.1 — §9.3)."""

    __slots__ = (
        "_audit",
        "_balance",
        "_caravan_participants",
        "_caravans",
        "_clan_members",
        "_clans",
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
        clans: IClanRepository,
        clan_members: IClanMembershipRepository,
        players: IPlayerRepository,
        caravans: ICaravanRepository,
        caravan_participants: ICaravanParticipantRepository,
        locks: ActivityLockService,
        balance: IBalanceConfig,
        random: IRandom,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler,
    ) -> None:
        self._uow = uow
        self._clans = clans
        self._clan_members = clan_members
        self._players = players
        self._caravans = caravans
        self._caravan_participants = caravan_participants
        self._locks = locks
        self._balance = balance
        self._random = random
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler

    async def execute(self, input_dto: CreateCaravanInput) -> CaravanCreated:
        """Создать караван. См. docstring модуля для контракта."""
        async with self._uow:
            cfg = self._balance.get().caravans
            now = self._clock.now()

            sender = await self._fetch_clan(chat_id=input_dto.sender_chat_id)
            receiver = await self._fetch_clan(chat_id=input_dto.receiver_chat_id)
            if sender.is_frozen:
                raise ClanFrozenError(chat_id=sender.chat_id)
            if receiver.is_frozen:
                raise ClanFrozenError(chat_id=receiver.chat_id)
            assert sender.id is not None
            assert receiver.id is not None

            player = await self._fetch_player(tg_id=input_dto.initiator_tg_id)
            assert player.id is not None
            self._ensure_player_active(player=player)
            await self._ensure_player_is_clan_leader(
                player_id=player.id,
                sender_clan_id=sender.id,
            )
            self._ensure_thickness(player=player, required=cfg.min_thickness_level_leader)
            self._ensure_length_after_contribution(
                player=player,
                contribution_cm=input_dto.contribution_cm,
                required=cfg.min_length_after_contribution_cm,
            )

            await self._ensure_no_active_caravan(clan_id=sender.id, player_id=player.id)
            await self._ensure_cooldown_expired(
                clan_id=sender.id,
                cooldown_hours=cfg.clan_cooldown_hours,
                now=now,
            )

            lobby_ends_at = now + timedelta(minutes=cfg.lobby_minutes)
            battle_ends_at = lobby_ends_at + timedelta(minutes=cfg.battle_minutes)
            await self._acquire_lock(
                player_id=player.id,
                ttl=lobby_ends_at + timedelta(minutes=cfg.battle_minutes) - now,
            )

            random_seed = self._random.randint(0, 2**31 - 1)
            caravan = Caravan.starting(
                sender_clan_id=sender.id,
                receiver_clan_id=receiver.id,
                leader_player_id=player.id,
                started_at=now,
                lobby_ends_at=lobby_ends_at,
                battle_ends_at=battle_ends_at,
                random_seed=random_seed,
            )
            saved = await self._caravans.add(caravan)
            assert saved.id is not None

            leader_participant = CaravanParticipant.caravaneer(
                caravan_id=saved.id,
                player_id=player.id,
                contribution=CaravanContribution(cm=input_dto.contribution_cm),
                is_leader=True,
                joined_at=now,
            )
            stored_leader = await self._caravan_participants.add(leader_participant)

            await self._scheduler.schedule_caravan_lobby_close(
                caravan_id=saved.id,
                run_at=saved.lobby_ends_at,
            )

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.CARAVAN_CREATED,
                    actor_id=player.tg_id,
                    target_kind="caravan",
                    target_id=str(saved.id),
                    before=None,
                    after={
                        "sender_clan_id": saved.sender_clan_id,
                        "receiver_clan_id": saved.receiver_clan_id,
                        "leader_player_id": saved.leader_player_id,
                        "started_at": saved.started_at.isoformat(),
                        "lobby_ends_at": saved.lobby_ends_at.isoformat(),
                        "battle_ends_at": saved.battle_ends_at.isoformat(),
                        "random_seed": saved.random_seed,
                        "leader_contribution_cm": input_dto.contribution_cm,
                    },
                    reason="caravan_created",
                    idempotency_key=f"caravan_created:{saved.id}",
                    occurred_at=now,
                )
            )

        return CaravanCreated(caravan=saved, leader_participant=stored_leader)

    # -------- helpers --------

    async def _fetch_clan(self, *, chat_id: int) -> Clan:
        clan = await self._clans.get_by_chat_id(chat_id)
        if clan is None:
            raise IntegrityError(f"chat_id={chat_id} is not a registered clan")
        if clan.id is None:  # pragma: no cover — защитный invariant
            raise IntegrityError("clan was loaded without id")
        return clan

    async def _fetch_player(self, *, tg_id: int) -> Player:
        player = await self._players.get_by_tg_id(tg_id)
        if player is None:
            raise PlayerNotFoundError(tg_id=tg_id)
        return player

    @staticmethod
    def _ensure_player_active(*, player: Player) -> None:
        if player.status is not PlayerStatus.ACTIVE:
            raise PlayerFrozenError(tg_id=player.tg_id)

    async def _ensure_player_is_clan_leader(
        self,
        *,
        player_id: int,
        sender_clan_id: int,
    ) -> None:
        membership = await self._clan_members.get_by_player(player_id)
        if membership is None or membership.clan_id != sender_clan_id:
            raise CaravanRoleConflictError(
                player_id=player_id,
                attempted_role="leader",
                reason=(
                    "player is not a member of the sender clan"
                    if membership is None
                    else f"player is in clan_id={membership.clan_id}, "
                    f"not sender_clan_id={sender_clan_id}"
                ),
            )
        if membership.role is not ClanMemberRole.LEADER:
            raise CaravanRoleConflictError(
                player_id=player_id,
                attempted_role="leader",
                reason=f"player has role {membership.role.value!r}, expected 'leader'",
            )

    @staticmethod
    def _ensure_thickness(*, player: Player, required: int) -> None:
        if player.thickness.level < required:
            assert player.id is not None
            raise CaravanRequirementError(
                player_id=player.id,
                requirement="thickness",
                required=required,
                actual=player.thickness.level,
            )

    @staticmethod
    def _ensure_length_after_contribution(
        *,
        player: Player,
        contribution_cm: int,
        required: int,
    ) -> None:
        remaining = player.length.cm - contribution_cm
        if remaining < required:
            assert player.id is not None
            raise CaravanRequirementError(
                player_id=player.id,
                requirement="length_after_contribution",
                required=required,
                actual=remaining,
            )

    async def _ensure_no_active_caravan(self, *, clan_id: int, player_id: int) -> None:
        existing = await self._caravans.get_active_by_clan(clan_id=clan_id)
        if existing is not None:
            raise AlreadyInCaravanError(player_id=player_id)

    async def _ensure_cooldown_expired(
        self,
        *,
        clan_id: int,
        cooldown_hours: int,
        now: datetime,
    ) -> None:
        if cooldown_hours <= 0:
            return
        last_started_at = await self._caravans.get_last_finished_at_for_clan(
            clan_id=clan_id,
        )
        if last_started_at is None:
            return
        threshold = last_started_at + timedelta(hours=cooldown_hours)
        if now < threshold:
            remaining = int((threshold - now).total_seconds())
            raise CaravanCooldownError(
                clan_id=clan_id,
                actual_remaining_seconds=remaining,
            )

    async def _acquire_lock(self, *, player_id: int, ttl: timedelta) -> None:
        try:
            await self._locks.acquire(
                actor_kind="player",
                actor_id=player_id,
                reason=LockReason.CARAVAN,
                ttl=ttl,
            )
        except LockAlreadyHeldError as exc:
            raise AlreadyInCaravanError(player_id=player_id) from exc


__all__ = [
    "CaravanCreated",
    "CreateCaravan",
]
