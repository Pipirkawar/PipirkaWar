"""Use-case `FindPlayers` (Спринт 2.5-B.1, ГДД §18.6.5).

`/find_player <text>` — поиск игроков по `tg_id` (точно), `@username`
(точно) либо по подстроке (ILIKE по `username`/`name`).

* Без TOTP (read-only — но всё равно пишем в `admin_audit_log`,
  чтобы super-admin в `/audit` видел, кто кого пробивал — ГДД §18.6.4).
* Авторизация: только активные админы (любая роль с правом support+).
  Прав `support` достаточно — read-side; `support+` означает «не
  read-only».
* Лимит результатов — параметр use-case-а (default 10), верхняя
  граница защищает от случая «`/find_player a`» с миллионом матчей.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
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
from pipirik_wars.domain.player import IPlayerRepository, Player, PlayerStatus
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork

#: Максимум результатов одной выдачи `/find_player`. Хватает для
#: типичного «помню часть @-шки или имени», и не разносит сообщение
#: Telegram-а на несколько кусков.
DEFAULT_FIND_PLAYERS_LIMIT = 10


@dataclass(frozen=True, slots=True)
class FindPlayersInput:
    """Параметры поиска игроков."""

    actor_tg_id: int
    query: str
    tg_chat_id: int | None = None
    source: AdminAuditSource = AdminAuditSource.BOT
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class PlayerSummary:
    """Сводка игрока для `/find_player`-выдачи и админ-логов.

    Сокращённый снимок `Player`. Хранит ровно то, что показывает
    презентер; не тащит за собой `created_at` / `updated_at` /
    `locale_override`, чтобы не плодить шум.
    """

    tg_id: int
    username: str | None
    name: str | None
    title: str | None
    length_cm: int
    thickness_level: int
    status: PlayerStatus
    anticheat_ban_until: datetime | None


@dataclass(frozen=True, slots=True)
class FindPlayersOutput:
    """Результат поиска: упорядоченная (по `id ASC`) сводка."""

    query: str
    results: Sequence[PlayerSummary]


def player_to_summary(player: Player) -> PlayerSummary:
    """Сжать `Player`-агрегат до сводки `PlayerSummary`.

    Вынесено наружу одним именем — `GetPlayerCard` (B.2) использует
    тот же контракт сводки, чтобы handler-ы `/find_player` и `/player`
    рендерили одну и ту же шапку игрока.
    """
    return PlayerSummary(
        tg_id=player.tg_id,
        username=player.username.value if player.username is not None else None,
        name=player.name.value if player.name is not None else None,
        title=player.title.value if player.title is not None else None,
        length_cm=player.length.cm,
        thickness_level=player.thickness.level,
        status=player.status,
        anticheat_ban_until=player.anticheat_ban_until,
    )


class FindPlayers:
    """Use-case поиска игроков для админских команд поддержки."""

    __slots__ = ("_admins", "_audit", "_authz", "_clock", "_limit", "_players", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        players: IPlayerRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
        limit: int = DEFAULT_FIND_PLAYERS_LIMIT,
    ) -> None:
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        self._uow = uow
        self._admins = admins
        self._players = players
        self._audit = audit
        self._clock = clock
        self._authz = authz
        self._limit = limit

    async def execute(self, inp: FindPlayersInput) -> FindPlayersOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        # `admin.id` гарантирован репо-инвариантом (см. RequestAdminConfirm).
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover — invariant of the repo
            raise RuntimeError("admin.id is None after get_by_tg_id")

        normalized_query = inp.query.strip()
        now = self._clock.now()

        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.FIND_PLAYER,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="player_query",
            target_id=normalized_query or "<empty>",
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
            source=inp.source,
            ip=inp.ip,
        )
        async with self._uow:
            if not normalized_query:
                rows: Sequence[Player] = ()
            else:
                rows = await self._players.find_by_query(
                    query=normalized_query,
                    limit=self._limit,
                )
            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_PLAYER_LOOKUP,
                    target_kind="player_query",
                    target_id=normalized_query or "<empty>",
                    before=None,
                    after={"matches": len(rows)},
                    reason=f"find_player:{normalized_query or '<empty>'}",
                    idempotency_key=None,
                    source=inp.source,
                    tg_chat_id=inp.tg_chat_id,
                    ip=inp.ip,
                    occurred_at=now,
                ),
            )

        return FindPlayersOutput(
            query=normalized_query,
            results=tuple(player_to_summary(row) for row in rows),
        )


__all__ = [
    "DEFAULT_FIND_PLAYERS_LIMIT",
    "FindPlayers",
    "FindPlayersInput",
    "FindPlayersOutput",
    "PlayerSummary",
    "player_to_summary",
]
