"""Use-case `GetClanDailyHeadHistory` (Спринт 2.5-D.3).

`/clan_daily_head_history <id|chat_id> [N=10]` — read-only история
последних N назначений «Главы клана дня» для клана: дата, игрок,
bonus_cm, источник (button/cron).

Не требует TOTP — read-only. Сам факт чтения логируется как
`ADMIN_CLAN_LOOKUP` (тот же ключ, что у `/clan` — для админа это всё
«пробивка клана»).

Контракт:

- актор должен быть `Admin.is_active` — иначе `AuthorizationError`;
- если клан не найден ни по `id`, ни по `chat_id` → `entries=()`;
- иначе через `IDailyHeadRepository.list_recent_for_clan(clan_id,
  limit)` берём последние `limit` назначений и enrichим каждое
  именем/username-ом игрока (один батч-запрос индивидуальных
  `players.get_by_id` — допустимо, история = 10 строк).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

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
from pipirik_wars.domain.clan import IClanRepository
from pipirik_wars.domain.daily_head.entities import DailyHeadSource
from pipirik_wars.domain.daily_head.repositories import IDailyHeadRepository
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork

DEFAULT_LIMIT = 10
MAX_LIMIT = 50


@dataclass(frozen=True, slots=True)
class GetClanDailyHeadHistoryInput:
    actor_tg_id: int
    query: int
    limit: int = DEFAULT_LIMIT
    tg_chat_id: int | None = None
    source: AdminAuditSource = AdminAuditSource.BOT
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class DailyHeadHistoryEntry:
    """Одна строка истории `daily_heads`."""

    moscow_date: date
    assigned_at: datetime
    bonus_cm: int
    source: DailyHeadSource
    player: PlayerSummary | None  # None — orphan (игрок удалён из БД).


@dataclass(frozen=True, slots=True)
class GetClanDailyHeadHistoryOutput:
    query: int
    clan_id: int | None
    clan_title: str | None
    entries: tuple[DailyHeadHistoryEntry, ...]


class GetClanDailyHeadHistory:
    """Use-case `/clan_daily_head_history`."""

    __slots__ = (
        "_admins",
        "_audit",
        "_authz",
        "_clans",
        "_clock",
        "_daily_heads",
        "_players",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        clans: IClanRepository,
        players: IPlayerRepository,
        daily_heads: IDailyHeadRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._clans = clans
        self._players = players
        self._daily_heads = daily_heads
        self._audit = audit
        self._clock = clock
        self._authz = authz

    async def execute(
        self,
        inp: GetClanDailyHeadHistoryInput,
    ) -> GetClanDailyHeadHistoryOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            raise RuntimeError("admin.id is None after get_by_tg_id")

        # Хард-капы: 1..MAX_LIMIT, дефолт DEFAULT_LIMIT.
        limit = max(1, min(MAX_LIMIT, inp.limit))

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.GET_CLAN_DAILY_HEAD_HISTORY,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="clan",
            target_id=str(inp.query),
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
            source=inp.source,
            ip=inp.ip,
        )
        async with self._uow:
            clan = await self._clans.get_by_id(inp.query)
            if clan is None:
                clan = await self._clans.get_by_chat_id(inp.query)

            entries: tuple[DailyHeadHistoryEntry, ...] = ()
            clan_id_int: int | None = None
            clan_title: str | None = None
            if clan is not None and clan.id is not None:
                clan_id_int = clan.id
                clan_title = clan.title.value
                rows = await self._daily_heads.list_recent_for_clan(
                    clan_id=clan.id,
                    limit=limit,
                )
                built: list[DailyHeadHistoryEntry] = []
                for row in rows:
                    player = await self._players.get_by_id(player_id=row.player_id)
                    summary = player_to_summary(player) if player is not None else None
                    built.append(
                        DailyHeadHistoryEntry(
                            moscow_date=row.moscow_date,
                            assigned_at=row.assigned_at,
                            bonus_cm=row.bonus_cm,
                            source=row.source,
                            player=summary,
                        ),
                    )
                entries = tuple(built)

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_CLAN_LOOKUP,
                    target_kind="clan",
                    target_id=str(inp.query),
                    before=None,
                    after={
                        "lookup": "daily_head_history",
                        "found": clan is not None,
                        "rows": len(entries),
                    },
                    reason=f"clan_daily_head_history:{inp.query}",
                    idempotency_key=None,
                    source=inp.source,
                    tg_chat_id=inp.tg_chat_id,
                    ip=inp.ip,
                    occurred_at=now,
                ),
            )

        return GetClanDailyHeadHistoryOutput(
            query=inp.query,
            clan_id=clan_id_int,
            clan_title=clan_title,
            entries=entries,
        )


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "DailyHeadHistoryEntry",
    "GetClanDailyHeadHistory",
    "GetClanDailyHeadHistoryInput",
    "GetClanDailyHeadHistoryOutput",
]
