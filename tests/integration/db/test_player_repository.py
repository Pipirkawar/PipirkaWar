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

    @pytest.mark.asyncio
    async def test_list_top_by_length_orders_by_length_desc(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Топ отсортирован по убыванию длины (ПД 1.4.6)."""
        repo = SqlAlchemyPlayerRepository(uow=uow)
        later = NOW + timedelta(seconds=1)
        async with uow:
            small = await repo.add(_make_new(tg_id=1, username=None))
            medium = await repo.add(_make_new(tg_id=2, username=None))
            big = await repo.add(_make_new(tg_id=3, username=None))
            assert small.id is not None and medium.id is not None and big.id is not None
            await repo.save(small.with_length(Length(cm=10), now=later))
            await repo.save(medium.with_length(Length(cm=50), now=later))
            await repo.save(big.with_length(Length(cm=200), now=later))

        async with uow:
            top = await repo.list_top_by_length(limit=10)
        # ожидаем порядок: 200 → 50 → 10
        assert [p.length.cm for p in top] == [200, 50, 10]
        assert [p.tg_id for p in top] == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_list_top_by_length_excludes_frozen(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Замороженные игроки не должны светиться в `/top`."""
        repo = SqlAlchemyPlayerRepository(uow=uow)
        later = NOW + timedelta(seconds=1)
        async with uow:
            active = await repo.add(_make_new(tg_id=1, username=None))
            frozen = await repo.add(_make_new(tg_id=2, username=None))
            await repo.save(active.with_length(Length(cm=10), now=later))
            saved_frozen = await repo.save(
                frozen.with_length(Length(cm=999), now=later).freeze(now=later)
            )
            assert saved_frozen.status is PlayerStatus.FROZEN

        async with uow:
            top = await repo.list_top_by_length(limit=10)
        assert [p.tg_id for p in top] == [1]  # frozen с длиной 999 исключён

    @pytest.mark.asyncio
    async def test_list_top_by_length_tie_break_by_id_asc(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """При равной длине — стабильный порядок по `id ASC`."""
        repo = SqlAlchemyPlayerRepository(uow=uow)
        later = NOW + timedelta(seconds=1)
        async with uow:
            first = await repo.add(_make_new(tg_id=10, username=None))
            second = await repo.add(_make_new(tg_id=11, username=None))
            third = await repo.add(_make_new(tg_id=12, username=None))
            await repo.save(first.with_length(Length(cm=42), now=later))
            await repo.save(second.with_length(Length(cm=42), now=later))
            await repo.save(third.with_length(Length(cm=42), now=later))

        async with uow:
            top = await repo.list_top_by_length(limit=10)
        # все по 42 см → стабильный порядок по id ASC (= порядок добавления)
        assert [p.tg_id for p in top] == [10, 11, 12]

    @pytest.mark.asyncio
    async def test_list_top_by_length_respects_limit(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        later = NOW + timedelta(seconds=1)
        async with uow:
            for tg in range(1, 6):
                p = await repo.add(_make_new(tg_id=tg, username=None))
                await repo.save(p.with_length(Length(cm=10 * tg), now=later))

        async with uow:
            top = await repo.list_top_by_length(limit=2)
        assert [p.length.cm for p in top] == [50, 40]

    @pytest.mark.asyncio
    async def test_list_top_by_length_empty_when_no_players(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            top = await repo.list_top_by_length(limit=100)
        assert top == ()

    @pytest.mark.asyncio
    async def test_list_top_by_length_rejects_non_positive_limit(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            with pytest.raises(ValueError, match="positive"):
                await repo.list_top_by_length(limit=0)
            with pytest.raises(ValueError, match="positive"):
                await repo.list_top_by_length(limit=-3)

    @pytest.mark.asyncio
    async def test_anticheat_ban_until_roundtrip(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Спринт 1.6.A: persist + reload `anticheat_ban_until`."""
        repo = SqlAlchemyPlayerRepository(uow=uow)
        ban_until = NOW + timedelta(days=14)
        async with uow:
            stored = await repo.add(_make_new(tg_id=42, username=None))
            assert stored.anticheat_ban_until is None  # default

            banned = stored.with_anticheat_ban(until=ban_until, now=NOW)
            saved = await repo.save(banned)
            assert saved.anticheat_ban_until == ban_until

        # Перечитываем — UTC tz должен сохраниться (см. ensure_utc).
        async with uow:
            reloaded = await repo.get_by_tg_id(42)
            assert reloaded is not None
            assert reloaded.anticheat_ban_until == ban_until
            assert reloaded.anticheat_ban_until is not None
            assert reloaded.anticheat_ban_until.tzinfo is not None

    @pytest.mark.asyncio
    async def test_anticheat_ban_lifted_persists_null(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        ban_until = NOW + timedelta(days=14)
        later = NOW + timedelta(days=15)
        async with uow:
            stored = await repo.add(_make_new(tg_id=42, username=None))
            banned = stored.with_anticheat_ban(until=ban_until, now=NOW)
            await repo.save(banned)

        async with uow:
            current = await repo.get_by_tg_id(42)
            assert current is not None
            lifted = current.with_anticheat_ban_lifted(now=later)
            await repo.save(lifted)

        async with uow:
            reloaded = await repo.get_by_tg_id(42)
            assert reloaded is not None
            assert reloaded.anticheat_ban_until is None

    # ── /find_player (Спринт 2.5-B.1) ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_find_by_query_exact_tg_id(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            await repo.add(_make_new(tg_id=100, username=Username(value="ivan")))
            await repo.add(_make_new(tg_id=200, username=Username(value="petr")))

        async with uow:
            rows = await repo.find_by_query(query="100", limit=10)
        assert [p.tg_id for p in rows] == [100]

    @pytest.mark.asyncio
    async def test_find_by_query_at_username_exact(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            await repo.add(_make_new(tg_id=100, username=Username(value="ivan")))
            await repo.add(_make_new(tg_id=101, username=Username(value="ivanushka")))

        async with uow:
            rows = await repo.find_by_query(query="@ivan", limit=10)
        # Точное совпадение: должны вернуть только "ivan", не "ivanushka".
        assert [p.tg_id for p in rows] == [100]

    @pytest.mark.asyncio
    async def test_find_by_query_substring_username_and_name_case_insensitive(
        self, uow: SqlAlchemyUnitOfWork
    ) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        later = NOW + timedelta(seconds=1)
        async with uow:
            p1 = await repo.add(_make_new(tg_id=100, username=Username(value="ivan42")))
            p2 = await repo.add(_make_new(tg_id=101, username=Username(value="petrov")))
            p3 = await repo.add(_make_new(tg_id=102, username=Username(value="anna")))
            assert p1.id is not None and p2.id is not None and p3.id is not None
            await repo.save(p2.with_name(PlayerName(value="Ivanushka"), now=later))
            await repo.save(p3.with_name(PlayerName(value="Алёна"), now=later))

        async with uow:
            rows = await repo.find_by_query(query="IVAN", limit=10)
        # Регистр не важен: совпадения по `username='ivan42'` и `name='Ivanushka'`.
        # Сортировка `id ASC`.
        assert [p.tg_id for p in rows] == [100, 101]

    @pytest.mark.asyncio
    async def test_find_by_query_empty_returns_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            await repo.add(_make_new(tg_id=100, username=Username(value="ivan")))

        async with uow:
            rows = await repo.find_by_query(query="   ", limit=10)
        assert rows == ()

    @pytest.mark.asyncio
    async def test_find_by_query_substring_escapes_like_wildcards(
        self, uow: SqlAlchemyUnitOfWork
    ) -> None:
        """Пользовательские `%` / `_` не должны превращаться в `LIKE`-метасимволы."""
        repo = SqlAlchemyPlayerRepository(uow=uow)
        later = NOW + timedelta(seconds=1)
        async with uow:
            p1 = await repo.add(_make_new(tg_id=100, username=Username(value="ivan_42")))
            p2 = await repo.add(_make_new(tg_id=101, username=Username(value="ivanovich")))
            assert p1.id is not None and p2.id is not None
            # имя нам не нужно — проверяем по username.
            _ = later

        async with uow:
            # `_` — это LIKE-метасимвол «один любой символ»; без эскейпа он бы
            # совпал с `ivanovich`. С эскейпом — только с `ivan_42`.
            rows = await repo.find_by_query(query="ivan_", limit=10)
        assert [p.tg_id for p in rows] == [100]

    @pytest.mark.asyncio
    async def test_find_by_query_includes_frozen_players(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Замороженных тоже находим — админ должен мочь их размораживать."""
        repo = SqlAlchemyPlayerRepository(uow=uow)
        later = NOW + timedelta(seconds=1)
        async with uow:
            p = await repo.add(_make_new(tg_id=100, username=Username(value="frozen_ivan")))
            await repo.save(p.freeze(now=later))

        async with uow:
            rows = await repo.find_by_query(query="frozen", limit=10)
        assert [p.tg_id for p in rows] == [100]
        assert rows[0].status is PlayerStatus.FROZEN

    @pytest.mark.asyncio
    async def test_find_by_query_respects_limit(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            for tg in range(100, 105):
                await repo.add(_make_new(tg_id=tg, username=Username(value=f"ivan{tg}")))

        async with uow:
            rows = await repo.find_by_query(query="ivan", limit=2)
        assert len(rows) == 2
        assert [p.tg_id for p in rows] == [100, 101]

    @pytest.mark.asyncio
    async def test_find_by_query_rejects_non_positive_limit(
        self, uow: SqlAlchemyUnitOfWork
    ) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            with pytest.raises(ValueError, match="positive"):
                await repo.find_by_query(query="ivan", limit=0)
            with pytest.raises(ValueError, match="positive"):
                await repo.find_by_query(query="ivan", limit=-1)
