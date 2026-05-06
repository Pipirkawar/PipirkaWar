"""Use-case `StartMassDuel` (Спринт 2.2.E, ГДД §7.2 / 2.2.2).

Старт массового PvP-боя клан×клан:

1. Резолвит оба клана по `chat_id` (`IClanRepository.get_by_chat_id`).
   Любой не найден — `IntegrityError` (handler должен был сначала зарегистрировать клан).
   Любой `frozen` — `ClanFrozenError`.
2. Запрашивает roster обеих сторон через
   `IClanMembershipRepository.list_by_clan` и подгружает `Player`-ы по
   `player_id` (через `IPlayerRepository.get_by_id`).
3. Игроки в обоих кланах одновременно (теоретически невозможно — БД
   гарантирует UNIQUE(player_id), но защищаемся) → исключаются из обеих
   сторон (ГДД §7.2 / 2.2.3 — нельзя сражаться против самого себя).
4. Каждый участник проходит eligibility-фильтр:
   * `status == ACTIVE` (frozen-игроки не воюют);
   * `length_cm ≥ balance.pvp.mass_duel.min_length_cm`;
   * `thickness_level ≥ balance.pvp.mass_duel.min_thickness_level`.
5. Если у любой стороны после фильтрации остаётся 0 eligible-участников
   → `MassDuelNoParticipantsError`.
6. Cooldown: `find_most_recent_for_clan` для каждого из двух кланов;
   если у любого клана последний mass-duel создан меньше чем
   `cooldown_hours` назад — `MassDuelCooldownError`.
7. Берёт activity-lock на каждого eligible-участника (с TTL `lock_ttl`).
   На любом конфликте — `LockAlreadyHeldError`. Уже взятые локи в
   рамках UoW откатятся транзакцией.
8. Создаёт `MassDuel.create_battle(...)` с `hit_pct` из
   `balance.pvp.duel_1v1` (массовый PvP использует ту же 3×3-матрицу
   урона) и сохраняет через `IMassDuelRepository.add(...)`.
9. Audit `PVP_MASS_DUEL_CREATED` (idempotency-key
   `pvp_mass_duel_created:{duel_id}`).

Транзакция — ambient `IUnitOfWork`. Любая ошибка откатывает всё —
участники не остаются с висящими PvP-локами.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pipirik_wars.application.dto.inputs import StartMassDuelInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance import PvpMassDuelConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.clan import (
    Clan,
    ClanFrozenError,
    IClanMembershipRepository,
    IClanRepository,
)
from pipirik_wars.domain.player import IPlayerRepository, Player, PlayerStatus
from pipirik_wars.domain.pvp import (
    IMassDuelRepository,
    MassDuel,
    MassDuelCooldownError,
    MassDuelNoParticipantsError,
)
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IUnitOfWork,
)
from pipirik_wars.shared.errors import IntegrityError

# TTL активити-лока на стороне массового боя: с запасом на максимально
# ожидаемую длительность боя (один тик + резерв на AFK-таймер).
# 30 минут симметрично 1×1-PvP — шедулер 2.2.F снимет лок раньше.
_DEFAULT_MASS_DUEL_LOCK_TTL = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class MassDuelStarted:
    """Результат старта массового боя."""

    duel: MassDuel


class StartMassDuel:
    """Use-case «начать массовый PvP-бой клан×клан»."""

    __slots__ = (
        "_audit",
        "_balance",
        "_clan_members",
        "_clans",
        "_clock",
        "_duels",
        "_lock_ttl",
        "_locks",
        "_players",
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
        duels: IMassDuelRepository,
        locks: ActivityLockService,
        balance: IBalanceConfig,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler | None = None,
        lock_ttl: timedelta = _DEFAULT_MASS_DUEL_LOCK_TTL,
    ) -> None:
        self._uow = uow
        self._clans = clans
        self._clan_members = clan_members
        self._players = players
        self._duels = duels
        self._locks = locks
        self._balance = balance
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler
        self._lock_ttl = lock_ttl

    async def execute(self, input_dto: StartMassDuelInput) -> MassDuelStarted:
        """Стартовать массовый бой. Бросает:

        - `IntegrityError` — один из клановых `chat_id` не зарегистрирован;
        - `ClanFrozenError` — клан-атакующий или клан-защитник заморожен;
        - `MassDuelCooldownError` — у любой стороны кулдаун ещё не истёк;
        - `MassDuelNoParticipantsError` — у любой стороны 0 eligible-участников;
        - `LockAlreadyHeldError` — кто-то из eligible-участников уже занят.
        """

        async with self._uow:
            now = self._clock.now()
            cfg = self._balance.get().pvp.mass_duel
            duel_1v1_cfg = self._balance.get().pvp.duel_1v1

            attacker = await self._fetch_clan(chat_id=input_dto.attacker_chat_id)
            defender = await self._fetch_clan(chat_id=input_dto.defender_chat_id)
            if attacker.is_frozen:
                raise ClanFrozenError(chat_id=attacker.chat_id)
            if defender.is_frozen:
                raise ClanFrozenError(chat_id=defender.chat_id)

            assert attacker.id is not None
            assert defender.id is not None

            await self._check_cooldown(clan_id=attacker.id, cfg=cfg, now=now)
            await self._check_cooldown(clan_id=defender.id, cfg=cfg, now=now)

            attacker_lengths = await self._collect_eligible(clan_id=attacker.id, cfg=cfg)
            defender_lengths = await self._collect_eligible(clan_id=defender.id, cfg=cfg)

            # Cross-clan-overlap (ГДД §7.2 / 2.2.3): если кто-то числится
            # в обоих ростерах — выкидываем из обоих, чтобы не сражаться
            # против самого себя. БД-инвариант UNIQUE(player_id) делает
            # это маловероятным, но защитный код дешёвый.
            overlap = set(attacker_lengths) & set(defender_lengths)
            if overlap:
                for pid in overlap:
                    attacker_lengths.pop(pid, None)
                    defender_lengths.pop(pid, None)

            if not attacker_lengths:
                raise MassDuelNoParticipantsError(clan_id=attacker.id)
            if not defender_lengths:
                raise MassDuelNoParticipantsError(clan_id=defender.id)

            # Берём activity-lock на каждого участника. Любой
            # конфликт → LockAlreadyHeldError → транзакция откатится,
            # уже взятые локи освободятся вместе с rollback-ом.
            for pid in sorted({*attacker_lengths, *defender_lengths}):
                await self._locks.acquire(
                    actor_kind="player",
                    actor_id=pid,
                    reason=LockReason.PVP,
                    ttl=self._lock_ttl,
                )

            battle = MassDuel.create_battle(
                clan1_id=attacker.id,
                clan2_id=defender.id,
                clan1_lengths=attacker_lengths,
                clan2_lengths=defender_lengths,
                hit_pct=duel_1v1_cfg.hit_pct,
                now=now,
            )
            stored = await self._duels.add(battle)
            assert stored.id is not None

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PVP_MASS_DUEL_CREATED,
                    actor_id=input_dto.initiator_tg_id,
                    target_kind="pvp_mass_duel",
                    target_id=str(stored.id),
                    before=None,
                    after={
                        "clan1_id": stored.clan1_id,
                        "clan2_id": stored.clan2_id,
                        "clan1_size": len(stored.clan1_member_ids),
                        "clan2_size": len(stored.clan2_member_ids),
                        "hit_pct": stored.hit_pct,
                    },
                    reason="pvp_mass_duel_created",
                    idempotency_key=f"pvp_mass_duel_created:{stored.id}",
                    occurred_at=now,
                )
            )

            run_at = now + timedelta(seconds=cfg.move_timer_seconds)
            stored_id = stored.id

        # AFK-таймер ставим снаружи UoW (идемпотентная операция шедулера).
        # Если транзакция выше не упала — `stored_id` валиден, и таймер
        # будет соответствовать только что закоммиченному бою.
        if self._scheduler is not None:
            await self._scheduler.schedule_mass_duel_afk_resolution(
                duel_id=stored_id,
                run_at=run_at,
            )

        return MassDuelStarted(duel=stored)

    async def _fetch_clan(self, *, chat_id: int) -> Clan:
        clan = await self._clans.get_by_chat_id(chat_id)
        if clan is None:
            raise IntegrityError(
                f"chat_id={chat_id} is not a registered clan",
            )
        if clan.id is None:  # pragma: no cover — защитный invariant
            raise IntegrityError("clan was loaded without id")
        return clan

    async def _check_cooldown(
        self,
        *,
        clan_id: int,
        cfg: PvpMassDuelConfig,
        now: datetime,
    ) -> None:
        recent = await self._duels.find_most_recent_for_clan(clan_id=clan_id)
        if recent is None:
            return
        threshold = now - timedelta(hours=cfg.cooldown_hours)
        if recent.created_at >= threshold:
            raise MassDuelCooldownError(
                clan_id=clan_id,
                cooldown_hours=cfg.cooldown_hours,
            )

    async def _collect_eligible(
        self,
        *,
        clan_id: int,
        cfg: PvpMassDuelConfig,
    ) -> dict[int, int]:
        """Собрать `{player_id → length_cm}` всех eligible-участников клана."""

        members = await self._clan_members.list_by_clan(clan_id)
        result: dict[int, int] = {}
        for member in members:
            player = await self._players.get_by_id(player_id=member.player_id)
            if player is None:
                # Игрок пропал из БД — пропускаем (не считаем eligible).
                continue
            if not _is_eligible(player=player, cfg=cfg):
                continue
            assert player.id is not None
            result[player.id] = player.length.cm
        return result


def _is_eligible(*, player: Player, cfg: PvpMassDuelConfig) -> bool:
    if player.status is not PlayerStatus.ACTIVE:
        return False
    if player.length.cm < cfg.min_length_cm:
        return False
    return player.thickness.level >= cfg.min_thickness_level


__all__ = [
    "MassDuelStarted",
    "StartMassDuel",
]
