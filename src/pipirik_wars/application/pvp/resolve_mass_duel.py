"""Use-case `ResolveMassDuel` (Спринт 2.2.E, ГДД §7.2).

Финальный резолв массового боя, когда все участники отправили выбор:

1. Загружает `MassDuel`. Нет — `MassDuelNotFoundError`.
2. `MassDuel.resolve(random=..., now=...)` — доменный мутатор:
   * требует `state == IN_PROGRESS`;
   * требует `is_ready_to_resolve == True` (иначе
     `MassDuelNotReadyError` — handler/шедулер должен сначала
     добить через `ForceResolveMassDuel`).
3. `IMassDuelRepository.save(...)` — пишет COMPLETED-агрегат вместе с
   `damage_entries` (отдельная таблица).
4. `apply_mass_duel_outcome(...)` — раскатывает ±длины по всем
   участникам. Прибавки — через `ILengthGranter` (anti-cheat-cap),
   списания — прямой `with_length` + audit `LENGTH_REVOKE`.
5. Снимает activity-locks всех участников (через `ActivityLockService`).
6. Audit `PVP_MASS_DUEL_COMPLETED` со снимком итога
   (idempotency-key `pvp_mass_duel_completed:{duel_id}`).

Транзакция — ambient `IUnitOfWork`. Если apply_mass_duel_outcome
бросает `AnticheatSoftBanError` (cap-trip-wire у атакующего), вся
транзакция откатывается — бой остаётся в `IN_PROGRESS` на предыдущем
шаге, локи участников остаются висящими (admin-разбор по audit-логу).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.application.dto.inputs import ResolveMassDuelInput
from pipirik_wars.application.pvp.apply_mass_outcome import apply_mass_duel_outcome
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.pvp import (
    IMassDuelRepository,
    MassDuel,
    MassDuelNotFoundError,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IRandom,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class MassDuelResolved:
    """Результат финального резолва массового боя."""

    duel: MassDuel


class ResolveMassDuel:
    """Use-case «разрешить массовый PvP-бой и применить ±длины»."""

    __slots__ = (
        "_audit",
        "_clock",
        "_duels",
        "_length_granter",
        "_locks",
        "_players",
        "_random",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        duels: IMassDuelRepository,
        locks: ActivityLockService,
        length_granter: ILengthGranter,
        random: IRandom,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._duels = duels
        self._locks = locks
        self._length_granter = length_granter
        self._random = random
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: ResolveMassDuelInput) -> MassDuelResolved:
        """Разрешить бой. Бросает:

        - `MassDuelNotFoundError` — боя с таким `duel_id` нет;
        - `InvalidMassDuelStateError` — бой не в `IN_PROGRESS`;
        - `MassDuelNotReadyError` — кто-то ещё не отправил выбор;
        - `AnticheatSoftBanError` — кто-то из атакующих в soft-ban-е.
        """

        async with self._uow:
            duel = await self._duels.get_by_id(duel_id=input_dto.duel_id)
            if duel is None:
                raise MassDuelNotFoundError(duel_id=input_dto.duel_id)

            now = self._clock.now()
            resolved = duel.resolve(random=self._random, now=now)
            saved = await self._duels.save(resolved)

            await apply_mass_duel_outcome(
                duel=saved,
                players=self._players,
                length_granter=self._length_granter,
                audit=self._audit,
                now=now,
            )
            await release_mass_duel_locks(saved, locks=self._locks)
            await audit_mass_duel_completed(
                audit=self._audit,
                duel=saved,
                now=now,
                afk_fallback=False,
            )
            return MassDuelResolved(duel=saved)


async def release_mass_duel_locks(duel: MassDuel, *, locks: ActivityLockService) -> None:
    """Снять activity-locks всех участников массового боя."""

    for pid in (*duel.clan1_member_ids, *duel.clan2_member_ids):
        await locks.release(actor_kind="player", actor_id=pid)


async def audit_mass_duel_completed(
    *,
    audit: IAuditLogger,
    duel: MassDuel,
    now: datetime,
    afk_fallback: bool,
) -> None:
    """Записать `PVP_MASS_DUEL_COMPLETED` со снимком итога."""
    outcome = duel.final_outcome
    assert outcome is not None
    assert duel.id is not None
    after: dict[str, object] = {
        "winner": outcome.winner.value,
        "clan1_total_dealt": outcome.clan1_total_dealt,
        "clan2_total_dealt": outcome.clan2_total_dealt,
        "clan1_delta_cm": outcome.clan1_delta_cm,
        "clan2_delta_cm": outcome.clan2_delta_cm,
    }
    if afk_fallback:
        after["afk_fallback"] = True
    await audit.record(
        AuditEntry(
            action=AuditAction.PVP_MASS_DUEL_COMPLETED,
            actor_id=None,
            target_kind="pvp_mass_duel",
            target_id=str(duel.id),
            before=None,
            after=after,
            reason="pvp_mass_duel_completed_afk" if afk_fallback else "pvp_mass_duel_completed",
            idempotency_key=f"pvp_mass_duel_completed:{duel.id}",
            occurred_at=now,
        )
    )


__all__ = [
    "MassDuelResolved",
    "ResolveMassDuel",
    "audit_mass_duel_completed",
    "release_mass_duel_locks",
]
