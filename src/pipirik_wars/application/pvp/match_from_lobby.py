"""Use-case `MatchFromLobby` (Спринт 2.1.F.2, ГДД §7.1).

Пикап дуэли из глобального FIFO-лобби: игрок дёрнул `/duel_global`,
мы вынимаем старейший вызов и принимаем его (логика как `AcceptDuel`).
Если лобби пустое — возвращаем специальный результат.

Алгоритм:

1. Загружаем `Player` по `tg_id`. Нет — `PlayerNotFoundError`.
2. Anti-cheat soft-ban-гейт + PvP-требования.
3. `lobby.pop_oldest()` — атомарно вытаскивает FIFO-голову. Если
   `None`, возвращаем `EmptyLobby` без побочных эффектов.
4. Загружаем `Duel`. Если её нет (сирота-запись после CASCADE-удалёния
   `pvp_duels`) — возвращаем `LobbyEntryStale`.
5. Если `state != PENDING_ACCEPT` (race с cancel/expire) — возвращаем
   `LobbyEntryStale`.
6. Self-challenge-edge: если `challenger_id == accepter.id`, кладём
   запись обратно в лобби и возвращаем `LobbyEntryStale(reason="self")`.
   Альтернатива (брать следующую) — overkill для первой версии; в
   конкуренции этот игрок просто попробует `/duel_global` ещё раз.
7. Берём lock на принимающего; вызываем `Duel.accept(...)`.
8. `IDuelRepository.save(...)`.
9. Сохраняем audit `PVP_DUEL_ACCEPTED` + `PVP_LOBBY_MATCHED`.
10. Снаружи UoW — `scheduler.cancel_global_lobby_expiration(duel_id)`.

Любая ошибка после `pop_oldest` ведёт к откату транзакции, **но**
запись из лобби уже удалена (pop_oldest = SELECT + DELETE атомарно).
Это намеренно: повторное появление того же вызова в лобби — задача
recovery-hook-а на старте бота (Спринт 1.3.D-style).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from pipirik_wars.application.dto.inputs import MatchFromLobbyInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.anticheat import AnticheatGuard
from pipirik_wars.domain.balance import PvpDuel1v1Config
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.pvp import (
    Duel,
    DuelState,
    IDuelRepository,
    PvpRequirementsNotMetError,
)
from pipirik_wars.domain.pvp.lobby import IGlobalLobbyRepository
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IUnitOfWork,
)

_DEFAULT_DUEL_LOCK_TTL = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class DuelMatched:
    """Дуэль успешно сматчена и переведена в IN_PROGRESS."""

    duel: Duel


@dataclass(frozen=True, slots=True)
class EmptyLobby:
    """В лобби не было ни одного вызова."""


@dataclass(frozen=True, slots=True)
class LobbyEntryStale:
    """Pop-нутая запись больше не валидна (race / self-challenge)."""

    reason: str


class MatchFromLobby:
    """Use-case «забрать вызов из глобального FIFO-лобби»."""

    __slots__ = (
        "_audit",
        "_balance",
        "_clock",
        "_duels",
        "_lobby",
        "_locks",
        "_players",
        "_scheduler",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        duels: IDuelRepository,
        lobby: IGlobalLobbyRepository,
        locks: ActivityLockService,
        scheduler: IDelayedJobScheduler,
        balance: IBalanceConfig,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._duels = duels
        self._lobby = lobby
        self._locks = locks
        self._scheduler = scheduler
        self._balance = balance
        self._audit = audit
        self._clock = clock

    async def execute(
        self,
        input_dto: MatchFromLobbyInput,
    ) -> DuelMatched | EmptyLobby | LobbyEntryStale:
        """Сматчить принимающего с FIFO-головой лобби."""

        cancel_expiration_for: int | None = None
        async with self._uow:
            accepter = await self._players.get_by_tg_id(input_dto.accepter_tg_id)
            if accepter is None:
                raise PlayerNotFoundError(tg_id=input_dto.accepter_tg_id)

            now = self._clock.now()
            cfg = self._balance.get().pvp.duel_1v1
            AnticheatGuard.require_unlocked(accepter, now=now)
            self._require_pvp_eligible(player=accepter, cfg=cfg)

            entry = await self._lobby.pop_oldest()
            if entry is None:
                return EmptyLobby()

            duel = await self._duels.get_by_id(duel_id=entry.duel_id)
            if duel is None:
                return LobbyEntryStale(reason="duel_not_found")
            if duel.state is not DuelState.PENDING_ACCEPT:
                return LobbyEntryStale(reason="not_pending_accept")

            accepter_id = self._require_id(accepter)
            if duel.challenger_id == accepter_id:
                # вернуть запись обратно — уже не FIFO-голова, но это
                # acceptable trade-off для первой версии (race-edge case).
                await self._lobby.enqueue(
                    duel_id=entry.duel_id,
                    enqueued_at=entry.enqueued_at,
                )
                return LobbyEntryStale(reason="self_challenge")

            challenger = await self._players.get_by_id(
                player_id=duel.challenger_id,
            )
            if challenger is None:
                raise PlayerNotFoundError(tg_id=duel.challenger_id)

            await self._locks.acquire(
                actor_kind="player",
                actor_id=accepter_id,
                reason=LockReason.PVP,
                ttl=_DEFAULT_DUEL_LOCK_TTL,
            )

            accepted = duel.accept(
                accepter_id=accepter_id,
                p1_length_cm=challenger.length.cm,
                p2_length_cm=accepter.length.cm,
                now=now,
            )
            saved = await self._duels.save(accepted)

            assert saved.id is not None
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PVP_DUEL_ACCEPTED,
                    actor_id=accepter.tg_id,
                    target_kind="pvp_duel",
                    target_id=str(saved.id),
                    before={"state": duel.state.value},
                    after={
                        "state": saved.state.value,
                        "challenged_id": saved.challenged_id,
                        "p1_length_cm": saved.p1_initial_length_cm,
                        "p2_length_cm": saved.p2_initial_length_cm,
                    },
                    reason="pvp_duel_accepted_via_lobby",
                    idempotency_key=f"pvp_duel_accepted:{saved.id}",
                    occurred_at=now,
                )
            )
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PVP_LOBBY_MATCHED,
                    actor_id=accepter.tg_id,
                    target_kind="pvp_duel",
                    target_id=str(saved.id),
                    before=None,
                    after={"accepter_id": accepter_id},
                    reason="pvp_lobby_matched",
                    idempotency_key=f"pvp_lobby_matched:{saved.id}",
                    occurred_at=now,
                )
            )
            cancel_expiration_for = saved.id

        if cancel_expiration_for is not None:
            await self._scheduler.cancel_global_lobby_expiration(
                duel_id=cancel_expiration_for,
            )
        return DuelMatched(duel=saved)

    @staticmethod
    def _require_id(player: Player) -> int:
        if player.id is None:
            raise RuntimeError(
                f"Player tg_id={player.tg_id} loaded without id; repository contract violation",
            )
        return player.id

    @staticmethod
    def _require_pvp_eligible(
        *,
        player: Player,
        cfg: PvpDuel1v1Config,
    ) -> None:
        if player.length.cm < cfg.min_length_cm:
            raise PvpRequirementsNotMetError(
                tg_id=player.tg_id,
                requirement="length",
                required=cfg.min_length_cm,
                actual=player.length.cm,
            )
        if player.thickness.level < cfg.min_thickness_level:
            raise PvpRequirementsNotMetError(
                tg_id=player.tg_id,
                requirement="thickness",
                required=cfg.min_thickness_level,
                actual=player.thickness.level,
            )


__all__ = [
    "DuelMatched",
    "EmptyLobby",
    "LobbyEntryStale",
    "MatchFromLobby",
]
