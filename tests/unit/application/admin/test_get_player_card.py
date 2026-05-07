"""Unit-тесты `GetPlayerCard` (Спринт 2.5-B.2)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.admin import (
    GetPlayerCard,
    GetPlayerCardInput,
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
from pipirik_wars.domain.forest import ForestRunStatus
from pipirik_wars.domain.forest.entities import Drop, NoDrop
from pipirik_wars.domain.forest.run import ForestRun
from pipirik_wars.domain.player import (
    Player,
    PlayerName,
    Username,
)
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clan_repo import (
    FakeClanMembershipRepository,
    FakeClanRepository,
)
from tests.fakes.clock import FakeClock
from tests.fakes.forest_run_repo import FakeForestRunRepository
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.uow import FakeUnitOfWork

_FIXED_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _build() -> tuple[
    GetPlayerCard,
    FakeAdminRepository,
    FakePlayerRepository,
    FakeClanRepository,
    FakeClanMembershipRepository,
    FakeForestRunRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    players = FakePlayerRepository()
    clans = FakeClanRepository()
    clan_members = FakeClanMembershipRepository()
    forest = FakeForestRunRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    use_case = GetPlayerCard(
        uow=uow,
        admins=admins,
        players=players,
        clans=clans,
        clan_members=clan_members,
        forest_runs=forest,
        audit=audit,
        clock=FakeClock(_FIXED_NOW),
        authz=FakeAdminAuthzAllowAll(),
    )
    return use_case, admins, players, clans, clan_members, forest, audit, uow


def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str | None = None,
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


def _seed_clan(clans: FakeClanRepository, *, chat_id: int, title: str) -> Clan:
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


def _seed_active_forest(
    forest: FakeForestRunRepository,
    *,
    player_id: int,
    duration: timedelta = timedelta(minutes=30),
) -> ForestRun:
    new_id = (max((r.id or 0 for r in forest.rows), default=0)) + 1
    drop: Drop = NoDrop()
    run = ForestRun(
        id=new_id,
        player_id=player_id,
        status=ForestRunStatus.IN_PROGRESS,
        started_at=_FIXED_NOW,
        ends_at=_FIXED_NOW + duration,
        branch_name="normal",
        length_delta_cm=2,
        drop=drop,
        finished_at=None,
    )
    forest.rows.append(run)
    return run


@pytest.mark.asyncio
class TestGetPlayerCard:
    async def test_inactive_admin_raises(self) -> None:
        use_case, admins, _p, _c, _cm, _f, audit, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT, is_active=False)

        with pytest.raises(AuthorizationError):
            await use_case.execute(
                GetPlayerCardInput(actor_tg_id=42, target_tg_id=100),
            )

        assert audit.entries == []
        assert uow.commits == 0

    async def test_unknown_admin_raises(self) -> None:
        use_case, _admins, _p, _c, _cm, _f, audit, uow = _build()
        with pytest.raises(AuthorizationError):
            await use_case.execute(
                GetPlayerCardInput(actor_tg_id=999, target_tg_id=100),
            )
        assert audit.entries == []
        assert uow.commits == 0

    async def test_player_not_found_returns_none_and_audits(self) -> None:
        use_case, admins, _p, _c, _cm, _f, audit, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        out = await use_case.execute(
            GetPlayerCardInput(actor_tg_id=42, target_tg_id=999, tg_chat_id=-100),
        )

        assert out.target_tg_id == 999
        assert out.card is None
        assert uow.commits == 1
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_PLAYER_LOOKUP
        assert a.target_kind == "player"
        assert a.target_id == "999"
        assert a.after == {"found": False}
        assert a.tg_chat_id == -100
        assert a.source == AdminAuditSource.BOT
        assert a.reason == "player_card:999"

    async def test_player_no_clan_no_forest_returns_minimal_card(self) -> None:
        use_case, admins, players, _c, _cm, _f, audit, uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100, username="ivan")

        out = await use_case.execute(
            GetPlayerCardInput(actor_tg_id=42, target_tg_id=100),
        )

        assert out.card is not None
        assert out.card.summary.tg_id == 100
        assert out.card.summary.username == "ivan"
        assert out.card.clan is None
        assert out.card.forest_active_run is None

        assert uow.commits == 1
        assert audit.entries[-1].after == {"found": True}

    async def test_player_with_clan_renders_clan_info(self) -> None:
        use_case, admins, players, clans, members, _f, _audit, _uow = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        player = _seed_player(players, tg_id=100, username="ivan")
        assert player.id is not None
        clan = _seed_clan(clans, chat_id=-100500, title="The Pipiriks")
        assert clan.id is not None
        _seed_membership(
            members,
            clan_id=clan.id,
            player_id=player.id,
            role=ClanMemberRole.LEADER,
        )

        out = await use_case.execute(
            GetPlayerCardInput(actor_tg_id=42, target_tg_id=100),
        )

        assert out.card is not None
        assert out.card.clan is not None
        assert out.card.clan.clan_id == clan.id
        assert out.card.clan.chat_id == -100500
        assert out.card.clan.title == "The Pipiriks"
        assert out.card.clan.status == ClanStatus.ACTIVE
        assert out.card.clan.role == ClanMemberRole.LEADER

    async def test_player_with_active_forest_run_renders_forest_info(
        self,
    ) -> None:
        use_case, admins, players, _c, _cm, forest, _a, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        player = _seed_player(players, tg_id=100, username="ivan")
        assert player.id is not None
        run = _seed_active_forest(forest, player_id=player.id)

        out = await use_case.execute(
            GetPlayerCardInput(actor_tg_id=42, target_tg_id=100),
        )

        assert out.card is not None
        assert out.card.forest_active_run is not None
        assert out.card.forest_active_run.run_id == run.id
        assert out.card.forest_active_run.status is ForestRunStatus.IN_PROGRESS
        assert out.card.forest_active_run.started_at == _FIXED_NOW
        assert out.card.forest_active_run.ends_at == _FIXED_NOW + timedelta(
            minutes=30,
        )

    async def test_player_summary_includes_name_and_status(self) -> None:
        use_case, admins, players, _c, _cm, _f, _a, _u = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        seeded = _seed_player(players, tg_id=100, username="ivan")
        # Сразу заморозим — карточка должна корректно отрендерить и frozen.
        frozen = replace(
            seeded,
            name=PlayerName(value="Иванушка"),
        ).freeze(now=_FIXED_NOW)
        # обновим row in-place (FakePlayerRepository хранит rows: list)
        idx = players.rows.index(seeded)
        players.rows[idx] = frozen

        out = await use_case.execute(
            GetPlayerCardInput(actor_tg_id=42, target_tg_id=100),
        )

        assert out.card is not None
        assert out.card.summary.name == "Иванушка"
        assert out.card.summary.status.value == "frozen"
