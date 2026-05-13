"""Unit-тесты паритета source=BOT / source=WEB для admin use-case-ов (Sprint 4.5-I).

Каждый тест вызывает один use-case дважды — с source=BOT и source=WEB —
и проверяет, что результат идентичен, а audit-записи отличаются только полем source/ip.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin.ban_player import BanPlayer, BanPlayerInput
from pipirik_wars.application.admin.find_players import FindPlayers, FindPlayersInput
from pipirik_wars.application.admin.freeze_clan import FreezeClanAdmin, FreezeClanAdminInput
from pipirik_wars.application.admin.freeze_player import FreezePlayer, FreezePlayerInput
from pipirik_wars.application.admin.get_admin_audit_trail import (
    GetAdminAuditTrail,
    GetAdminAuditTrailInput,
)
from pipirik_wars.application.admin.get_balance_value import (
    GetBalanceValue,
    GetBalanceValueInput,
)
from pipirik_wars.application.admin.unfreeze_clan import UnfreezeClanAdmin, UnfreezeClanAdminInput
from pipirik_wars.application.admin.unfreeze_player import UnfreezePlayer, UnfreezePlayerInput
from pipirik_wars.domain.admin import AdminAuditAction, AdminAuditSource, AdminRole
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.clan import ChatKind, Clan, ClanStatus, ClanTitle
from pipirik_wars.domain.player import Player, PlayerStatus, Username
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_audit_query import FakeAdminAuditQuery
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.balance import FakeBalanceConfig
from tests.fakes.clan_repo import FakeClanRepository
from tests.fakes.clock import FakeClock
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.uow import FakeUnitOfWork
from tests.unit.domain.balance.factories import valid_balance_payload

_NOW = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)


def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    status: PlayerStatus = PlayerStatus.ACTIVE,
) -> Player:
    new_id = (max((p.id or 0 for p in players.rows), default=0)) + 1
    base = Player.new(tg_id=tg_id, username=Username(value="test_user"), now=_NOW)
    seeded = replace(base, id=new_id, status=status)
    players.rows.append(seeded)
    return seeded


# ---------------------------------------------------------------------------
# BanPlayer
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestBanPlayerSourceParity:
    """BanPlayer: source=BOT and source=WEB produce identical results."""

    async def test_bot_source_recorded(self) -> None:
        admins = FakeAdminRepository()
        players = FakePlayerRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100)

        uc = BanPlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            BanPlayerInput(
                actor_tg_id=42,
                target_tg_id=100,
                reason="test",
                source=AdminAuditSource.BOT,
                tg_chat_id=-100,
            ),
        )
        assert out.was_already_banned is False
        assert len(audit.entries) == 1
        assert audit.entries[0].source == AdminAuditSource.BOT
        assert audit.entries[0].ip is None
        assert audit.entries[0].tg_chat_id == -100

    async def test_web_source_recorded(self) -> None:
        admins = FakeAdminRepository()
        players = FakePlayerRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100)

        uc = BanPlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            BanPlayerInput(
                actor_tg_id=42,
                target_tg_id=100,
                reason="test",
                source=AdminAuditSource.WEB,
                ip="10.0.0.1",
            ),
        )
        assert out.was_already_banned is False
        assert len(audit.entries) == 1
        assert audit.entries[0].source == AdminAuditSource.WEB
        assert audit.entries[0].ip == "10.0.0.1"
        assert audit.entries[0].tg_chat_id is None

    async def test_bot_web_identical_outcome(self) -> None:
        for src, ip, chat in [
            (AdminAuditSource.BOT, None, -100),
            (AdminAuditSource.WEB, "1.2.3.4", None),
        ]:
            admins = FakeAdminRepository()
            players = FakePlayerRepository()
            audit = FakeAdminAuditLogger()
            uow = FakeUnitOfWork()
            admins.seed(tg_id=42, role=AdminRole.SUPPORT)
            _seed_player(players, tg_id=100)

            uc = BanPlayer(
                uow=uow,
                admins=admins,
                players=players,
                audit=audit,
                clock=FakeClock(_NOW),
                authz=FakeAdminAuthzAllowAll(),
            )
            out = await uc.execute(
                BanPlayerInput(
                    actor_tg_id=42,
                    target_tg_id=100,
                    reason="same reason",
                    source=src,
                    ip=ip,
                    tg_chat_id=chat,
                ),
            )
            assert out.was_already_banned is False
            assert players.rows[0].status is PlayerStatus.BANNED
            assert len(audit.entries) == 1
            assert audit.entries[0].action == AdminAuditAction.ADMIN_PLAYER_BANNED
            assert audit.entries[0].source == src


# ---------------------------------------------------------------------------
# FreezePlayer
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestFreezePlayerSourceParity:
    async def test_bot_source(self) -> None:
        admins = FakeAdminRepository()
        players = FakePlayerRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=200)

        uc = FreezePlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            FreezePlayerInput(
                actor_tg_id=1,
                target_tg_id=200,
                source=AdminAuditSource.BOT,
                tg_chat_id=-1,
            ),
        )
        assert not out.was_already_frozen
        assert audit.entries[0].source == AdminAuditSource.BOT

    async def test_web_source(self) -> None:
        admins = FakeAdminRepository()
        players = FakePlayerRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=200)

        uc = FreezePlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            FreezePlayerInput(
                actor_tg_id=1,
                target_tg_id=200,
                source=AdminAuditSource.WEB,
                ip="10.0.0.2",
            ),
        )
        assert not out.was_already_frozen
        assert audit.entries[0].source == AdminAuditSource.WEB
        assert audit.entries[0].ip == "10.0.0.2"


# ---------------------------------------------------------------------------
# UnfreezePlayer
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestUnfreezePlayerSourceParity:
    async def test_bot_source(self) -> None:
        admins = FakeAdminRepository()
        players = FakePlayerRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=300, status=PlayerStatus.FROZEN)

        uc = UnfreezePlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            UnfreezePlayerInput(
                actor_tg_id=1,
                target_tg_id=300,
                source=AdminAuditSource.BOT,
                tg_chat_id=-1,
            ),
        )
        assert not out.was_already_active
        assert audit.entries[0].source == AdminAuditSource.BOT

    async def test_web_source(self) -> None:
        admins = FakeAdminRepository()
        players = FakePlayerRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=300, status=PlayerStatus.FROZEN)

        uc = UnfreezePlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            UnfreezePlayerInput(
                actor_tg_id=1,
                target_tg_id=300,
                source=AdminAuditSource.WEB,
                ip="192.168.1.1",
            ),
        )
        assert not out.was_already_active
        assert audit.entries[0].source == AdminAuditSource.WEB
        assert audit.entries[0].ip == "192.168.1.1"


# ---------------------------------------------------------------------------
# FindPlayers
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestFindPlayersSourceParity:
    async def test_bot_source(self) -> None:
        admins = FakeAdminRepository()
        players = FakePlayerRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=400)

        uc = FindPlayers(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            FindPlayersInput(
                actor_tg_id=1,
                query="400",
                source=AdminAuditSource.BOT,
                tg_chat_id=-1,
            ),
        )
        assert len(out.results) == 1
        assert audit.entries[0].source == AdminAuditSource.BOT

    async def test_web_source(self) -> None:
        admins = FakeAdminRepository()
        players = FakePlayerRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=400)

        uc = FindPlayers(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            FindPlayersInput(
                actor_tg_id=1,
                query="400",
                source=AdminAuditSource.WEB,
                ip="10.0.0.3",
            ),
        )
        assert len(out.results) == 1
        assert audit.entries[0].source == AdminAuditSource.WEB
        assert audit.entries[0].ip == "10.0.0.3"


def _seed_clan(
    clans: FakeClanRepository,
    *,
    clan_id: int = 10,
    chat_id: int = -100500,
    title: str = "TestClan",
    status: ClanStatus = ClanStatus.ACTIVE,
) -> Clan:
    clan = Clan(
        id=clan_id,
        chat_id=chat_id,
        chat_kind=ChatKind.GROUP,
        title=ClanTitle(value=title),
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )
    clans.rows.append(clan)
    return clan


# ---------------------------------------------------------------------------
# FreezeClanAdmin
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestFreezeClanSourceParity:
    async def test_bot_source(self) -> None:
        admins = FakeAdminRepository()
        clans = FakeClanRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)
        _seed_clan(clans, clan_id=10, chat_id=10000, title="Tribe")

        uc = FreezeClanAdmin(
            uow=uow,
            admins=admins,
            clans=clans,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            FreezeClanAdminInput(
                actor_tg_id=1,
                query=10,
                source=AdminAuditSource.BOT,
                tg_chat_id=-1,
            ),
        )
        assert out.outcome == "frozen"
        assert audit.entries[0].source == AdminAuditSource.BOT

    async def test_web_source(self) -> None:
        admins = FakeAdminRepository()
        clans = FakeClanRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)
        _seed_clan(clans, clan_id=10, chat_id=10000, title="Tribe")

        uc = FreezeClanAdmin(
            uow=uow,
            admins=admins,
            clans=clans,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            FreezeClanAdminInput(
                actor_tg_id=1,
                query=10,
                source=AdminAuditSource.WEB,
                ip="172.16.0.1",
            ),
        )
        assert out.outcome == "frozen"
        assert audit.entries[0].source == AdminAuditSource.WEB
        assert audit.entries[0].ip == "172.16.0.1"


# ---------------------------------------------------------------------------
# UnfreezeClanAdmin
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestUnfreezeClanSourceParity:
    async def test_bot_source(self) -> None:
        admins = FakeAdminRepository()
        clans = FakeClanRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)
        _seed_clan(clans, clan_id=20, chat_id=20000, title="Tribe2", status=ClanStatus.FROZEN)

        uc = UnfreezeClanAdmin(
            uow=uow,
            admins=admins,
            clans=clans,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            UnfreezeClanAdminInput(
                actor_tg_id=1,
                query=20,
                source=AdminAuditSource.BOT,
                tg_chat_id=-1,
            ),
        )
        assert out.outcome == "unfrozen"
        assert audit.entries[0].source == AdminAuditSource.BOT

    async def test_web_source(self) -> None:
        admins = FakeAdminRepository()
        clans = FakeClanRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)
        _seed_clan(clans, clan_id=20, chat_id=20000, title="Tribe2", status=ClanStatus.FROZEN)

        uc = UnfreezeClanAdmin(
            uow=uow,
            admins=admins,
            clans=clans,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            UnfreezeClanAdminInput(
                actor_tg_id=1,
                query=20,
                source=AdminAuditSource.WEB,
                ip="172.16.0.2",
            ),
        )
        assert out.outcome == "unfrozen"
        assert audit.entries[0].source == AdminAuditSource.WEB
        assert audit.entries[0].ip == "172.16.0.2"


# ---------------------------------------------------------------------------
# GetBalanceValue
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestGetBalanceValueSourceParity:
    async def test_bot_source(self) -> None:
        admins = FakeAdminRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)

        balance = FakeBalanceConfig(BalanceConfig.model_validate(valid_balance_payload()))
        uc = GetBalanceValue(
            uow=uow,
            admins=admins,
            balance=balance,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            GetBalanceValueInput(
                actor_tg_id=1,
                key="version",
                source=AdminAuditSource.BOT,
                tg_chat_id=-1,
            ),
        )
        assert out.key == "version"
        assert audit.entries[0].source == AdminAuditSource.BOT
        assert audit.entries[0].action == AdminAuditAction.ADMIN_BALANCE_GET

    async def test_web_source(self) -> None:
        admins = FakeAdminRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPPORT)

        balance = FakeBalanceConfig(BalanceConfig.model_validate(valid_balance_payload()))
        uc = GetBalanceValue(
            uow=uow,
            admins=admins,
            balance=balance,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            GetBalanceValueInput(
                actor_tg_id=1,
                key="version",
                source=AdminAuditSource.WEB,
                ip="10.0.0.5",
            ),
        )
        assert out.key == "version"
        assert audit.entries[0].source == AdminAuditSource.WEB
        assert audit.entries[0].ip == "10.0.0.5"


# ---------------------------------------------------------------------------
# GetAdminAuditTrail
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestGetAdminAuditTrailSourceParity:
    async def test_bot_source(self) -> None:
        admins = FakeAdminRepository()
        audit = FakeAdminAuditLogger()
        query = FakeAdminAuditQuery()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPER_ADMIN)

        uc = GetAdminAuditTrail(
            uow=uow,
            admins=admins,
            query=query,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            GetAdminAuditTrailInput(
                actor_tg_id=1,
                source=AdminAuditSource.BOT,
                tg_chat_id=-1,
            ),
        )
        assert out.records is not None
        assert audit.entries[0].source == AdminAuditSource.BOT
        assert audit.entries[0].action == AdminAuditAction.ADMIN_AUDIT_QUERIED

    async def test_web_source(self) -> None:
        admins = FakeAdminRepository()
        audit = FakeAdminAuditLogger()
        query = FakeAdminAuditQuery()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=1, role=AdminRole.SUPER_ADMIN)

        uc = GetAdminAuditTrail(
            uow=uow,
            admins=admins,
            query=query,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            GetAdminAuditTrailInput(
                actor_tg_id=1,
                source=AdminAuditSource.WEB,
                ip="10.0.0.6",
            ),
        )
        assert out.records is not None
        assert audit.entries[0].source == AdminAuditSource.WEB
        assert audit.entries[0].ip == "10.0.0.6"


# ---------------------------------------------------------------------------
# Default source = BOT (backward-compatibility)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestDefaultSourceIsBotBackwardCompat:
    """Ensure that omitting source defaults to BOT (backward-compatible)."""

    async def test_ban_player_default_source(self) -> None:
        admins = FakeAdminRepository()
        players = FakePlayerRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100)

        uc = BanPlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            BanPlayerInput(actor_tg_id=42, target_tg_id=100, reason="test"),
        )
        assert out.was_already_banned is False
        assert audit.entries[0].source == AdminAuditSource.BOT
        assert audit.entries[0].ip is None

    async def test_freeze_player_default_source(self) -> None:
        admins = FakeAdminRepository()
        players = FakePlayerRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100)

        uc = FreezePlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            FreezePlayerInput(actor_tg_id=42, target_tg_id=100),
        )
        assert not out.was_already_frozen
        assert audit.entries[0].source == AdminAuditSource.BOT

    async def test_find_players_default_source(self) -> None:
        admins = FakeAdminRepository()
        players = FakePlayerRepository()
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100)

        uc = FindPlayers(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        )
        out = await uc.execute(
            FindPlayersInput(actor_tg_id=42, query="100"),
        )
        assert len(out.results) == 1
        assert audit.entries[0].source == AdminAuditSource.BOT
