"""Unit-тесты `FindPlayers` (Спринт 2.5-B.1)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import (
    FindPlayers,
    FindPlayersInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditSource,
    AdminRole,
)
from pipirik_wars.domain.player import (
    Player,
    PlayerName,
    Username,
)
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clock import FakeClock
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.uow import FakeUnitOfWork

_FIXED_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _build() -> tuple[
    FindPlayers,
    FakeAdminRepository,
    FakePlayerRepository,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
    FakeClock,
]:
    admins = FakeAdminRepository()
    players = FakePlayerRepository()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    clock = FakeClock(_FIXED_NOW)
    use_case = FindPlayers(
        uow=uow,
        admins=admins,
        players=players,
        audit=audit,
        clock=clock,
        limit=10,
    )
    return use_case, admins, players, audit, uow, clock


def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str | None = None,
    name: str | None = None,
) -> Player:
    """Подложить игрока с авто-id (имитация `add()` без UoW)."""
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


@pytest.mark.asyncio
class TestFindPlayers:
    async def test_unknown_admin_raises(self) -> None:
        use_case, _admins, _players, audit, uow, _ = _build()

        with pytest.raises(AuthorizationError):
            await use_case.execute(
                FindPlayersInput(actor_tg_id=999, query="ivan"),
            )

        # Авторизация падает ДО UoW и audit.
        assert audit.entries == []
        assert uow.commits == 0

    async def test_inactive_admin_raises(self) -> None:
        use_case, admins, _players, audit, uow, _ = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT, is_active=False)

        with pytest.raises(AuthorizationError):
            await use_case.execute(
                FindPlayersInput(actor_tg_id=42, query="ivan"),
            )

        assert audit.entries == []
        assert uow.commits == 0

    async def test_query_by_tg_id_returns_single_match(self) -> None:
        use_case, admins, players, audit, uow, _ = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100, username="ivan")
        _seed_player(players, tg_id=200, username="petr")

        out = await use_case.execute(
            FindPlayersInput(actor_tg_id=42, query="100", tg_chat_id=-100),
        )

        assert out.query == "100"
        assert len(out.results) == 1
        assert out.results[0].tg_id == 100
        assert out.results[0].username == "ivan"

        # Audit написан после успешного поиска (1 транзакция).
        assert uow.commits == 1
        assert uow.rollbacks == 0
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.action == AdminAuditAction.ADMIN_PLAYER_LOOKUP
        assert a.target_kind == "player_query"
        assert a.target_id == "100"
        assert a.source == AdminAuditSource.BOT
        assert a.tg_chat_id == -100
        assert a.after == {"matches": 1}
        assert a.reason == "find_player:100"

    async def test_query_by_at_username_returns_exact_match(self) -> None:
        use_case, admins, players, audit, _uow, _ = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100, username="ivan")
        _seed_player(players, tg_id=101, username="ivanushka")

        out = await use_case.execute(
            FindPlayersInput(actor_tg_id=42, query="@ivan"),
        )

        # Точное совпадение, а не подстрока: только "ivan".
        assert len(out.results) == 1
        assert out.results[0].tg_id == 100
        assert audit.entries[-1].after == {"matches": 1}

    async def test_query_substring_matches_username_and_name(self) -> None:
        use_case, admins, players, audit, _uow, _ = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100, username="ivan42")
        _seed_player(players, tg_id=101, username="petrov", name="Ivanushka")
        _seed_player(players, tg_id=102, username="anna", name="Алёна")

        out = await use_case.execute(
            FindPlayersInput(actor_tg_id=42, query="IVAN"),
        )

        # `IVAN` (case-insensitive) совпадает с username `ivan42` и name
        # `Ivanushka` — 2 матча. Сортировка FakePlayerRepository: id ASC.
        assert [p.tg_id for p in out.results] == [100, 101]
        assert audit.entries[-1].after == {"matches": 2}

    async def test_query_substring_supports_cyrillic(self) -> None:
        use_case, admins, players, audit, _uow, _ = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=200, username="petr", name="Иванушка")
        _seed_player(players, tg_id=201, username="anna", name="Алёна")

        out = await use_case.execute(
            FindPlayersInput(actor_tg_id=42, query="иван"),
        )

        # Кириллица: `иван` ⊂ `Иванушка` (casefold-нечувствительный).
        assert [p.tg_id for p in out.results] == [200]
        assert audit.entries[-1].after == {"matches": 1}

    async def test_query_not_found_returns_empty_and_audits(self) -> None:
        use_case, admins, _players, audit, uow, _ = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)

        out = await use_case.execute(
            FindPlayersInput(actor_tg_id=42, query="ghost"),
        )

        assert out.results == ()
        # Even-on-empty: одна аудит-запись с matches=0.
        assert uow.commits == 1
        assert audit.entries[-1].after == {"matches": 0}
        assert audit.entries[-1].target_id == "ghost"

    async def test_empty_query_short_circuits_to_empty(self) -> None:
        use_case, admins, players, audit, _uow, _ = _build()
        admins.seed(tg_id=42, role=AdminRole.SUPPORT)
        _seed_player(players, tg_id=100, username="ivan")

        out = await use_case.execute(
            FindPlayersInput(actor_tg_id=42, query="   "),
        )

        assert out.query == ""
        assert out.results == ()
        # Аудит пишется и про пустой запрос — это всё равно «попытка
        # пробить кого-то», и она важна для журнала super-admin-а.
        assert audit.entries[-1].target_id == "<empty>"
        assert audit.entries[-1].after == {"matches": 0}

    async def test_constructor_rejects_non_positive_limit(self) -> None:
        with pytest.raises(ValueError, match="limit must be positive"):
            FindPlayers(
                uow=FakeUnitOfWork(),
                admins=FakeAdminRepository(),
                players=FakePlayerRepository(),
                audit=FakeAdminAuditLogger(),
                clock=FakeClock(_FIXED_NOW),
                limit=0,
            )
