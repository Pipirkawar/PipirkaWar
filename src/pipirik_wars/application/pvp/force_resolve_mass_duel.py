"""Use-case `ForceResolveMassDuel` (Спринт 2.2.E, ГДД §7.2).

AFK-фоллбэк массового боя. Шедулер раунд-таймера (Спринт 2.2.F)
вызывает этот use-case по истечении общего таймера боя, если
хотя бы один участник не отправил `submit_move`. Для каждого
молчаливого участника выбирается случайный `MassRoundChoice(attack,
block)` через `IRandom`, после чего бой резолвится через `MassDuel.resolve(...)`.

Алгоритм:

1. Загружает `MassDuel`. Нет — `MassDuelNotFoundError`.
2. Если бой не в `IN_PROGRESS` — no-op (`was_already_resolved=True`).
   Это идемпотентность для случаев, когда между шедулингом и
   срабатыванием бой уже разрешился (через `ResolveMassDuel`) или
   был отменён (через `CancelMassDuel`).
3. Если все уже отправили (`missing_player_ids == ()`) — пропускает
   шаг force-submit и сразу делает `resolve(...)` (это нормальный
   путь, когда последний `SubmitMassMove` пришёл одновременно с
   таймером).
4. Иначе для каждого `pid in missing_player_ids` роллит
   `MassRoundChoice(player_id=pid, attack=random, block=random)`
   через `IRandom.choice`.
5. `MassDuel.force_submit_missing(fallback_choices=..., now=...)`.
6. `MassDuel.resolve(random=..., now=...)`.
7. `IMassDuelRepository.save(...)`.
8. `apply_mass_duel_outcome(...)` — раскат ±длин.
9. Снимает activity-locks всех участников.
10. Audit `PVP_MASS_DUEL_COMPLETED` (с `afk_fallback=True`,
    idempotency-key `pvp_mass_duel_completed:{duel_id}`).

Транзакция — ambient `IUnitOfWork`. AnticheatSoftBanError при
apply_mass_duel_outcome → откат, бой остаётся в IN_PROGRESS.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import ForceResolveMassDuelInput
from pipirik_wars.application.pvp.apply_mass_outcome import apply_mass_duel_outcome
from pipirik_wars.application.pvp.resolve_mass_duel import (
    audit_mass_duel_completed,
    release_mass_duel_locks,
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.pvp import (
    IMassDuelRepository,
    MassDuel,
    MassDuelNotFoundError,
    MassRoundChoice,
    Position,
)
from pipirik_wars.domain.shared.ports import (
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IRandom,
    IUnitOfWork,
)

# Все три позиции — единый pool для random.choice. Атака и блок
# независимы (даже если совпали — это валидный домен).
_POSITIONS: tuple[Position, ...] = (Position.HIGH, Position.MID, Position.LOW)


@dataclass(frozen=True, slots=True)
class MassDuelForceResolved:
    """Результат AFK-фоллбэка массового боя."""

    duel: MassDuel
    was_already_resolved: bool
    """`True`, если шедулер опоздал — бой уже завершён или отменён."""


class ForceResolveMassDuel:
    """Use-case «AFK-таймер боя: добить случайными выборами и резолвнуть»."""

    __slots__ = (
        "_audit",
        "_clock",
        "_duels",
        "_length_granter",
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
        players: IPlayerRepository,
        duels: IMassDuelRepository,
        locks: ActivityLockService,
        length_granter: ILengthGranter,
        random: IRandom,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler | None = None,
    ) -> None:
        self._uow = uow
        self._players = players
        self._duels = duels
        self._locks = locks
        self._length_granter = length_granter
        self._random = random
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler

    async def execute(self, input_dto: ForceResolveMassDuelInput) -> MassDuelForceResolved:
        """AFK-резолв. Бросает:

        - `MassDuelNotFoundError` — боя нет;
        - `AnticheatSoftBanError` — при apply_mass_duel_outcome.

        Возвращает `was_already_resolved=True` без мутаций, если бой
        уже разрешён или отменён (шедулер опоздал) — идемпотентность.
        """

        async with self._uow:
            duel = await self._duels.get_by_id(duel_id=input_dto.duel_id)
            if duel is None:
                raise MassDuelNotFoundError(duel_id=input_dto.duel_id)

            if not duel.is_in_progress:
                return MassDuelForceResolved(duel=duel, was_already_resolved=True)

            now = self._clock.now()
            ready = duel
            missing = duel.missing_player_ids
            if missing:
                fallback_choices = {
                    pid: MassRoundChoice(
                        player_id=pid,
                        attack=self._random.choice(_POSITIONS),
                        block=self._random.choice(_POSITIONS),
                    )
                    for pid in missing
                }
                ready = duel.force_submit_missing(
                    fallback_choices=fallback_choices,
                    now=now,
                )
            resolved = ready.resolve(random=self._random, now=now)
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
                afk_fallback=True,
            )
            saved_id = saved.id
            assert saved_id is not None

        # AFK-таймер снимаем снаружи UoW. Это best-effort cleanup на случай
        # повторного срабатывания (обычно job уже выполнился и был удалён из
        # job-store-а автоматически, но cancel идемпотентен по контракту).
        if self._scheduler is not None:
            await self._scheduler.cancel_mass_duel_afk_resolution(duel_id=saved_id)

        return MassDuelForceResolved(duel=saved, was_already_resolved=False)


__all__ = [
    "ForceResolveMassDuel",
    "MassDuelForceResolved",
]
