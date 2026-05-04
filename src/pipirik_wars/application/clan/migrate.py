"""Use-case `MigrateClanChatId` — миграция group → supergroup.

Telegram умеет «промоутить» обычную группу до супергруппы. При этом
`chat_id` меняется (с `-…` на `-100…`). Бот получает событие через
`message.migrate_to_chat_id`. Внутренний `id` клана **не меняется** —
вся история, audit и членства сохраняются.

Acceptance из Спринта 1.1.4 («смена `chat_id` обрабатывается»).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import MigrateClanChatIdInput
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    IClanRepository,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)
from pipirik_wars.shared.errors import IntegrityError


@dataclass(frozen=True, slots=True)
class MigrateClanResult:
    """`outcome`:

    - `"migrated"` — chat_id обновлён.
    - `"already_migrated"` — chat_id уже был такой (повторный вызов).
    """

    clan: Clan
    outcome: str


class ClanNotFoundError(IntegrityError):
    """Миграция клана, которого нет в `clans`. На уровне Спринта 1.1.4 —
    конфигурационный/гоночный баг (мы получили `migrate_to_chat_id` от
    Telegram, но клан в БД не зарегистрирован).
    """

    def __init__(self, *, old_chat_id: int) -> None:
        super().__init__(f"clan with old chat_id={old_chat_id} not found")
        self.old_chat_id = old_chat_id


class MigrateClanChatId:
    """Миграция clan.chat_id (group → supergroup)."""

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

    async def execute(self, input_dto: MigrateClanChatIdInput) -> MigrateClanResult:
        new_kind = ChatKind(input_dto.new_chat_kind)
        async with self._uow:
            now = self._clock.now()
            existing = await self._clans.get_by_chat_id(input_dto.old_chat_id)
            if existing is None:
                # Возможно, миграция уже произошла раньше — проверим новый.
                already = await self._clans.get_by_chat_id(input_dto.new_chat_id)
                if already is not None:
                    return MigrateClanResult(clan=already, outcome="already_migrated")
                raise ClanNotFoundError(old_chat_id=input_dto.old_chat_id)

            migrated = existing.with_chat_id(
                new_chat_id=input_dto.new_chat_id,
                new_chat_kind=new_kind,
                now=now,
            )
            if migrated is existing:
                return MigrateClanResult(clan=existing, outcome="already_migrated")

            saved = await self._clans.save(migrated)
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.CLAN_MIGRATE,
                    actor_id=None,
                    target_kind="clan",
                    target_id=str(saved.id),
                    before={
                        "chat_id": existing.chat_id,
                        "chat_kind": existing.chat_kind.value,
                    },
                    after={
                        "chat_id": saved.chat_id,
                        "chat_kind": saved.chat_kind.value,
                    },
                    reason="telegram_group_to_supergroup",
                    idempotency_key=(
                        f"migrate_clan:{input_dto.old_chat_id}->{input_dto.new_chat_id}"
                    ),
                    occurred_at=now,
                )
            )
            return MigrateClanResult(clan=saved, outcome="migrated")
