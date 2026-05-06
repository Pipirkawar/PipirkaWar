"""Unit-тесты `FreezePlayer` и `UnfreezePlayer` (Спринт 2.5-B.3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import (
    FreezePlayer,
    FreezePlayerInput,
    UnfreezePlayer,
    UnfreezePlayerInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import AdminAuditAction, AdminAuditSource, AdminRole
from pipirik_wars.domain.player import (
    Player,
    PlayerStatus,
    Username,
)
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from tests.fakes.admin_audit import FakeAdminAuditLogger
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


def _build_freeze() -> tuple[
    FreezePlayer,
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
        FreezePlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
        ),
        admins,
        players,
        audit,
        uow,
    )


def _build_unfreeze() -> tuple[
    UnfreezePlayer,
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
        UnfreezePlayer(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            clock=FakeClock(_NOW),
        ),
        admins,
        players,
        audit,
        uow,
    )


@pytest.mark.asyncio
class TestFreezePlayer:
    async def test_inactive_admin_raises(self) -> None:
        uc, admins, _p, audit, uow = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT, is_active=False)

        with pytest.raises(AuthorizationError):
            await uc.execute(FreezePlayerInput(actor_tg_id=42, target_tg_id=100))

        assert audit.entries == []
        assert uow.commits == 0

    async def test_unknown_player_raises(self) -> None:
        uc, admins, _p, audit, uow = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        with pytest.raises(PlayerNotFoundError):
            await uc.execute(FreezePlayerInput(actor_tg_id=42, target_tg_id=999))

        assert audit.entries == []
        assert uow.commits == 0
        assert uow.rollbacks == 1

    async def test_freeze_active_writes_audit(self) -> None:
        uc, admins, players, audit, uow = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100)

        out = await uc.execute(
            FreezePlayerInput(
                actor_tg_id=42,
                target_tg_id=100,
                reason="тест",
                tg_chat_id=-100500,
            ),
        )

        assert out.was_already_frozen is False
        assert players.rows[0].status is PlayerStatus.FROZEN
        assert uow.commits == 1
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_PLAYER_FROZEN
        assert a.target_id == "100"
        assert a.before == {"status": "active"}
        assert a.after == {"status": "frozen"}
        assert a.reason == "тест"
        assert a.tg_chat_id == -100500
        assert a.source == AdminAuditSource.BOT

    async def test_freeze_already_frozen_is_noop(self) -> None:
        uc, admins, players, audit, uow = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100, status=PlayerStatus.FROZEN)

        out = await uc.execute(FreezePlayerInput(actor_tg_id=42, target_tg_id=100))

        assert out.was_already_frozen is True
        # Audit-лог чист (no-op никаких мутаций), но контекст UoW
        # закрылся штатно — commit==1 на read-only транзакции безопасен.
        assert audit.entries == []
        assert uow.commits == 1


@pytest.mark.asyncio
class TestUnfreezePlayer:
    async def test_inactive_admin_raises(self) -> None:
        uc, admins, _p, audit, uow = _build_unfreeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT, is_active=False)

        with pytest.raises(AuthorizationError):
            await uc.execute(UnfreezePlayerInput(actor_tg_id=42, target_tg_id=100))

        assert audit.entries == []
        assert uow.commits == 0

    async def test_unknown_player_raises(self) -> None:
        uc, admins, _p, audit, uow = _build_unfreeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        with pytest.raises(PlayerNotFoundError):
            await uc.execute(UnfreezePlayerInput(actor_tg_id=42, target_tg_id=999))

        assert audit.entries == []
        assert uow.commits == 0
        assert uow.rollbacks == 1

    async def test_unfreeze_frozen_writes_audit(self) -> None:
        uc, admins, players, audit, uow = _build_unfreeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100, status=PlayerStatus.FROZEN)

        out = await uc.execute(
            UnfreezePlayerInput(
                actor_tg_id=42,
                target_tg_id=100,
                reason="разморозка",
            ),
        )

        assert out.was_already_active is False
        assert players.rows[0].status is PlayerStatus.ACTIVE
        assert uow.commits == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_PLAYER_UNFROZEN
        assert a.target_id == "100"
        assert a.before == {"status": "frozen"}
        assert a.after == {"status": "active"}
        assert a.reason == "разморозка"

    async def test_unfreeze_already_active_is_noop(self) -> None:
        uc, admins, players, audit, uow = _build_unfreeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100)

        out = await uc.execute(UnfreezePlayerInput(actor_tg_id=42, target_tg_id=100))

        assert out.was_already_active is True
        assert audit.entries == []
        assert uow.commits == 1
