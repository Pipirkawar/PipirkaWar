"""Unit-tests for ``ListClansAdmin`` use-case (Sprint 4.5-E)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin.list_clans import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ListClansAdmin,
    ListClansAdminInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import AdminRole
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanStatus,
)
from pipirik_wars.domain.clan.value_objects import ClanTitle
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clan_repo import FakeClanRepository
from tests.fakes.clock import FakeClock
from tests.fakes.uow import FakeUnitOfWork

_FIXED_NOW = datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC)


def _build() -> tuple[
    ListClansAdmin,
    FakeAdminRepository,
    FakeClanRepository,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    clans = FakeClanRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    use_case = ListClansAdmin(
        uow=uow,
        admins=admins,
        clans=clans,
        audit=audit,
        clock=FakeClock(_FIXED_NOW),
        authz=FakeAdminAuthzAllowAll(),
    )
    return use_case, admins, clans, uow


def _seed_clan(
    clans: FakeClanRepository,
    *,
    chat_id: int,
    title: str,
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
class TestListClansAdmin:
    async def test_unknown_admin_raises(self) -> None:
        use_case, _admins, _clans, _uow = _build()
        with pytest.raises(AuthorizationError):
            await use_case.execute(ListClansAdminInput(actor_tg_id=999))

    async def test_inactive_admin_raises(self) -> None:
        use_case, admins, _clans, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT, is_active=False)
        with pytest.raises(AuthorizationError):
            await use_case.execute(ListClansAdminInput(actor_tg_id=42))

    async def test_empty_list(self) -> None:
        use_case, admins, _clans, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        result = await use_case.execute(ListClansAdminInput(actor_tg_id=42))
        assert result.total == 0
        assert len(result.clans) == 0
        assert result.page == 1

    async def test_returns_all_clans(self) -> None:
        use_case, admins, clans, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_clan(clans, chat_id=-100, title="Alpha")
        _seed_clan(clans, chat_id=-200, title="Beta")
        _seed_clan(clans, chat_id=-300, title="Gamma", status=ClanStatus.FROZEN)

        result = await use_case.execute(ListClansAdminInput(actor_tg_id=42))
        assert result.total == 3
        assert len(result.clans) == 3

    async def test_filter_frozen(self) -> None:
        use_case, admins, clans, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_clan(clans, chat_id=-100, title="Alpha")
        _seed_clan(clans, chat_id=-200, title="Beta", status=ClanStatus.FROZEN)
        _seed_clan(clans, chat_id=-300, title="Gamma", status=ClanStatus.FROZEN)

        result = await use_case.execute(
            ListClansAdminInput(actor_tg_id=42, status_filter=ClanStatus.FROZEN),
        )
        assert result.total == 2
        assert all(c.status is ClanStatus.FROZEN for c in result.clans)

    async def test_filter_active(self) -> None:
        use_case, admins, clans, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_clan(clans, chat_id=-100, title="Alpha")
        _seed_clan(clans, chat_id=-200, title="Beta", status=ClanStatus.FROZEN)

        result = await use_case.execute(
            ListClansAdminInput(actor_tg_id=42, status_filter=ClanStatus.ACTIVE),
        )
        assert result.total == 1
        assert result.clans[0].title.value == "Alpha"

    async def test_pagination_page1(self) -> None:
        use_case, admins, clans, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        for i in range(5):
            _seed_clan(clans, chat_id=-(100 + i), title=f"Clan{i}")

        result = await use_case.execute(
            ListClansAdminInput(actor_tg_id=42, page=1, page_size=2),
        )
        assert result.total == 5
        assert len(result.clans) == 2
        assert result.page == 1

    async def test_pagination_page2(self) -> None:
        use_case, admins, clans, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        for i in range(5):
            _seed_clan(clans, chat_id=-(100 + i), title=f"Clan{i}")

        result = await use_case.execute(
            ListClansAdminInput(actor_tg_id=42, page=2, page_size=2),
        )
        assert result.total == 5
        assert len(result.clans) == 2
        assert result.page == 2

    async def test_pagination_last_page(self) -> None:
        use_case, admins, clans, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        for i in range(5):
            _seed_clan(clans, chat_id=-(100 + i), title=f"Clan{i}")

        result = await use_case.execute(
            ListClansAdminInput(actor_tg_id=42, page=3, page_size=2),
        )
        assert result.total == 5
        assert len(result.clans) == 1

    async def test_page_size_capped(self) -> None:
        use_case, admins, _clans, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        result = await use_case.execute(
            ListClansAdminInput(actor_tg_id=42, page_size=999),
        )
        assert result.page_size == MAX_PAGE_SIZE

    async def test_default_page_size(self) -> None:
        use_case, admins, _clans, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        result = await use_case.execute(ListClansAdminInput(actor_tg_id=42))
        assert result.page_size == DEFAULT_PAGE_SIZE

    async def test_ordered_by_id(self) -> None:
        use_case, admins, clans, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_clan(clans, chat_id=-300, title="Gamma")
        _seed_clan(clans, chat_id=-100, title="Alpha")
        _seed_clan(clans, chat_id=-200, title="Beta")

        result = await use_case.execute(ListClansAdminInput(actor_tg_id=42))
        ids = [c.id for c in result.clans if c.id is not None]
        assert ids == sorted(ids)
        assert len(ids) == len(result.clans)
