"""Use-case `ChallengeDuel` (Спринт 2.1.D, ГДД §7.1).

Игрок отправляет `/pvp` (кнопкой или адресной командой) и создаёт
PvP-вызов 1×1. Use-case:

1. Маппит DTO-`mode` (`"chat_only"` / `"chat_then_global"` /
   `"global_only"`) на доменный `DuelMode`.
2. Загружает `Player` по `tg_id` челленджера. Нет — `PlayerNotFoundError`.
3. Если `mode != GLOBAL_ONLY` — загружает оппонента по
   `challenged_tg_id`. Нет — `PlayerNotFoundError`.
4. Anti-cheat soft-ban-гейт для челленджера через `AnticheatGuard.require_unlocked`.
5. PvP-требования (ГДД §7.1, `balance.pvp.duel_1v1`):
   * длина ≥ `min_length_cm` (по умолчанию `20` см);
   * толщина ≥ `min_thickness_level` (по умолчанию `2`).
   Иначе — `PvpRequirementsNotMetError`. Для адресных режимов
   проверка идёт **только** для челленджера; оппонент проверяется
   на стороне `AcceptDuel` (он мог не успеть откатить длину между
   созданием вызова и принятием).
6. Берёт activity-lock (`actor_kind="player"`, `actor_id=player.id`,
   `reason=PVP`, ttl = duel-TTL). Если уже взят — `LockAlreadyHeldError`
   (handler конвертит в локализованное «вы заняты» — ГДД §3.2,
   ПД 2.1.6 «нельзя одновременно в PvP и поход»).
7. Создаёт `Duel.create_challenge(...)` через домен и кладёт в
   `IDuelRepository.add(...)`.
8. Пишет `audit_log(action=PVP_DUEL_CREATED)` со снимком ключевых
   полей; `idempotency_key=f"pvp_duel_created:{duel.id}"`.
9. Возвращает `DuelChallenged(duel)` для handler-а.

Транзакция — через ambient `IUnitOfWork`. Любая ошибка откатывает
лок, запись `pvp_duels` и audit одной транзакцией.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from pipirik_wars.application.dto.inputs import ChallengeDuelInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.anticheat import AnticheatGuard
from pipirik_wars.domain.balance import PvpDuel1v1Config
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import IPlayerRepository, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    IDuelRepository,
    PvpRequirementsNotMetError,
)
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)

# TTL активити-лока на стороне челленджера. Покрывает фазу ожидания
# принятия (~3 мин для CHAT_THEN_GLOBAL + 10 мин «глобал-лобби» по
# ПД 2.1.3) плюс саму дуэль (≤ 3 раунда × 60 сек). 30 минут с запасом —
# если шедулер 2.1.F/2.1.G не успеет освободить, lock сам экспайрится.
_DEFAULT_DUEL_LOCK_TTL = timedelta(minutes=30)

_DTO_MODE_TO_DOMAIN: dict[str, DuelMode] = {
    "chat_only": DuelMode.CHAT_ONLY,
    "chat_then_global": DuelMode.CHAT_THEN_GLOBAL,
    "global_only": DuelMode.GLOBAL_ONLY,
}


@dataclass(frozen=True, slots=True)
class DuelChallenged:
    """Результат успешного создания вызова."""

    duel: Duel


class ChallengeDuel:
    """Use-case «бросить PvP-вызов 1×1»."""

    __slots__ = (
        "_audit",
        "_balance",
        "_clock",
        "_duels",
        "_locks",
        "_players",
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
    ) -> None:
        self._uow = uow
        self._players = players
        self._duels = duels
        self._locks = locks
        self._balance = balance
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: ChallengeDuelInput) -> DuelChallenged:
        """Создать вызов. Бросает:

        - `PlayerNotFoundError` — челленджера или оппонента нет в БД;
        - `AnticheatSoftBanError` — челленджер в soft-ban-е;
        - `PvpRequirementsNotMetError` — длина/толщина ниже порога;
        - `LockAlreadyHeldError` — челленджер уже занят (другой PvP/forest);
        - `SelfChallengeError` — `challenger == challenged`.
        """

        domain_mode = _DTO_MODE_TO_DOMAIN[input_dto.mode]
        async with self._uow:
            challenger = await self._fetch_player(tg_id=input_dto.challenger_tg_id)
            cfg = self._balance.get().pvp.duel_1v1

            # DTO `_validate_mode_consistency` гарантирует:
            # - challenged_tg_id != None для CHAT_*-режимов;
            # - challenged_tg_id == None для GLOBAL_ONLY.
            challenged: Player | None = None
            if input_dto.challenged_tg_id is not None:
                challenged = await self._fetch_player(
                    tg_id=input_dto.challenged_tg_id,
                )

            now = self._clock.now()
            AnticheatGuard.require_unlocked(challenger, now=now)
            self._require_pvp_eligible(player=challenger, cfg=cfg)

            await self._locks.acquire(
                actor_kind="player",
                actor_id=self._require_id(challenger),
                reason=LockReason.PVP,
                ttl=_DEFAULT_DUEL_LOCK_TTL,
            )

            duel = Duel.create_challenge(
                challenger_id=self._require_id(challenger),
                challenged_id=(self._require_id(challenged) if challenged is not None else None),
                mode=domain_mode,
                hit_pct=cfg.hit_pct,
                expected_rounds=cfg.rounds,
                now=now,
            )
            saved = await self._duels.add(duel)

            assert saved.id is not None  # repo гарантирует id после add()
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PVP_DUEL_CREATED,
                    actor_id=challenger.tg_id,
                    target_kind="pvp_duel",
                    target_id=str(saved.id),
                    before=None,
                    after={
                        "challenger_id": saved.challenger_id,
                        "challenged_id": saved.challenged_id,
                        "mode": saved.mode.value,
                        "hit_pct": saved.hit_pct,
                        "expected_rounds": saved.expected_rounds,
                    },
                    reason="pvp_duel_challenge_created",
                    idempotency_key=f"pvp_duel_created:{saved.id}",
                    occurred_at=now,
                )
            )
        return DuelChallenged(duel=saved)

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
    "ChallengeDuel",
    "DuelChallenged",
]
