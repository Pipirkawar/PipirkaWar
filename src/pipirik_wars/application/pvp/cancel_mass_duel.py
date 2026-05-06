"""Use-case `CancelMassDuel` (Спринт 2.2.E, ГДД §7.2).

Отмена активного массового боя без раскатывания ±длин. Используется
в административных сценариях:

* админ-команда отмены через handler;
* деградация ростера / интегральный сбой шедулера.

Алгоритм:

1. Загружает `MassDuel`. Нет — `MassDuelNotFoundError`.
2. `MassDuel.cancel(now=...)` — доменный мутатор (идемпотентно для
   уже `CANCELLED`-боя; из `COMPLETED` нельзя — `InvalidMassDuelStateError`).
3. `IMassDuelRepository.save(...)`.
4. Снимает activity-locks всех участников.
5. Audit `PVP_MASS_DUEL_CANCELLED` (idempotency-key
   `pvp_mass_duel_cancelled:{duel_id}`).

Транзакция — ambient `IUnitOfWork`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import CancelMassDuelInput
from pipirik_wars.application.security import ActivityLockService
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
    IDelayedJobScheduler,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class MassDuelCancelled:
    """Результат отмены массового боя."""

    duel: MassDuel
    was_already_cancelled: bool


class CancelMassDuel:
    """Use-case «отменить активный массовый PvP-бой»."""

    __slots__ = (
        "_audit",
        "_clock",
        "_duels",
        "_locks",
        "_scheduler",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        duels: IMassDuelRepository,
        locks: ActivityLockService,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler | None = None,
    ) -> None:
        self._uow = uow
        self._duels = duels
        self._locks = locks
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler

    async def execute(self, input_dto: CancelMassDuelInput) -> MassDuelCancelled:
        """Отменить бой. Бросает:

        - `MassDuelNotFoundError` — боя с таким `duel_id` нет;
        - `InvalidMassDuelStateError` — бой уже `COMPLETED`.
        """

        async with self._uow:
            duel = await self._duels.get_by_id(duel_id=input_dto.duel_id)
            if duel is None:
                raise MassDuelNotFoundError(duel_id=input_dto.duel_id)

            if duel.is_cancelled:
                return MassDuelCancelled(duel=duel, was_already_cancelled=True)

            now = self._clock.now()
            cancelled = duel.cancel(now=now)
            saved = await self._duels.save(cancelled)

            for pid in (*saved.clan1_member_ids, *saved.clan2_member_ids):
                await self._locks.release(actor_kind="player", actor_id=pid)

            assert saved.id is not None
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PVP_MASS_DUEL_CANCELLED,
                    actor_id=None,
                    target_kind="pvp_mass_duel",
                    target_id=str(saved.id),
                    before={"state": duel.state.value},
                    after={"state": saved.state.value},
                    reason=input_dto.reason,
                    idempotency_key=f"pvp_mass_duel_cancelled:{saved.id}",
                    occurred_at=now,
                )
            )
            saved_id = saved.id

        # AFK-таймер снимаем снаружи UoW (идемпотентная операция шедулера).
        if self._scheduler is not None:
            await self._scheduler.cancel_mass_duel_afk_resolution(duel_id=saved_id)

        return MassDuelCancelled(duel=saved, was_already_cancelled=False)


__all__ = [
    "CancelMassDuel",
    "MassDuelCancelled",
]
