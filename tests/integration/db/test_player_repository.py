"""Integration-тесты `SqlAlchemyPlayerRepository`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerAlreadyRegisteredError,
    PlayerName,
    PlayerStatus,
    Thickness,
    Title,
    Username,
)
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyPlayerRepository
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError

NOW = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)


def _make_new(tg_id: int = 42, username: Username | None = None) -> Player:
    return Player.new(tg_id=tg_id, username=username, now=NOW)


class TestSqlAlchemyPlayerRepository:
    @pytest.mark.asyncio
    async def test_get_by_tg_id_when_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            assert await repo.get_by_tg_id(404) is None

    @pytest.mark.asyncio
    async def test_add_and_get_back(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            stored = await repo.add(_make_new(tg_id=42, username=Username(value="ivan42")))
            assert stored.id is not None
            assert stored.tg_id == 42
            assert stored.username == Username(value="ivan42")
            assert stored.length == Length(cm=2)
            assert stored.thickness == Thickness(level=1)
            assert stored.title is None
            assert stored.name is None
            assert stored.status is PlayerStatus.ACTIVE

        async with uow:
            found = await repo.get_by_tg_id(42)
            assert found is not None
            assert found.id == stored.id
            assert found.tg_id == 42
            assert found.username == Username(value="ivan42")

    @pytest.mark.asyncio
    async def test_initial_state_matches_gdd(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Стартовая длина 2, толщина 1, без титула, без имени, ACTIVE."""
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            stored = await repo.add(_make_new(tg_id=100, username=None))
            assert stored.length.cm == 2
            assert stored.thickness.level == 1
            assert stored.title is None
            assert stored.name is None
            assert stored.status is PlayerStatus.ACTIVE
            assert stored.username is None

    @pytest.mark.asyncio
    async def test_duplicate_tg_id_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            await repo.add(_make_new(tg_id=999, username=None))

        with pytest.raises(PlayerAlreadyRegisteredError) as exc:
            async with uow:
                await repo.add(_make_new(tg_id=999, username=None))
        assert exc.value.tg_id == 999

    @pytest.mark.asyncio
    async def test_add_player_with_preset_id_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        """`add` для уже-имеющего-id игрока должен падать (вызывающий перепутал API)."""
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            stored = await repo.add(_make_new(tg_id=42, username=None))

        with pytest.raises(DomainIntegrityError, match="pre-set id"):
            async with uow:
                await repo.add(stored)

    @pytest.mark.asyncio
    async def test_save_persists_mutations(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            stored = await repo.add(_make_new(tg_id=7, username=None))

        later = NOW + timedelta(seconds=1)
        async with uow:
            mutated = (
                stored.with_length(Length(cm=50), now=later)
                .with_thickness(Thickness(level=3), now=later)
                .with_title(Title.NEWBIE, now=later)
                .with_name(PlayerName(value="Иванушка"), now=later)
                .with_username(Username(value="ivan_v2"), now=later)
            )
            saved = await repo.save(mutated)
            assert saved.length == Length(cm=50)
            assert saved.thickness == Thickness(level=3)
            assert saved.title is Title.NEWBIE
            assert saved.name == PlayerName(value="Иванушка")
            assert saved.username == Username(value="ivan_v2")
            assert saved.updated_at == later
            # `created_at` immutable
            assert saved.created_at == stored.created_at

        async with uow:
            reloaded = await repo.get_by_tg_id(7)
            assert reloaded is not None
            assert reloaded.length == Length(cm=50)
            assert reloaded.title is Title.NEWBIE
            assert reloaded.name == PlayerName(value="Иванушка")

    @pytest.mark.asyncio
    async def test_save_can_clear_optional_fields(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            stored = await repo.add(_make_new(tg_id=8, username=Username(value="x")))
            stored = await repo.save(stored.with_name(PlayerName(value="Иванушка"), now=NOW))

        later = NOW + timedelta(seconds=1)
        async with uow:
            cleared = stored.without_name(now=later).with_username(None, now=later)
            saved = await repo.save(cleared)
            assert saved.name is None
            assert saved.username is None

        async with uow:
            reloaded = await repo.get_by_tg_id(8)
            assert reloaded is not None
            assert reloaded.name is None
            assert reloaded.username is None

    @pytest.mark.asyncio
    async def test_save_unknown_id_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        ghost = Player(
            id=99999,
            tg_id=12345,
            username=None,
            length=Length(cm=2),
            thickness=Thickness(level=1),
            title=None,
            name=None,
            status=PlayerStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
        with pytest.raises(DomainIntegrityError, match="does not exist"):
            async with uow:
                await repo.save(ghost)

    @pytest.mark.asyncio
    async def test_save_player_without_id_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        """`save` для игрока без id (ещё не вставленного) — это баг вызывающего."""
        repo = SqlAlchemyPlayerRepository(uow=uow)
        with pytest.raises(DomainIntegrityError, match="without id"):
            async with uow:
                await repo.save(_make_new(tg_id=42, username=None))

    @pytest.mark.asyncio
    async def test_freeze_unfreeze_round_trip(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            stored = await repo.add(_make_new(tg_id=42, username=None))

        later = NOW + timedelta(seconds=1)
        async with uow:
            saved = await repo.save(stored.freeze(now=later))
            assert saved.status is PlayerStatus.FROZEN

        async with uow:
            reloaded = await repo.get_by_tg_id(42)
            assert reloaded is not None
            assert reloaded.status is PlayerStatus.FROZEN
            even_later = later + timedelta(seconds=1)
            saved = await repo.save(reloaded.unfreeze(now=even_later))
            assert saved.status is PlayerStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_get_by_id_returns_player(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            stored = await repo.add(_make_new(tg_id=42, username=Username(value="ivan42")))
        assert stored.id is not None

        async with uow:
            found = await repo.get_by_id(player_id=stored.id)
            assert found is not None
            assert found.id == stored.id
            assert found.tg_id == 42

    @pytest.mark.asyncio
    async def test_get_by_id_missing_returns_none(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            assert await repo.get_by_id(player_id=99999) is None
