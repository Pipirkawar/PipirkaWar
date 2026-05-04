"""Use-case `JoinClan` (Спринт 1.1.5).

Условие участия в клане: «игрок виден в чате клана **И** зарегистрирован
в боте → авто-членство». Use-case вызывается из bot-handler-а на
`chat_member: ... → member`. Если игрок не зарегистрирован — мы не
создаём `clan_members`-запись и возвращаем `outcome="not_registered"`,
по которому handler пошлёт пользователю инструкцию «напишите боту в ЛС».

Acceptance из `development_plan.md` Спринт 1.1.5:
> игрок без регистрации в ЛС → `clan_members` не создаётся, бот шлёт
> инструкцию.

Использует уникальное БД-ограничение `UNIQUE(player_id)` (Спринт 1.1.B):
один игрок = один клан одновременно (правило ГДД §4). Если игрок уже в
другом клане — `IClanMembershipRepository.add` бросит
`ClanMembershipExistsError`, которое use-case пробрасывает «как есть»
(handler покажет «вы уже состоите в клане»).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import JoinClanInput
from pipirik_wars.domain.clan import (
    Clan,
    ClanMember,
    IClanMembershipRepository,
    IClanRepository,
)
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)
from pipirik_wars.shared.errors import IntegrityError


@dataclass(frozen=True, slots=True)
class JoinClanResult:
    """Результат попытки добавить игрока в клан.

    `outcome`:
    - `"joined"` — членство создано.
    - `"already_member"` — игрок уже состоял в этом клане → no-op.
    - `"not_registered"` — игрок не зарегистрирован в ЛС → инструкция.
    """

    outcome: str
    clan: Clan | None
    member: ClanMember | None


class JoinClan:
    """Use-case авто-членства в клане."""

    __slots__ = (
        "_audit",
        "_clans",
        "_clock",
        "_members",
        "_players",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        clans: IClanRepository,
        clan_members: IClanMembershipRepository,
        players: IPlayerRepository,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._clans = clans
        self._members = clan_members
        self._players = players
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: JoinClanInput) -> JoinClanResult:
        async with self._uow:
            now = self._clock.now()
            clan = await self._clans.get_by_chat_id(input_dto.chat_id)
            if clan is None:
                # Чат с ботом, но клан не зарегистрирован → конфигурационный
                # баг. На уровне 1.1.5 мы это не обрабатываем — handler
                # должен был проверить и сначала вызвать RegisterClan.
                raise IntegrityError(
                    f"chat_id={input_dto.chat_id} is not a registered clan",
                )
            if clan.id is None:  # pragma: no cover — защитный invariant
                raise IntegrityError("clan was loaded without id")

            player = await self._players.get_by_tg_id(input_dto.tg_id)
            if player is None:
                return JoinClanResult(
                    outcome="not_registered",
                    clan=clan,
                    member=None,
                )
            if player.id is None:  # pragma: no cover — защитный invariant
                raise IntegrityError("player was loaded without id")

            existing = await self._members.get_by_player(player.id)
            if existing is not None and existing.clan_id == clan.id:
                return JoinClanResult(
                    outcome="already_member",
                    clan=clan,
                    member=existing,
                )

            member = ClanMember.new(
                clan_id=clan.id,
                player_id=player.id,
                now=now,
            )
            saved = await self._members.add(member)
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.CLAN_MEMBER_JOIN,
                    actor_id=player.tg_id,
                    target_kind="clan_member",
                    target_id=f"{clan.id}:{player.id}",
                    before=None,
                    after={
                        "clan_id": clan.id,
                        "player_id": player.id,
                        "tg_id": player.tg_id,
                        "chat_id": clan.chat_id,
                    },
                    reason="auto_join_on_chat_member",
                    idempotency_key=f"join_clan:{clan.id}:{player.id}",
                    occurred_at=now,
                )
            )
            return JoinClanResult(
                outcome="joined",
                clan=clan,
                member=saved,
            )
