"""Unit-тесты `GetClanDailyHeadHistory` (Спринт 2.5-D.3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from pipirik_wars.application.admin import (
    GetClanDailyHeadHistory,
    GetClanDailyHeadHistoryInput,
)
from pipirik_wars.application.admin.get_clan_daily_head_history import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditSource,
    AdminRole,
)
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanStatus,
    ClanTitle,
)
from pipirik_wars.domain.daily_head.entities import (
    DailyHeadAssignment,
    DailyHeadSource,
)
from pipirik_wars.domain.player import Player, Username
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clan_repo import FakeClanRepository
from tests.fakes.clock import FakeClock
from tests.fakes.daily_head import FakeDailyHeadRepository
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.uow import FakeUnitOfWork

_FIXED_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _build() -> tuple[
    GetClanDailyHeadHistory,
    FakeAdminRepository,
    FakeClanRepository,
    FakePlayerRepository,
    FakeDailyHeadRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    clans = FakeClanRepository()
    players = FakePlayerRepository()
    daily_heads = FakeDailyHeadRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    use_case = GetClanDailyHeadHistory(
        uow=uow,
        admins=admins,
        clans=clans,
        players=players,
        daily_heads=daily_heads,
        audit=audit,
        clock=FakeClock(_FIXED_NOW),
        authz=FakeAdminAuthzAllowAll(),
    )
    return use_case, admins, clans, players, daily_heads, audit, uow


def _seed_clan(clans: FakeClanRepository, *, chat_id: int = -1, title: str = "C") -> Clan:
    new_id = (max((c.id or 0 for c in clans.rows), default=0)) + 1
    clan = Clan(
        id=new_id,
        chat_id=chat_id,
        chat_kind=ChatKind.GROUP,
        title=ClanTitle(value=title),
        status=ClanStatus.ACTIVE,
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
    )
    clans.rows.append(clan)
    return clan


def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str | None = "player",
) -> Player:
    new_id = (max((p.id or 0 for p in players.rows), default=0)) + 1
    base = Player.new(
        tg_id=tg_id,
        username=Username(value=username) if username is not None else None,
        now=_FIXED_NOW,
    )
    seeded = replace(base, id=new_id)
    players.rows.append(seeded)
    return seeded


def _seed_assignment(
    daily_heads: FakeDailyHeadRepository,
    *,
    clan_id: int,
    player_id: int,
    moscow_date: date,
    bonus_cm: int = 5,
    assigned_at: datetime,
    source: DailyHeadSource = DailyHeadSource.CRON,
) -> DailyHeadAssignment:
    assignment = DailyHeadAssignment(
        id=None,
        clan_id=clan_id,
        player_id=player_id,
        moscow_date=moscow_date,
        source=source,
        bonus_cm=bonus_cm,
        assigned_at=assigned_at,
    )
    new_id = daily_heads._next_id
    saved = replace(assignment, id=new_id)
    daily_heads._next_id += 1
    daily_heads.items.append(saved)
    return saved


@pytest.mark.asyncio
class TestGetClanDailyHeadHistory:
    async def test_unknown_admin_raises(self) -> None:
        uc, _admins, _c, _p, _dh, audit, uow = _build()
        with pytest.raises(AuthorizationError):
            await uc.execute(GetClanDailyHeadHistoryInput(actor_tg_id=999, query=1))
        assert audit.entries == []
        assert uow.commits == 0

    async def test_inactive_admin_raises(self) -> None:
        uc, admins, _c, _p, _dh, audit, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT, is_active=False)
        with pytest.raises(AuthorizationError):
            await uc.execute(GetClanDailyHeadHistoryInput(actor_tg_id=42, query=1))
        assert audit.entries == []

    async def test_clan_not_found_returns_empty_with_audit(self) -> None:
        uc, admins, _c, _p, _dh, audit, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        out = await uc.execute(
            GetClanDailyHeadHistoryInput(actor_tg_id=42, query=999, tg_chat_id=-1),
        )

        assert out.clan_id is None
        assert out.clan_title is None
        assert out.entries == ()
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_CLAN_LOOKUP
        assert a.target_kind == "clan"
        assert a.target_id == "999"
        assert a.after == {"lookup": "daily_head_history", "found": False, "rows": 0}
        assert a.tg_chat_id == -1
        assert a.source == AdminAuditSource.BOT
        assert a.reason == "clan_daily_head_history:999"

    async def test_returns_recent_entries_sorted_desc(self) -> None:
        uc, admins, clans, players, daily_heads, audit, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, title="The Pipiriks")
        assert clan.id is not None
        p1 = _seed_player(players, tg_id=100, username="alice")
        p2 = _seed_player(players, tg_id=101, username="bob")
        assert p1.id is not None and p2.id is not None
        # Старая запись.
        _seed_assignment(
            daily_heads,
            clan_id=clan.id,
            player_id=p1.id,
            moscow_date=date(2026, 5, 6),
            assigned_at=_FIXED_NOW - timedelta(days=2),
            source=DailyHeadSource.CRON,
        )
        # Свежая запись.
        _seed_assignment(
            daily_heads,
            clan_id=clan.id,
            player_id=p2.id,
            moscow_date=date(2026, 5, 7),
            assigned_at=_FIXED_NOW - timedelta(days=1),
            source=DailyHeadSource.BUTTON,
        )

        out = await uc.execute(
            GetClanDailyHeadHistoryInput(actor_tg_id=42, query=clan.id),
        )

        assert out.clan_id == clan.id
        assert out.clan_title == "The Pipiriks"
        assert len(out.entries) == 2
        # Первая — свежая (DESC).
        assert out.entries[0].moscow_date == date(2026, 5, 7)
        assert out.entries[0].source is DailyHeadSource.BUTTON
        assert out.entries[0].player is not None
        assert out.entries[0].player.tg_id == 101
        # Вторая — старая.
        assert out.entries[1].moscow_date == date(2026, 5, 6)
        assert out.entries[1].source is DailyHeadSource.CRON
        # Audit с подсчётом.
        assert audit.entries[-1].after == {
            "lookup": "daily_head_history",
            "found": True,
            "rows": 2,
        }

    async def test_orphan_player_renders_none(self) -> None:
        uc, admins, clans, _p, daily_heads, _audit, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans)
        assert clan.id is not None
        # player_id=999 — игрок не существует в БД.
        _seed_assignment(
            daily_heads,
            clan_id=clan.id,
            player_id=999,
            moscow_date=date(2026, 5, 7),
            assigned_at=_FIXED_NOW,
        )

        out = await uc.execute(
            GetClanDailyHeadHistoryInput(actor_tg_id=42, query=clan.id),
        )

        assert len(out.entries) == 1
        assert out.entries[0].player is None
        assert out.entries[0].moscow_date == date(2026, 5, 7)

    async def test_default_limit_applied(self) -> None:
        uc, admins, clans, players, daily_heads, _audit, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans)
        assert clan.id is not None
        p = _seed_player(players, tg_id=100)
        assert p.id is not None
        for i in range(15):  # 15 записей — больше чем DEFAULT_LIMIT=10
            _seed_assignment(
                daily_heads,
                clan_id=clan.id,
                player_id=p.id,
                moscow_date=date(2026, 4, 1) + timedelta(days=i),
                assigned_at=_FIXED_NOW - timedelta(days=15 - i),
            )

        # Без limit — должен использоваться DEFAULT_LIMIT.
        out = await uc.execute(
            GetClanDailyHeadHistoryInput(actor_tg_id=42, query=clan.id),
        )
        assert len(out.entries) == DEFAULT_LIMIT

    async def test_limit_capped_to_max(self) -> None:
        uc, admins, clans, players, daily_heads, _audit, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans)
        assert clan.id is not None
        p = _seed_player(players, tg_id=100)
        assert p.id is not None
        for i in range(MAX_LIMIT + 10):
            _seed_assignment(
                daily_heads,
                clan_id=clan.id,
                player_id=p.id,
                moscow_date=date(2026, 1, 1) + timedelta(days=i),
                assigned_at=_FIXED_NOW - timedelta(days=MAX_LIMIT + 10 - i),
            )

        # Запрашиваем 100 — должно быть обрезано до MAX_LIMIT.
        out = await uc.execute(
            GetClanDailyHeadHistoryInput(actor_tg_id=42, query=clan.id, limit=100),
        )
        assert len(out.entries) == MAX_LIMIT

    async def test_limit_floor_to_one(self) -> None:
        uc, admins, clans, players, daily_heads, _audit, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans)
        assert clan.id is not None
        p = _seed_player(players, tg_id=100)
        assert p.id is not None
        _seed_assignment(
            daily_heads,
            clan_id=clan.id,
            player_id=p.id,
            moscow_date=date(2026, 5, 7),
            assigned_at=_FIXED_NOW,
        )
        # limit=0 — но мы тебе не дадим, как минимум одну строку.
        out = await uc.execute(
            GetClanDailyHeadHistoryInput(actor_tg_id=42, query=clan.id, limit=0),
        )
        assert len(out.entries) == 1

    async def test_lookup_by_chat_id_falls_back(self) -> None:
        uc, admins, clans, _p, _dh, _audit, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, chat_id=-987654, title="Karavashki")

        out = await uc.execute(
            GetClanDailyHeadHistoryInput(actor_tg_id=42, query=-987654),
        )
        assert out.clan_id == clan.id
        assert out.clan_title == "Karavashki"

    async def test_empty_history_returns_empty_entries(self) -> None:
        uc, admins, clans, _p, _dh, audit, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans)
        assert clan.id is not None

        out = await uc.execute(
            GetClanDailyHeadHistoryInput(actor_tg_id=42, query=clan.id),
        )

        assert out.clan_id == clan.id
        assert out.entries == ()
        assert audit.entries[-1].after == {
            "lookup": "daily_head_history",
            "found": True,
            "rows": 0,
        }
