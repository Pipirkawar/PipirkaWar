"""Use-case `GetPlayerCard` (Спринт 2.5-B.2, ГДД §18.6.5).

`/player <tg_id>` — карточка игрока для админ-поддержки. Использует
**существующие** репо-методы, новых не вводит:

* `IPlayerRepository.get_by_tg_id` — основное состояние (длина,
  толщина, статус, anticheat-soft-ban-таймер).
* `IClanMembershipRepository.get_by_player` + `IClanRepository.get_by_id` —
  привязка к клану (если есть).
* `IForestRunRepository.get_active_by_player` — активный поход в лес
  (если есть): админу важно видеть `ends_at`, чтобы понимать, до какого
  момента игрок занят.

Список последних 5 PvP/PvE-боёв в карточку **не входит**: ни
`IDuelRepository`, ни `IMassDuelRepository`, ни `IForestRunRepository`
не имеют метода «список последних N для игрока». Заводить новые
read-методы поверх существующих агрегатов — отдельный шаг (B-followup
в `docs/current_tasks.md`); до тех пор админ видит активный forest-run
и поведенческие маркеры (anticheat / freeze).

Read-only — TOTP не нужен, но запись `ADMIN_PLAYER_LOOKUP` обязательна
(ГДД §18.6.4: super-admin должен видеть в `/audit`, кто и кого «пробивал»).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.admin.find_players import (
    PlayerSummary,
    player_to_summary,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminRepository,
)
from pipirik_wars.domain.clan import (
    ClanMemberRole,
    ClanStatus,
    IClanMembershipRepository,
    IClanRepository,
)
from pipirik_wars.domain.forest import ForestRunStatus, IForestRunRepository
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


@dataclass(frozen=True, slots=True)
class GetPlayerCardInput:
    """Параметры команды."""

    actor_tg_id: int
    target_tg_id: int
    tg_chat_id: int | None = None
    source: AdminAuditSource = AdminAuditSource.BOT
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class ClanCardInfo:
    """Сводка клана в карточке игрока."""

    clan_id: int
    chat_id: int
    title: str
    status: ClanStatus
    role: ClanMemberRole
    joined_at: datetime


@dataclass(frozen=True, slots=True)
class ForestCardInfo:
    """Сводка активного forest-run-а."""

    run_id: int
    started_at: datetime
    ends_at: datetime
    status: ForestRunStatus


@dataclass(frozen=True, slots=True)
class PlayerCard:
    """Карточка игрока для админ-выдачи `/player`.

    `summary` повторяет сводку из `/find_player` (длина, толщина,
    @username и т.п.), а сверху лежат «контекстные» поля админа: клан и
    активный forest-run. Если игрок не в клане / не в лесу — `None`.
    """

    summary: PlayerSummary
    clan: ClanCardInfo | None
    forest_active_run: ForestCardInfo | None


@dataclass(frozen=True, slots=True)
class GetPlayerCardOutput:
    """Карточка либо `None`, если игрока с таким `tg_id` нет."""

    target_tg_id: int
    card: PlayerCard | None


class GetPlayerCard:
    """Use-case рендеринга карточки игрока."""

    __slots__ = (
        "_admins",
        "_audit",
        "_authz",
        "_clan_members",
        "_clans",
        "_clock",
        "_forest_runs",
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
        forest_runs: IForestRunRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._players = players
        self._clans = clans
        self._clan_members = clan_members
        self._forest_runs = forest_runs
        self._audit = audit
        self._clock = clock
        self._authz = authz

    async def execute(self, inp: GetPlayerCardInput) -> GetPlayerCardOutput:
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

        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.GET_PLAYER_CARD,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="player",
            target_id=str(inp.target_tg_id),
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
            source=inp.source,
            ip=inp.ip,
        )

        async with self._uow:
            player = await self._players.get_by_tg_id(inp.target_tg_id)
            card: PlayerCard | None = None
            if player is not None and player.id is not None:
                clan_info = None
                membership = await self._clan_members.get_by_player(player.id)
                if membership is not None:
                    clan = await self._clans.get_by_id(membership.clan_id)
                    if clan is not None and clan.id is not None:
                        clan_info = ClanCardInfo(
                            clan_id=clan.id,
                            chat_id=clan.chat_id,
                            title=clan.title.value,
                            status=clan.status,
                            role=membership.role,
                            joined_at=membership.joined_at,
                        )

                forest_info = None
                run = await self._forest_runs.get_active_by_player(player_id=player.id)
                if run is not None and run.id is not None:
                    forest_info = ForestCardInfo(
                        run_id=run.id,
                        started_at=run.started_at,
                        ends_at=run.ends_at,
                        status=run.status,
                    )

                card = PlayerCard(
                    summary=player_to_summary(player),
                    clan=clan_info,
                    forest_active_run=forest_info,
                )

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_PLAYER_LOOKUP,
                    target_kind="player",
                    target_id=str(inp.target_tg_id),
                    before=None,
                    after={"found": card is not None},
                    reason=f"player_card:{inp.target_tg_id}",
                    idempotency_key=None,
                    source=inp.source,
                    tg_chat_id=inp.tg_chat_id,
                    ip=inp.ip,
                    occurred_at=now,
                ),
            )

        return GetPlayerCardOutput(target_tg_id=inp.target_tg_id, card=card)


__all__ = [
    "ClanCardInfo",
    "ForestCardInfo",
    "GetPlayerCard",
    "GetPlayerCardInput",
    "GetPlayerCardOutput",
    "PlayerCard",
]
