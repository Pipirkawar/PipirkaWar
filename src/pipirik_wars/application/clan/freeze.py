"""Use-case `FreezeClan` (Спринт 1.1.6).

Срабатывает при удалении бота из чата (`my_chat_member: bot → kicked / left`).
Не удаляет данные — только меняет статус клана на `FROZEN`. Любые
клановые механики (Глава дня, караван, масс-PvP) пропускают frozen-кланы,
но история и `clan_members` остаются нетронутыми.

Acceptance из Спринта 1.1.6:
> бот кикнут → `status='frozen'`, история сохранена; повторное
> добавление → `status='active'`.

Разморозка ходит через `RegisterClan` (см. `register.py`), который
идемпотентен и сам определяет, freeze→active нужно сделать или клан
ещё ни разу не регистрировался.

Идемпотентность: повторный freeze уже-frozen клана → outcome
`"already_frozen"`, без аудит-записи.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import FreezeClanInput
from pipirik_wars.domain.clan import Clan, IClanRepository
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)
from pipirik_wars.shared.errors import IntegrityError


@dataclass(frozen=True, slots=True)
class FreezeClanResult:
    """`outcome`:

    - `"frozen"` — клан только что заморожен.
    - `"already_frozen"` — был уже frozen, ничего не делали.
    - `"not_found"` — клана с таким `chat_id` нет (миграция или гонка).
    """

    outcome: str
    clan: Clan | None


class FreezeClan:
    """Use-case заморозки клана."""

    __slots__ = ("_audit", "_clans", "_clock", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        clans: IClanRepository,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._clans = clans
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: FreezeClanInput) -> FreezeClanResult:
        async with self._uow:
            now = self._clock.now()
            existing = await self._clans.get_by_chat_id(input_dto.chat_id)
            if existing is None:
                return FreezeClanResult(outcome="not_found", clan=None)
            if existing.is_frozen:
                return FreezeClanResult(outcome="already_frozen", clan=existing)
            if existing.id is None:  # pragma: no cover — защитный invariant
                raise IntegrityError("clan was loaded without id")

            frozen = existing.freeze(now=now)
            saved = await self._clans.save(frozen)
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.CLAN_FREEZE,
                    actor_id=None,
                    target_kind="clan",
                    target_id=str(saved.id),
                    before={"status": "active"},
                    after={"status": "frozen"},
                    reason=input_dto.reason,
                    idempotency_key=(f"freeze_clan:{saved.chat_id}:{int(now.timestamp())}"),
                    occurred_at=now,
                )
            )
            return FreezeClanResult(outcome="frozen", clan=saved)
