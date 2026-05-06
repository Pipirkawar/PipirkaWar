"""Use-case `GetClanCard` (Спринт 2.5-D.1, ГДД §18.6.5).

`/clan <id|chat_id>` — read-only карточка клана для админ-поддержки.

Семантика lookup-а:

* На вход приходит положительное целое число (`int`). Парсинг строки в
  `int` — задача handler-а; use-case получает уже валидный `query: int`.
* Сначала пробуем как внутренний `Clan.id` (`IClanRepository.get_by_id`).
  Если не нашли — пробуем как Telegram `chat_id`
  (`IClanRepository.get_by_chat_id`). Это поведение симметрично
  `/player`-команде: один аргумент работает на оба ключа.
* Текстовый поиск по названию (`title`-substring) — отдельная задача
  D.3-followup; реализация требует нового read-метода
  `IClanRepository.find_by_title` + ILIKE-индекса. На D.1 она намеренно
  не сделана, чтобы спринт оставался обозримым.

Карточка содержит:

* реквизиты клана (`id`, `chat_id`, `chat_kind`, `title`, `status`,
  `created_at`);
* сводку «лидер» (если есть участник с `role=LEADER` — это атаман
  на стороне разбойников / лидер каравана; в реальной модели «глава
  дня» хранится отдельно и не считается owner-ом);
* список участников в виде `PlayerSummary` (как в `/player`) с
  ролью + датой вступления;
* агрегаты по составу: `member_count`, `total_length_cm` (только
  активных игроков, чтобы цифра соответствовала тому, что видит
  движок clantop-а — ГДД §6 / §11).

Read-only — TOTP не нужен. Сам факт чтения логируется как
`ADMIN_CLAN_LOOKUP` (super-admin в `/audit` должен видеть, кто и
какой клан «пробивал»).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.application.admin.find_players import (
    PlayerSummary,
    player_to_summary,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    IAdminAuditLogger,
    IAdminRepository,
)
from pipirik_wars.domain.clan import (
    ClanMemberRole,
    ClanStatus,
    IClanMembershipRepository,
    IClanRepository,
)
from pipirik_wars.domain.player import IPlayerRepository, PlayerStatus
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


@dataclass(frozen=True, slots=True)
class GetClanCardInput:
    """Параметры команды `/clan`.

    `query` — целое число; handler парсит строку в `int` и валидирует
    положительность. Use-case проверяет, найден ли клан, но сам не
    парсит строку, чтобы не дублировать UX-валидацию.
    """

    actor_tg_id: int
    query: int
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class ClanMemberCardInfo:
    """Один участник клана для карточки.

    `summary` повторяет сводку из `/find_player` (длина, толщина,
    @username и т.п.). `role` и `joined_at` приходят из `clan_members`.
    Если игрок пропал из БД (orphan-ссылка), entry просто пропускается
    use-case-ом — в `members` он не попадает.
    """

    summary: PlayerSummary
    role: ClanMemberRole
    joined_at: datetime


@dataclass(frozen=True, slots=True)
class ClanCard:
    """Карточка клана для админ-выдачи `/clan`."""

    clan_id: int
    chat_id: int
    chat_kind: str
    title: str
    status: ClanStatus
    created_at: datetime
    updated_at: datetime
    member_count: int
    active_member_count: int
    total_length_cm: int
    leader: ClanMemberCardInfo | None
    members: Sequence[ClanMemberCardInfo]


@dataclass(frozen=True, slots=True)
class GetClanCardOutput:
    """Результат: карточка либо `None`, если клан с таким идентификатором не найден."""

    query: int
    card: ClanCard | None


class GetClanCard:
    """Use-case карточки клана."""

    __slots__ = (
        "_admins",
        "_audit",
        "_clan_members",
        "_clans",
        "_clock",
        "_players",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        players: IPlayerRepository,
        clans: IClanRepository,
        clan_members: IClanMembershipRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._players = players
        self._clans = clans
        self._clan_members = clan_members
        self._audit = audit
        self._clock = clock

    async def execute(self, inp: GetClanCardInput) -> GetClanCardOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover — invariant
            raise RuntimeError("admin.id is None after get_by_tg_id")

        now = self._clock.now()

        async with self._uow:
            clan = await self._clans.get_by_id(inp.query)
            if clan is None:
                clan = await self._clans.get_by_chat_id(inp.query)

            card: ClanCard | None = None
            if clan is not None and clan.id is not None:
                card = await self._build_card(clan_id=clan.id, clan=clan)

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_CLAN_LOOKUP,
                    target_kind="clan",
                    target_id=str(inp.query),
                    before=None,
                    after={"found": card is not None},
                    reason=f"clan_card:{inp.query}",
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return GetClanCardOutput(query=inp.query, card=card)

    async def _build_card(
        self,
        *,
        clan_id: int,
        clan: object,  # фактически — Clan; локальный тип, чтобы не плодить импорты.
    ) -> ClanCard:
        # Локальный импорт ради точности типизации dataclass-а:
        from pipirik_wars.domain.clan import Clan as _Clan  # noqa: PLC0415

        assert isinstance(clan, _Clan)
        members = await self._clan_members.list_by_clan(clan_id)

        leader: ClanMemberCardInfo | None = None
        member_infos: list[ClanMemberCardInfo] = []
        active_count = 0
        total_length_cm = 0

        for membership in members:
            player = await self._players.get_by_id(player_id=membership.player_id)
            if player is None:
                # Orphan-ссылка: игрок исчез из БД (теоретически невозможно, но не падаем).
                continue
            info = ClanMemberCardInfo(
                summary=player_to_summary(player),
                role=membership.role,
                joined_at=membership.joined_at,
            )
            member_infos.append(info)
            if player.status is PlayerStatus.ACTIVE:
                active_count += 1
                total_length_cm += player.length.cm
            if membership.role is ClanMemberRole.LEADER and leader is None:
                leader = info

        return ClanCard(
            clan_id=clan_id,
            chat_id=clan.chat_id,
            chat_kind=clan.chat_kind.value,
            title=clan.title.value,
            status=clan.status,
            created_at=clan.created_at,
            updated_at=clan.updated_at,
            member_count=len(member_infos),
            active_member_count=active_count,
            total_length_cm=total_length_cm,
            leader=leader,
            members=tuple(member_infos),
        )


__all__ = [
    "ClanCard",
    "ClanMemberCardInfo",
    "GetClanCard",
    "GetClanCardInput",
    "GetClanCardOutput",
]
