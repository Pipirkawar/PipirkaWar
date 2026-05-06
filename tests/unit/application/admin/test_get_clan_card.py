"""Unit-тесты `GetClanCard` (Спринт 2.5-D.1)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import (
    GetClanCard,
    GetClanCardInput,
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
    ClanMember,
    ClanMemberRole,
    ClanStatus,
)
from pipirik_wars.domain.clan.value_objects import ClanTitle
from pipirik_wars.domain.player import (
    Player,
    PlayerName,
    Username,
)
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clan_repo import (
    FakeClanMembershipRepository,
    FakeClanRepository,
)
from tests.fakes.clock import FakeClock
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.uow import FakeUnitOfWork

_FIXED_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _build() -> tuple[
    GetClanCard,
    FakeAdminRepository,
    FakePlayerRepository,
    FakeClanRepository,
    FakeClanMembershipRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    players = FakePlayerRepository()
    clans = FakeClanRepository()
    members = FakeClanMembershipRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    use_case = GetClanCard(
        uow=uow,
        admins=admins,
        players=players,
        clans=clans,
        clan_members=members,
        audit=audit,
        clock=FakeClock(_FIXED_NOW),
    )
    return use_case, admins, players, clans, members, audit, uow


def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str | None = None,
    name: str | None = None,
) -> Player:
    new_id = (max((p.id or 0 for p in players.rows), default=0)) + 1
    base = Player.new(
        tg_id=tg_id,
        username=Username(value=username) if username is not None else None,
        now=_FIXED_NOW,
    )
    seeded = replace(
        base,
        id=new_id,
        name=PlayerName(value=name) if name is not None else None,
    )
    players.rows.append(seeded)
    return seeded


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


def _seed_membership(
    members: FakeClanMembershipRepository,
    *,
    clan_id: int,
    player_id: int,
    role: ClanMemberRole = ClanMemberRole.MEMBER,
) -> ClanMember:
    m = ClanMember(
        clan_id=clan_id,
        player_id=player_id,
        role=role,
        joined_at=_FIXED_NOW,
    )
    members.rows.append(m)
    return m


@pytest.mark.asyncio
class TestGetClanCard:
    async def test_unknown_admin_raises(self) -> None:
        use_case, _admins, _p, _c, _cm, audit, uow = _build()
        with pytest.raises(AuthorizationError):
            await use_case.execute(GetClanCardInput(actor_tg_id=999, query=1))
        assert audit.entries == []
        assert uow.commits == 0

    async def test_inactive_admin_raises(self) -> None:
        use_case, admins, _p, _c, _cm, audit, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT, is_active=False)
        with pytest.raises(AuthorizationError):
            await use_case.execute(GetClanCardInput(actor_tg_id=42, query=1))
        assert audit.entries == []
        assert uow.commits == 0

    async def test_clan_not_found_returns_none_and_audits(self) -> None:
        use_case, admins, _p, _c, _cm, audit, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        out = await use_case.execute(
            GetClanCardInput(actor_tg_id=42, query=999, tg_chat_id=-100),
        )

        assert out.query == 999
        assert out.card is None
        assert uow.commits == 1
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_CLAN_LOOKUP
        assert a.target_kind == "clan"
        assert a.target_id == "999"
        assert a.after == {"found": False}
        assert a.tg_chat_id == -100
        assert a.source == AdminAuditSource.BOT
        assert a.reason == "clan_card:999"

    async def test_clan_lookup_by_internal_id(self) -> None:
        use_case, admins, _p, clans, _cm, audit, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, chat_id=-100500, title="The Pipiriks")
        assert clan.id is not None

        out = await use_case.execute(
            GetClanCardInput(actor_tg_id=42, query=clan.id),
        )

        assert out.card is not None
        assert out.card.clan_id == clan.id
        assert out.card.title == "The Pipiriks"
        assert out.card.chat_id == -100500
        assert out.card.chat_kind == "group"
        assert out.card.status is ClanStatus.ACTIVE
        assert audit.entries[-1].after == {"found": True}

    async def test_clan_lookup_by_chat_id_falls_back(self) -> None:
        use_case, admins, _p, clans, _cm, _a, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, chat_id=-987654, title="Каравашки")

        out = await use_case.execute(
            GetClanCardInput(actor_tg_id=42, query=-987654),
        )

        assert out.card is not None
        assert out.card.clan_id == clan.id
        assert out.card.chat_id == -987654

    async def test_clan_with_members_aggregates_lengths(self) -> None:
        use_case, admins, players, clans, members, _a, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, chat_id=-100500, title="The Pipiriks")
        assert clan.id is not None
        leader = _seed_player(players, tg_id=100, username="leader", name="Leader")
        peon = _seed_player(players, tg_id=101, username="peon", name="Peon")
        assert leader.id is not None and peon.id is not None
        _seed_membership(
            members,
            clan_id=clan.id,
            player_id=leader.id,
            role=ClanMemberRole.LEADER,
        )
        _seed_membership(members, clan_id=clan.id, player_id=peon.id)

        out = await use_case.execute(
            GetClanCardInput(actor_tg_id=42, query=clan.id),
        )

        assert out.card is not None
        assert out.card.member_count == 2
        assert out.card.active_member_count == 2
        # Каждый Player.new имеет стартовую длину >0; сумма >0.
        assert out.card.total_length_cm == leader.length.cm + peon.length.cm
        assert out.card.leader is not None
        assert out.card.leader.summary.tg_id == 100
        assert out.card.leader.role is ClanMemberRole.LEADER
        # Список членов содержит обоих, в порядке вставки.
        assert tuple(m.summary.tg_id for m in out.card.members) == (100, 101)

    async def test_frozen_player_excluded_from_total_length(self) -> None:
        use_case, admins, players, clans, members, _a, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, chat_id=-100500, title="The Pipiriks")
        assert clan.id is not None
        active = _seed_player(players, tg_id=100, username="active")
        frozen_seed = _seed_player(players, tg_id=101, username="frozen")
        assert active.id is not None and frozen_seed.id is not None
        # Заморозить игрока 101.
        frozen = frozen_seed.freeze(now=_FIXED_NOW)
        idx = players.rows.index(frozen_seed)
        players.rows[idx] = frozen
        _seed_membership(members, clan_id=clan.id, player_id=active.id)
        _seed_membership(members, clan_id=clan.id, player_id=frozen_seed.id)

        out = await use_case.execute(
            GetClanCardInput(actor_tg_id=42, query=clan.id),
        )

        assert out.card is not None
        assert out.card.member_count == 2
        assert out.card.active_member_count == 1
        assert out.card.total_length_cm == active.length.cm

    async def test_no_leader_renders_none(self) -> None:
        use_case, admins, players, clans, members, _a, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, chat_id=-100500, title="No-leader clan")
        assert clan.id is not None
        peon = _seed_player(players, tg_id=100, username="peon")
        assert peon.id is not None
        _seed_membership(members, clan_id=clan.id, player_id=peon.id)

        out = await use_case.execute(
            GetClanCardInput(actor_tg_id=42, query=clan.id),
        )

        assert out.card is not None
        assert out.card.leader is None

    async def test_orphan_membership_skipped(self) -> None:
        use_case, admins, _p, clans, members, _a, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(clans, chat_id=-100500, title="Orphans")
        assert clan.id is not None
        # players-таблица пуста: membership ссылается на несуществующего игрока.
        members.rows.append(
            ClanMember(
                clan_id=clan.id,
                player_id=999,
                role=ClanMemberRole.MEMBER,
                joined_at=_FIXED_NOW,
            ),
        )

        out = await use_case.execute(
            GetClanCardInput(actor_tg_id=42, query=clan.id),
        )

        assert out.card is not None
        assert out.card.member_count == 0
        assert out.card.members == ()

    async def test_frozen_clan_status_passes_through(self) -> None:
        use_case, admins, _p, clans, _cm, _a, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        clan = _seed_clan(
            clans,
            chat_id=-100500,
            title="Frozen clan",
            status=ClanStatus.FROZEN,
        )
        assert clan.id is not None

        out = await use_case.execute(
            GetClanCardInput(actor_tg_id=42, query=clan.id),
        )

        assert out.card is not None
        assert out.card.status is ClanStatus.FROZEN
