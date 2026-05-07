"""Unit-тесты `BanPlayer` (Спринт 2.5-B.4)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import BanPlayer, BanPlayerInput
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import AdminAuditAction, AdminAuditSource, AdminRole
from pipirik_wars.domain.player import Player, PlayerStatus, Username
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clock import FakeClock
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.uow import FakeUnitOfWork

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    status: PlayerStatus = PlayerStatus.ACTIVE,
) -> Player:
    new_id = (max((p.id or 0 for p in players.rows), default=0)) + 1
    base = Player.new(tg_id=tg_id, username=Username(value="ivan"), now=_NOW)
    seeded = replace(base, id=new_id, status=status)
    players.rows.append(seeded)
    return seeded


def _build() -> tuple[
    BanPlayer,
    FakeAdminRepository,
    FakePlayerRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    players = FakePlayerRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    return (
        BanPlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        ),
        admins,
        players,
        audit,
        uow,
    )


@pytest.mark.asyncio
class TestBanPlayer:
    async def test_inactive_admin_raises(self) -> None:
        uc, admins, _p, audit, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT, is_active=False)

        with pytest.raises(AuthorizationError):
            await uc.execute(
                BanPlayerInput(actor_tg_id=42, target_tg_id=100, reason="x"),
            )
        assert audit.entries == []
        assert uow.commits == 0

    async def test_unknown_admin_raises(self) -> None:
        uc, _admins, _p, audit, uow = _build()

        with pytest.raises(AuthorizationError):
            await uc.execute(
                BanPlayerInput(actor_tg_id=999, target_tg_id=100, reason="x"),
            )
        assert audit.entries == []
        assert uow.commits == 0

    async def test_empty_reason_raises_value_error(self) -> None:
        uc, admins, players, audit, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100)

        with pytest.raises(ValueError, match="reason"):
            await uc.execute(
                BanPlayerInput(actor_tg_id=42, target_tg_id=100, reason="   "),
            )
        # Player не тронут.
        assert players.rows[0].status is PlayerStatus.ACTIVE
        assert audit.entries == []

    async def test_unknown_player_raises(self) -> None:
        uc, admins, _p, audit, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        with pytest.raises(PlayerNotFoundError):
            await uc.execute(
                BanPlayerInput(actor_tg_id=42, target_tg_id=999, reason="макрос"),
            )
        assert audit.entries == []
        assert uow.rollbacks == 1

    async def test_ban_active_player(self) -> None:
        uc, admins, players, audit, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100)

        out = await uc.execute(
            BanPlayerInput(
                actor_tg_id=42,
                target_tg_id=100,
                reason="макрос пойман",
                tg_chat_id=-100500,
            ),
        )

        assert out.was_already_banned is False
        assert players.rows[0].status is PlayerStatus.BANNED
        assert uow.commits == 1
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_PLAYER_BANNED
        assert a.target_kind == "player"
        assert a.target_id == "100"
        assert a.before == {"status": "active"}
        assert a.after == {"status": "banned"}
        assert a.reason == "макрос пойман"
        assert a.source == AdminAuditSource.BOT
        assert a.tg_chat_id == -100500

    async def test_ban_frozen_player_overrides_status(self) -> None:
        uc, admins, players, audit, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100, status=PlayerStatus.FROZEN)

        out = await uc.execute(
            BanPlayerInput(actor_tg_id=42, target_tg_id=100, reason="макрос"),
        )

        assert out.was_already_banned is False
        assert players.rows[0].status is PlayerStatus.BANNED
        assert audit.entries[0].before == {"status": "frozen"}
        assert audit.entries[0].after == {"status": "banned"}
        assert uow.commits == 1

    async def test_ban_already_banned_is_noop(self) -> None:
        uc, admins, players, audit, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100, status=PlayerStatus.BANNED)

        out = await uc.execute(
            BanPlayerInput(actor_tg_id=42, target_tg_id=100, reason="макрос"),
        )

        assert out.was_already_banned is True
        # Без записи в аудит и без save (но commit на read-only OK).
        assert audit.entries == []
        assert uow.commits == 1
