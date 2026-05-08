"""Use-case `JoinCaravanLobby` (Спринт 3.2-B, ГДД §9.4 — §9.5).

Игрок жмёт «Вступить как <role>» под объявлением каравана:

1. Открывается ambient-`IUnitOfWork`.
2. Резолвится караван (`ICaravanRepository.get_by_id`):
   - не найден → `CaravanNotFoundError`;
   - `status != LOBBY` → `CaravanLobbyClosedError`.
3. Резолвится игрок (`IPlayerRepository.get_by_tg_id`):
   - не найден → `PlayerNotFoundError`;
   - `FROZEN`/`BANNED` → `PlayerFrozenError`.
4. Игрок ещё не участник этого каравана (UNIQUE `(caravan_id, player_id)`)
   — иначе `AlreadyInCaravanError(player_id=...)`.
5. Валидация роли (ГДД §9.4):
   - `CARAVANEER` — игрок должен состоять в `sender_clan_id`;
   - `DEFENDER` — игрок должен состоять в `receiver_clan_id`;
   - `RAIDER` — игрок не должен состоять ни в `sender_clan_id`,
     ни в `receiver_clan_id` (в третьем клане можно).
   На уровне БД-модели игрок состоит максимум в одном клане
   (см. `IClanMembershipRepository.get_by_player`), так что
   «двойное членство» из ГДД §9.4 — академический case; здесь
   достаточно сравнить `membership.clan_id` с `sender`/`receiver`-id.
6. Минимальный уровень толщины (ГДД §9.5):
   - `RAIDER` — `>= caravans.min_thickness_level_raider` (=5);
   - `CARAVANEER`/`DEFENDER` — нет требования.
7. Длинные требования (ГДД §9.2):
   - `CARAVANEER` — `length - contribution_cm >= 20 см`;
   - `DEFENDER`/`RAIDER` — `length >= 20 см` (общая база).
8. Capacity (ГДД §9.5):
   - `RAIDER` count `<=` `max_raiders_per_caravaneer × CARAVANEER count`;
   - `DEFENDER` count `<=` `max_defenders_per_caravaneer × CARAVANEER count`.
   Считаем ДО добавления нового участника, чтобы предел был «после
   входа этого игрока» (`new_count <= cap`).
9. Берётся `activity_lock(player, CARAVAN, ttl)`. TTL — оставшееся
   время лобби + battle_minutes (чтобы лок снимался не раньше конца боя).
10. Сохраняется `CaravanParticipant` через `add(...)`.
11. Audit `CARAVAN_PLAYER_JOINED` (idempotency-key
    `caravan_player_joined:{caravan_id}:{player_id}`).
12. Возвращается `JoinedCaravanLobby`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from pipirik_wars.application.dto.inputs import JoinCaravanLobbyInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance import CaravansConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.caravan import (
    AlreadyInCaravanError,
    Caravan,
    CaravanCapacityExceededError,
    CaravanContribution,
    CaravanLobbyClosedError,
    CaravanNotFoundError,
    CaravanParticipant,
    CaravanRequirementError,
    CaravanRole,
    CaravanRoleConflictError,
    ICaravanParticipantRepository,
    ICaravanRepository,
)
from pipirik_wars.domain.clan import IClanMembershipRepository
from pipirik_wars.domain.player import IPlayerRepository, Player, PlayerStatus
from pipirik_wars.domain.player.errors import PlayerFrozenError, PlayerNotFoundError
from pipirik_wars.domain.security import LockAlreadyHeldError, LockReason
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)

# Минимальная длина для входа в караван в любой роли (ГДД §9.2 «правило 20 см»).
# Числа в `CaravansConfig.min_length_cm`/`min_length_after_contribution_cm` —
# 20 / 20; используем `min_length_cm` как общий «нижний пол».
_ROLE_TO_AUDIT_ROLE: Final[dict[CaravanRole, str]] = {
    CaravanRole.CARAVANEER: "caravaneer",
    CaravanRole.DEFENDER: "defender",
    CaravanRole.RAIDER: "raider",
}


@dataclass(frozen=True, slots=True)
class JoinedCaravanLobby:
    """Результат успешного `JoinCaravanLobby`."""

    caravan: Caravan
    participant: CaravanParticipant


class JoinCaravanLobby:
    """Use-case «игрок вступил в лобби каравана» (ГДД §9.4 — §9.5)."""

    __slots__ = (
        "_audit",
        "_balance",
        "_caravan_participants",
        "_caravans",
        "_clan_members",
        "_clock",
        "_locks",
        "_players",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        caravans: ICaravanRepository,
        caravan_participants: ICaravanParticipantRepository,
        clan_members: IClanMembershipRepository,
        players: IPlayerRepository,
        locks: ActivityLockService,
        balance: IBalanceConfig,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._caravans = caravans
        self._caravan_participants = caravan_participants
        self._clan_members = clan_members
        self._players = players
        self._locks = locks
        self._balance = balance
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: JoinCaravanLobbyInput) -> JoinedCaravanLobby:
        """Вступить в лобби каравана. См. docstring модуля для контракта."""
        async with self._uow:
            cfg = self._balance.get().caravans
            now = self._clock.now()

            caravan = await self._fetch_caravan(caravan_id=input_dto.caravan_id)
            self._ensure_lobby(caravan=caravan)

            player = await self._fetch_player(tg_id=input_dto.tg_id)
            assert player.id is not None
            self._ensure_player_active(player=player)

            await self._ensure_not_yet_participant(
                caravan_id=caravan.id,  # type: ignore[arg-type]
                player_id=player.id,
            )

            requested_role = _parse_role(input_dto.role)
            await self._ensure_role_allowed(
                caravan=caravan,
                player_id=player.id,
                requested_role=requested_role,
            )
            self._ensure_thickness(player=player, role=requested_role, cfg=cfg)
            self._ensure_length(
                player=player,
                role=requested_role,
                contribution_cm=input_dto.contribution_cm,
                cfg=cfg,
            )
            await self._ensure_capacity(caravan=caravan, role=requested_role, cfg=cfg)

            await self._acquire_lock(
                player_id=player.id,
                ttl=self._lock_ttl(caravan=caravan, now=now, cfg=cfg),
            )

            participant = self._build_participant(
                caravan_id=caravan.id,  # type: ignore[arg-type]
                player_id=player.id,
                role=requested_role,
                contribution_cm=input_dto.contribution_cm,
                now=now,
            )
            stored = await self._caravan_participants.add(participant)

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.CARAVAN_PLAYER_JOINED,
                    actor_id=player.tg_id,
                    target_kind="caravan",
                    target_id=str(caravan.id),
                    before=None,
                    after={
                        "caravan_id": caravan.id,
                        "player_id": player.id,
                        "role": _ROLE_TO_AUDIT_ROLE[requested_role],
                        "contribution_cm": input_dto.contribution_cm,
                    },
                    reason="caravan_player_joined",
                    idempotency_key=(f"caravan_player_joined:{caravan.id}:{player.id}"),
                    occurred_at=now,
                )
            )

        return JoinedCaravanLobby(caravan=caravan, participant=stored)

    # -------- helpers --------

    async def _fetch_caravan(self, *, caravan_id: int) -> Caravan:
        caravan = await self._caravans.get_by_id(caravan_id=caravan_id)
        if caravan is None:
            raise CaravanNotFoundError(caravan_id=caravan_id)
        if caravan.id is None:  # pragma: no cover — защитный invariant
            raise RuntimeError("caravan loaded without id; repository contract violation")
        return caravan

    @staticmethod
    def _ensure_lobby(*, caravan: Caravan) -> None:
        if not caravan.is_in_lobby:
            assert caravan.id is not None
            raise CaravanLobbyClosedError(
                caravan_id=caravan.id,
                status=caravan.status.value,
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

    async def _ensure_not_yet_participant(
        self,
        *,
        caravan_id: int,
        player_id: int,
    ) -> None:
        existing = await self._caravan_participants.list_by_caravan(
            caravan_id=caravan_id,
        )
        for participant in existing:
            if participant.player_id == player_id:
                raise AlreadyInCaravanError(player_id=player_id)

    async def _ensure_role_allowed(
        self,
        *,
        caravan: Caravan,
        player_id: int,
        requested_role: CaravanRole,
    ) -> None:
        membership = await self._clan_members.get_by_player(player_id)
        clan_id = membership.clan_id if membership is not None else None

        if requested_role is CaravanRole.CARAVANEER:
            if clan_id != caravan.sender_clan_id:
                raise CaravanRoleConflictError(
                    player_id=player_id,
                    attempted_role="caravaneer",
                    reason=("player must be a member of the sender clan to join as caravaneer"),
                )
        elif requested_role is CaravanRole.DEFENDER:
            if clan_id != caravan.receiver_clan_id:
                raise CaravanRoleConflictError(
                    player_id=player_id,
                    attempted_role="defender",
                    reason=("player must be a member of the receiver clan to join as defender"),
                )
        elif requested_role is CaravanRole.RAIDER:
            if clan_id in {caravan.sender_clan_id, caravan.receiver_clan_id}:
                raise CaravanRoleConflictError(
                    player_id=player_id,
                    attempted_role="raider",
                    reason=(
                        "player must not be a member of either sender or receiver clan "
                        "to join as raider"
                    ),
                )
        else:  # pragma: no cover — `LEADER` фильтруется в `_parse_role`
            raise CaravanRoleConflictError(
                player_id=player_id,
                attempted_role=requested_role.value,
                reason=f"role {requested_role.value!r} cannot be requested via JoinCaravanLobby",
            )

    @staticmethod
    def _ensure_thickness(
        *,
        player: Player,
        role: CaravanRole,
        cfg: CaravansConfig,
    ) -> None:
        if role is not CaravanRole.RAIDER:
            return
        required = cfg.min_thickness_level_raider
        if player.thickness.level < required:
            assert player.id is not None
            raise CaravanRequirementError(
                player_id=player.id,
                requirement="thickness",
                required=required,
                actual=player.thickness.level,
            )

    @staticmethod
    def _ensure_length(
        *,
        player: Player,
        role: CaravanRole,
        contribution_cm: int | None,
        cfg: CaravansConfig,
    ) -> None:
        assert player.id is not None
        if role is CaravanRole.CARAVANEER:
            assert contribution_cm is not None  # валидируется на DTO-уровне
            remaining = player.length.cm - contribution_cm
            required = cfg.min_length_after_contribution_cm
            if remaining < required:
                raise CaravanRequirementError(
                    player_id=player.id,
                    requirement="length_after_contribution",
                    required=required,
                    actual=remaining,
                )
            return
        required = cfg.min_length_cm
        if player.length.cm < required:
            raise CaravanRequirementError(
                player_id=player.id,
                requirement="length_total",
                required=required,
                actual=player.length.cm,
            )

    async def _ensure_capacity(
        self,
        *,
        caravan: Caravan,
        role: CaravanRole,
        cfg: CaravansConfig,
    ) -> None:
        if role is CaravanRole.CARAVANEER:
            return
        caravaneers = await self._caravan_participants.list_by_caravan_and_role(
            caravan_id=caravan.id,  # type: ignore[arg-type]
            role=CaravanRole.CARAVANEER,
        )
        same_role = await self._caravan_participants.list_by_caravan_and_role(
            caravan_id=caravan.id,  # type: ignore[arg-type]
            role=role,
        )
        if role is CaravanRole.RAIDER:
            cap = cfg.max_raiders_per_caravaneer * len(caravaneers)
        else:  # DEFENDER
            cap = cfg.max_defenders_per_caravaneer * len(caravaneers)
        new_count = len(same_role) + 1
        if new_count > cap:
            assert caravan.id is not None
            raise CaravanCapacityExceededError(
                caravan_id=caravan.id,
                role=_ROLE_TO_AUDIT_ROLE[role],
                limit=cap,
            )

    @staticmethod
    def _lock_ttl(*, caravan: Caravan, now: datetime, cfg: CaravansConfig) -> timedelta:
        # Лок держим до самого конца боя (`battle_ends_at`), но не меньше
        # чем `battle_minutes` (если игрок зашёл в самые последние секунды
        # лобби, остаток до `lobby_ends_at` стремится к 0). На случай
        # «отрицательного» остатка кладём минимум `battle_minutes`.
        remaining = caravan.battle_ends_at - now
        minimum = timedelta(minutes=cfg.battle_minutes)
        if remaining < minimum:
            return minimum
        return remaining

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

    @staticmethod
    def _build_participant(
        *,
        caravan_id: int,
        player_id: int,
        role: CaravanRole,
        contribution_cm: int | None,
        now: datetime,
    ) -> CaravanParticipant:
        if role is CaravanRole.CARAVANEER:
            assert contribution_cm is not None  # DTO-валидация
            return CaravanParticipant.caravaneer(
                caravan_id=caravan_id,
                player_id=player_id,
                contribution=CaravanContribution(cm=contribution_cm),
                is_leader=False,
                joined_at=now,
            )
        if role is CaravanRole.DEFENDER:
            return CaravanParticipant.defender(
                caravan_id=caravan_id,
                player_id=player_id,
                joined_at=now,
            )
        if role is CaravanRole.RAIDER:
            return CaravanParticipant.raider(
                caravan_id=caravan_id,
                player_id=player_id,
                joined_at=now,
            )
        raise RuntimeError(  # pragma: no cover
            f"JoinCaravanLobby: unsupported role {role.value!r}",
        )


def _parse_role(role: str) -> CaravanRole:
    """`Literal["caravaneer", "defender", "raider"]` → `CaravanRole`.

    DTO-уровень не пускает `LEADER`-строку (тип-литерал), но мы и здесь
    защищаемся — `LEADER` не может быть запрошен через `JoinCaravanLobby`
    (роль выдаётся только в `CreateCaravan`).
    """
    if role == "caravaneer":
        return CaravanRole.CARAVANEER
    if role == "defender":
        return CaravanRole.DEFENDER
    if role == "raider":
        return CaravanRole.RAIDER
    raise ValueError(  # pragma: no cover — DTO Literal не пропустит
        f"JoinCaravanLobby: unsupported role {role!r}",
    )


__all__ = [
    "JoinCaravanLobby",
    "JoinedCaravanLobby",
]
