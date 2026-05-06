"""Unit-тесты `FreezeClanAdmin` / `UnfreezeClanAdmin` (Спринт 2.5-D.2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import (
    FreezeClanAdmin,
    FreezeClanAdminInput,
    UnfreezeClanAdmin,
    UnfreezeClanAdminInput,
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
)
from pipirik_wars.domain.clan.value_objects import ClanTitle
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clan_repo import FakeClanRepository
from tests.fakes.clock import FakeClock
from tests.fakes.uow import FakeUnitOfWork

_FIXED_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _build_freeze() -> tuple[
    FreezeClanAdmin,
    FakeAdminRepository,
    FakeClanRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    clans = FakeClanRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    use_case = FreezeClanAdmin(
        uow=uow,
        admins=admins,
        clans=clans,
        audit=audit,
        clock=FakeClock(_FIXED_NOW),
    )
    return use_case, admins, clans, audit, uow


def _build_unfreeze() -> tuple[
    UnfreezeClanAdmin,
    FakeAdminRepository,
    FakeClanRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    clans = FakeClanRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    use_case = UnfreezeClanAdmin(
        uow=uow,
        admins=admins,
        clans=clans,
        audit=audit,
        clock=FakeClock(_FIXED_NOW),
    )
    return use_case, admins, clans, audit, uow


def _seed_clan(
    clans: FakeClanRepository,
    *,
    chat_id: int = -100500,
    title: str = "C",
    status: ClanStatus = ClanStatus.ACTIVE,
) -> Clan:
    new_id = (max((c.id or 0 for c in clans.rows), default=0)) + 1
    clan = Clan(
        id=new_id,
        chat_id=chat_id,
        chat_kind=ChatKind.GROUP,
        title=ClanTitle(value=title),
        status=status,
        created_at=_FIXED_NOW,
        updated_at=_FIXED_NOW,
    )
    clans.rows.append(clan)
    return clan


@pytest.mark.asyncio
class TestFreezeClanAdmin:
    async def test_unknown_admin_raises(self) -> None:
        uc, _admins, _c, audit, uow = _build_freeze()
        with pytest.raises(AuthorizationError):
            await uc.execute(FreezeClanAdminInput(actor_tg_id=999, query=1))
        assert audit.entries == []
        assert uow.commits == 0

    async def test_inactive_admin_raises(self) -> None:
        uc, admins, _c, audit, uow = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT, is_active=False)
        with pytest.raises(AuthorizationError):
            await uc.execute(FreezeClanAdminInput(actor_tg_id=42, query=1))
        assert audit.entries == []
        assert uow.commits == 0

    async def test_clan_not_found_outcome(self) -> None:
        uc, admins, _c, audit, _u = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        out = await uc.execute(FreezeClanAdminInput(actor_tg_id=42, query=999))
        assert out.outcome == "not_found"
        assert out.clan is None
        assert audit.entries == []  # not_found = no audit

    async def test_freeze_active_clan_writes_audit_and_saves(self) -> None:
        uc, admins, clans, audit, uow = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans)
        assert clan.id is not None

        out = await uc.execute(
            FreezeClanAdminInput(
                actor_tg_id=42,
                query=clan.id,
                reason="abuse",
                tg_chat_id=-100,
            ),
        )

        assert out.outcome == "frozen"
        assert out.clan is not None
        assert out.clan.is_frozen
        # In-memory repo replaces the row, so we re-read.
        saved = await clans.get_by_id(clan.id)
        assert saved is not None
        assert saved.status is ClanStatus.FROZEN
        assert uow.commits == 1
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_CLAN_FROZEN
        assert a.target_kind == "clan"
        assert a.target_id == str(clan.id)
        assert a.before == {"status": "active"}
        assert a.after == {"status": "frozen"}
        assert a.reason == "abuse"
        assert a.tg_chat_id == -100
        assert a.source == AdminAuditSource.BOT

    async def test_already_frozen_is_idempotent_no_audit(self) -> None:
        uc, admins, clans, audit, _u = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, status=ClanStatus.FROZEN)
        assert clan.id is not None

        out = await uc.execute(FreezeClanAdminInput(actor_tg_id=42, query=clan.id))

        assert out.outcome == "already_frozen"
        assert out.clan is not None
        assert out.clan.is_frozen
        assert audit.entries == []  # no audit on idempotent no-op

    async def test_lookup_by_chat_id_falls_back(self) -> None:
        uc, admins, clans, audit, _u = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, chat_id=-987654)

        out = await uc.execute(FreezeClanAdminInput(actor_tg_id=42, query=-987654))
        assert out.outcome == "frozen"
        assert out.clan is not None
        assert out.clan.id == clan.id
        assert audit.entries[-1].target_id == str(clan.id)

    async def test_default_reason_when_none(self) -> None:
        uc, admins, clans, audit, _u = _build_freeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans)
        assert clan.id is not None

        await uc.execute(FreezeClanAdminInput(actor_tg_id=42, query=clan.id))

        # default reason format: freeze_clan:<id>
        assert audit.entries[-1].reason == f"freeze_clan:{clan.id}"


@pytest.mark.asyncio
class TestUnfreezeClanAdmin:
    async def test_unknown_admin_raises(self) -> None:
        uc, _admins, _c, audit, uow = _build_unfreeze()
        with pytest.raises(AuthorizationError):
            await uc.execute(UnfreezeClanAdminInput(actor_tg_id=999, query=1))
        assert audit.entries == []
        assert uow.commits == 0

    async def test_clan_not_found_outcome(self) -> None:
        uc, admins, _c, audit, _u = _build_unfreeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        out = await uc.execute(UnfreezeClanAdminInput(actor_tg_id=42, query=999))
        assert out.outcome == "not_found"
        assert audit.entries == []

    async def test_unfreeze_frozen_clan_writes_audit(self) -> None:
        uc, admins, clans, audit, uow = _build_unfreeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, status=ClanStatus.FROZEN)
        assert clan.id is not None

        out = await uc.execute(UnfreezeClanAdminInput(actor_tg_id=42, query=clan.id))

        assert out.outcome == "unfrozen"
        assert out.clan is not None
        assert out.clan.status is ClanStatus.ACTIVE
        saved = await clans.get_by_id(clan.id)
        assert saved is not None
        assert saved.status is ClanStatus.ACTIVE
        assert uow.commits == 1
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_CLAN_UNFROZEN
        assert a.before == {"status": "frozen"}
        assert a.after == {"status": "active"}
        assert a.reason == f"unfreeze_clan:{clan.id}"

    async def test_already_active_is_idempotent_no_audit(self) -> None:
        uc, admins, clans, audit, _u = _build_unfreeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, status=ClanStatus.ACTIVE)
        assert clan.id is not None

        out = await uc.execute(UnfreezeClanAdminInput(actor_tg_id=42, query=clan.id))

        assert out.outcome == "already_active"
        assert out.clan is not None
        assert audit.entries == []

    async def test_lookup_by_chat_id_falls_back(self) -> None:
        uc, admins, clans, _audit, _u = _build_unfreeze()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, chat_id=-987654, status=ClanStatus.FROZEN)

        out = await uc.execute(UnfreezeClanAdminInput(actor_tg_id=42, query=-987654))
        assert out.outcome == "unfrozen"
        assert out.clan is not None
        assert out.clan.id == clan.id
