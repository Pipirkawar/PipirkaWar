"""Use-case `RegisterClan` (Спринт 1.1.4).

Срабатывает при добавлении бота в группу/супергруппу
(`my_chat_member: bot added`). Идемпотентен:

- если `chat_id` ещё не зарегистрирован → создаём `Clan` с `ACTIVE`;
- если `chat_id` уже есть и `frozen` (бот когда-то был кикнут) →
  размораживаем (audit `CLAN_UNFREEZE`);
- если `chat_id` уже есть и `active` → no-op (это повторный
  `my_chat_member` или гонка).

Acceptance criteria из `development_plan.md` Спринт 1.1.4:
> новый чат → запись `clans`; смена `chat_id` (group→supergroup)
> обрабатывается.

Миграция group→supergroup живёт в отдельном use-case
`MigrateClanChatId` (см. `migrate.py`), потому что Telegram доставляет
её через другое событие (`message.migrate_to_chat_id`).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import RegisterClanInput
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanTitle,
    IClanRepository,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class RegisterClanResult:
    """Результат регистрации.

    `outcome`:
    - `"created"` — клан создан с нуля.
    - `"unfrozen"` — клан существовал в `frozen` и был размрожен.
    - `"already_active"` — повторный вызов на active-клане, ничего не
      изменили.
    """

    clan: Clan
    outcome: str


class RegisterClan:
    """Use-case регистрации клана при добавлении бота в чат."""

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

    async def execute(self, input_dto: RegisterClanInput) -> RegisterClanResult:
        chat_kind = ChatKind(input_dto.chat_kind)
        title = ClanTitle(value=input_dto.title)
        async with self._uow:
            now = self._clock.now()
            existing = await self._clans.get_by_chat_id(input_dto.chat_id)
            if existing is None:
                created = Clan.new(
                    chat_id=input_dto.chat_id,
                    chat_kind=chat_kind,
                    title=title,
                    now=now,
                )
                saved = await self._clans.add(created)
                await self._audit.record(
                    AuditEntry(
                        action=AuditAction.CLAN_REGISTER,
                        actor_id=input_dto.added_by_tg_id,
                        target_kind="clan",
                        target_id=str(saved.chat_id),
                        before=None,
                        after={
                            "chat_id": saved.chat_id,
                            "chat_kind": saved.chat_kind.value,
                            "title": saved.title.value,
                        },
                        reason="register_clan",
                        idempotency_key=f"register_clan:{saved.chat_id}",
                        occurred_at=now,
                    )
                )
                return RegisterClanResult(clan=saved, outcome="created")

            if existing.is_frozen:
                unfrozen = existing.unfreeze(now=now)
                saved = await self._clans.save(unfrozen)
                await self._audit.record(
                    AuditEntry(
                        action=AuditAction.CLAN_UNFREEZE,
                        actor_id=input_dto.added_by_tg_id,
                        target_kind="clan",
                        target_id=str(saved.chat_id),
                        before={"status": "frozen"},
                        after={"status": "active"},
                        reason="bot_added_back",
                        idempotency_key=f"unfreeze_clan:{saved.chat_id}:{int(now.timestamp())}",
                        occurred_at=now,
                    )
                )
                return RegisterClanResult(clan=saved, outcome="unfrozen")

            return RegisterClanResult(clan=existing, outcome="already_active")
