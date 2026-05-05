"""Use-case `AcceptDuel` (Спринт 2.1.D, ГДД §7.1).

Игрок принимает PvP-вызов:

1. Загружает `Duel` по `duel_id`. Нет — `DuelNotFoundError`.
2. Загружает `Player` по `tg_id` принимающего. Нет — `PlayerNotFoundError`.
3. Anti-cheat soft-ban-гейт через `AnticheatGuard.require_unlocked`.
4. PvP-требования (длина ≥ `min_length_cm`, толщина ≥
   `min_thickness_level`). Иначе — `PvpRequirementsNotMetError`.
5. Загружает челленджера (`duel.challenger_id`) — нужен снимок длины
   как `p1_initial_length_cm` для path-independent резолва.
6. Берёт activity-lock на принимающего (`actor_kind="player"`,
   `actor_id=player.id`, `reason=PVP`). Если занят — `LockAlreadyHeldError`.
   Лок челленджера уже взят `ChallengeDuel`.
7. `Duel.accept(...)` — переход PENDING_ACCEPT → IN_PROGRESS, снапшот
   длин, инициализация `pending_round=1`. Доменные ошибки
   (`InvalidDuelStateError`, `NotADuelParticipantError`) пробрасываются.
8. Сохраняет через `IDuelRepository.save(...)`.
9. Audit `PVP_DUEL_ACCEPTED` со снимком обеих длин и режимом.

Для `GLOBAL_ONLY` принимающий становится `challenged_id` (кто первый
успел нажать «принять» — тот и оппонент). Для адресных режимов
`accepter_id` обязан совпадать с `challenged_id`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from pipirik_wars.application.dto.inputs import AcceptDuelInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.anticheat import AnticheatGuard
from pipirik_wars.domain.balance import PvpDuel1v1Config
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelNotFoundError,
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

# TTL активити-лока на стороне принимающего: симметрично с челленджером,
# с запасом на 3 раунда × 60 сек. Шедулер 2.1.G снимет лок раньше.
_DEFAULT_DUEL_LOCK_TTL = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class DuelAccepted:
    """Результат успешного принятия вызова."""

    duel: Duel


class AcceptDuel:
    """Use-case «принять PvP-вызов»."""

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
        locks: ActivityLockService,
        balance: IBalanceConfig,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler | None = None,
        lobby: IGlobalLobbyRepository | None = None,
    ) -> None:
        self._uow = uow
        self._players = players
        self._duels = duels
        self._locks = locks
        self._balance = balance
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler
        self._lobby = lobby

    async def execute(self, input_dto: AcceptDuelInput) -> DuelAccepted:
        """Принять вызов. Бросает:

        - `DuelNotFoundError` — дуэли с таким `duel_id` нет;
        - `PlayerNotFoundError` — принимающего или челленджера нет в БД;
        - `AnticheatSoftBanError` — принимающий в soft-ban-е;
        - `PvpRequirementsNotMetError` — длина/толщина ниже порога;
        - `LockAlreadyHeldError` — принимающий уже занят;
        - `InvalidDuelStateError` — дуэль не в `PENDING_ACCEPT`;
        - `NotADuelParticipantError` — `tg_id` не соответствует
          `challenged_id` для адресного режима.
        """

        async with self._uow:
            duel = await self._duels.get_by_id(duel_id=input_dto.duel_id)
            if duel is None:
                raise DuelNotFoundError(duel_id=input_dto.duel_id)

            accepter = await self._fetch_player(tg_id=input_dto.tg_id)
            cfg = self._balance.get().pvp.duel_1v1

            now = self._clock.now()
            AnticheatGuard.require_unlocked(accepter, now=now)
            self._require_pvp_eligible(player=accepter, cfg=cfg)

            challenger = await self._players.get_by_id(
                player_id=duel.challenger_id,
            )
            if challenger is None:
                raise PlayerNotFoundError(tg_id=duel.challenger_id)

            await self._locks.acquire(
                actor_kind="player",
                actor_id=self._require_id(accepter),
                reason=LockReason.PVP,
                ttl=_DEFAULT_DUEL_LOCK_TTL,
            )

            accepted = duel.accept(
                accepter_id=self._require_id(accepter),
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
                        "challenger_id": saved.challenger_id,
                        "challenged_id": saved.challenged_id,
                        "p1_initial_length_cm": saved.p1_initial_length_cm,
                        "p2_initial_length_cm": saved.p2_initial_length_cm,
                    },
                    reason="pvp_duel_accepted",
                    idempotency_key=f"pvp_duel_accepted:{saved.id}",
                    occurred_at=now,
                )
            )

            # удаляем запись из лобби, если она там была (GLOBAL_ONLY-вызов
            # был принят по адресу — например через handler `/duel_global`).
            duel_id_for_cleanup = saved.id
            mode_was_chat_then_global = duel.mode is DuelMode.CHAT_THEN_GLOBAL
            mode_was_global_only = duel.mode is DuelMode.GLOBAL_ONLY
            if self._lobby is not None and mode_was_global_only:
                await self._lobby.remove(duel_id=duel_id_for_cleanup)

        # Снимаем scheduled-job-ы **снаружи** UoW (idempotent).
        if self._scheduler is not None:
            if mode_was_chat_then_global:
                await self._scheduler.cancel_chat_to_global_escalation(
                    duel_id=duel_id_for_cleanup,
                )
            elif mode_was_global_only:
                await self._scheduler.cancel_global_lobby_expiration(
                    duel_id=duel_id_for_cleanup,
                )
        return DuelAccepted(duel=saved)

    async def _fetch_player(self, *, tg_id: int) -> Player:
        player = await self._players.get_by_tg_id(tg_id)
        if player is None:
            raise PlayerNotFoundError(tg_id=tg_id)
        return player

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
    "AcceptDuel",
    "DuelAccepted",
]
