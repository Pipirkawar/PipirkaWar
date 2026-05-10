"""Integration-тесты `SqlAlchemyClanRepository` и `SqlAlchemyClanMembershipRepository`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanAlreadyRegisteredError,
    ClanMember,
    ClanMembershipExistsError,
    ClanStatus,
    ClanTitle,
)
from pipirik_wars.domain.player import Player
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError

NOW = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)


def _new_clan(*, chat_id: int = -100123, kind: ChatKind = ChatKind.SUPERGROUP) -> Clan:
    return Clan.new(
        chat_id=chat_id,
        chat_kind=kind,
        title=ClanTitle(value="Лесные братья"),
        now=NOW,
    )


class TestSqlAlchemyClanRepository:
    @pytest.mark.asyncio
    async def test_get_by_chat_id_when_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyClanRepository(uow=uow)
        async with uow:
            assert await repo.get_by_chat_id(-100404) is None

    @pytest.mark.asyncio
    async def test_add_and_get(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyClanRepository(uow=uow)
        async with uow:
            stored = await repo.add(_new_clan(chat_id=-100123))
            assert stored.id is not None
            assert stored.chat_id == -100123
            assert stored.chat_kind is ChatKind.SUPERGROUP
            assert stored.title.value == "Лесные братья"
            assert stored.status is ClanStatus.ACTIVE

        async with uow:
            found = await repo.get_by_chat_id(-100123)
            assert found is not None
            assert found.id == stored.id

            assert stored.id is not None
            by_id = await repo.get_by_id(stored.id)
            assert by_id is not None
            assert by_id.chat_id == -100123

    @pytest.mark.asyncio
    async def test_duplicate_chat_id_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyClanRepository(uow=uow)
        async with uow:
            await repo.add(_new_clan(chat_id=-100777))

        with pytest.raises(ClanAlreadyRegisteredError) as exc:
            async with uow:
                await repo.add(_new_clan(chat_id=-100777))
        assert exc.value.chat_id == -100777

    @pytest.mark.asyncio
    async def test_save_persists_title_and_status(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyClanRepository(uow=uow)
        async with uow:
            stored = await repo.add(_new_clan(chat_id=-100888))

        later = NOW + timedelta(seconds=1)
        async with uow:
            mutated = stored.with_title(
                ClanTitle(value="Banana Bros"),
                now=later,
            ).freeze(now=later)
            saved = await repo.save(mutated)
            assert saved.title.value == "Banana Bros"
            assert saved.status is ClanStatus.FROZEN
            assert saved.updated_at == later

        async with uow:
            reloaded = await repo.get_by_chat_id(-100888)
            assert reloaded is not None
            assert reloaded.title.value == "Banana Bros"
            assert reloaded.status is ClanStatus.FROZEN

    @pytest.mark.asyncio
    async def test_save_chat_id_migration(self, uow: SqlAlchemyUnitOfWork) -> None:
        """group → supergroup: меняется и chat_id, и chat_kind, но id сохраняется."""
        repo = SqlAlchemyClanRepository(uow=uow)
        async with uow:
            stored = await repo.add(_new_clan(chat_id=12345, kind=ChatKind.GROUP))

        later = NOW + timedelta(seconds=1)
        async with uow:
            migrated = stored.with_chat_id(
                new_chat_id=-100012345,
                new_chat_kind=ChatKind.SUPERGROUP,
                now=later,
            )
            saved = await repo.save(migrated)
            assert saved.id == stored.id
            assert saved.chat_id == -100012345
            assert saved.chat_kind is ChatKind.SUPERGROUP

        async with uow:
            assert await repo.get_by_chat_id(12345) is None
            new_found = await repo.get_by_chat_id(-100012345)
            assert new_found is not None
            assert new_found.id == stored.id

    @pytest.mark.asyncio
    async def test_save_unknown_id_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyClanRepository(uow=uow)
        ghost = Clan(
            id=99999,
            chat_id=-100000,
            chat_kind=ChatKind.GROUP,
            title=ClanTitle(value="Ghost"),
            status=ClanStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
        with pytest.raises(DomainIntegrityError, match="does not exist"):
            async with uow:
                await repo.save(ghost)

    @pytest.mark.asyncio
    async def test_add_with_preset_id_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyClanRepository(uow=uow)
        async with uow:
            stored = await repo.add(_new_clan(chat_id=-100999))

        with pytest.raises(DomainIntegrityError, match="pre-set id"):
            async with uow:
                await repo.add(stored)


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


async def _seed_clan(uow: SqlAlchemyUnitOfWork, *, chat_id: int) -> Clan:
    repo = SqlAlchemyClanRepository(uow=uow)
    async with uow:
        return await repo.add(_new_clan(chat_id=chat_id))


class TestSqlAlchemyClanMembershipRepository:
    @pytest.mark.asyncio
    async def test_get_by_player_when_empty(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = SqlAlchemyClanMembershipRepository(uow=uow)
        async with uow:
            assert await repo.get_by_player(404) is None

    @pytest.mark.asyncio
    async def test_add_and_lookup(self, uow: SqlAlchemyUnitOfWork) -> None:
        clan = await _seed_clan(uow, chat_id=-100123)
        player = await _seed_player(uow, tg_id=42)
        assert clan.id is not None
        assert player.id is not None

        repo = SqlAlchemyClanMembershipRepository(uow=uow)
        async with uow:
            stored = await repo.add(ClanMember.new(clan_id=clan.id, player_id=player.id, now=NOW))
            assert stored.clan_id == clan.id
            assert stored.player_id == player.id

        async with uow:
            found = await repo.get_by_player(player.id)
            assert found is not None
            assert found.clan_id == clan.id

            members = await repo.list_by_clan(clan.id)
            assert len(members) == 1
            assert members[0].player_id == player.id

    @pytest.mark.asyncio
    async def test_player_can_be_in_only_one_clan(self, uow: SqlAlchemyUnitOfWork) -> None:
        clan_a = await _seed_clan(uow, chat_id=-100111)
        clan_b = await _seed_clan(uow, chat_id=-100222)
        player = await _seed_player(uow, tg_id=42)
        assert clan_a.id is not None and clan_b.id is not None and player.id is not None

        repo = SqlAlchemyClanMembershipRepository(uow=uow)
        async with uow:
            await repo.add(
                ClanMember.new(
                    clan_id=clan_a.id,
                    player_id=player.id,
                    now=NOW,
                ),
            )

        # Уникальный индекс на player_id ловит попытку добавить
        # этого же игрока в другой клан.
        with pytest.raises(ClanMembershipExistsError) as exc:
            async with uow:
                await repo.add(
                    ClanMember.new(
                        clan_id=clan_b.id,
                        player_id=player.id,
                        now=NOW,
                    ),
                )
        assert exc.value.player_id == player.id

    @pytest.mark.asyncio
    async def test_remove_existing_returns_true(self, uow: SqlAlchemyUnitOfWork) -> None:
        clan = await _seed_clan(uow, chat_id=-100333)
        player = await _seed_player(uow, tg_id=99)
        assert clan.id is not None and player.id is not None

        repo = SqlAlchemyClanMembershipRepository(uow=uow)
        async with uow:
            await repo.add(ClanMember.new(clan_id=clan.id, player_id=player.id, now=NOW))

        async with uow:
            assert (await repo.remove(clan_id=clan.id, player_id=player.id)) is True

        async with uow:
            assert await repo.get_by_player(player.id) is None

    @pytest.mark.asyncio
    async def test_remove_missing_is_idempotent(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Повторный кик из чата не должен падать."""
        repo = SqlAlchemyClanMembershipRepository(uow=uow)
        async with uow:
            assert (await repo.remove(clan_id=12345, player_id=67890)) is False

    @pytest.mark.asyncio
    async def test_count_active_for_player(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Sprint 3.6-A: бонус-за-племена. Все gates на одном sql-репо.

        Проверяем за один тест полный набор:
        - frozen-клан → не считается;
        - размер `< min_tribe_size` → не считается;
        - размер `>= min_tribe_size` + игрок-член → +1;
        - игрок не в членах → не считается.
        """
        clan_repo = SqlAlchemyClanRepository(uow=uow)
        member_repo = SqlAlchemyClanMembershipRepository(uow=uow)

        # ── ACTIVE-клан с 4 членами, в т. ч. наш игрок (id=42) ──
        active_big = await _seed_clan(uow, chat_id=-100100)
        assert active_big.id is not None
        # ── ACTIVE-клан с 3 членами, в т. ч. наш игрок ──
        active_small = await _seed_clan(uow, chat_id=-100200)
        assert active_small.id is not None
        # ── FROZEN-клан с 5 членами, в т. ч. наш игрок ──
        frozen = await _seed_clan(uow, chat_id=-100300)
        assert frozen.id is not None
        async with uow:
            saved = await clan_repo.save(frozen.freeze(now=NOW + timedelta(seconds=1)))
            assert saved.status is ClanStatus.FROZEN
        # ── ACTIVE-клан с 4 членами, БЕЗ нашего игрока ──
        active_no_player = await _seed_clan(uow, chat_id=-100400)
        assert active_no_player.id is not None

        # Сидим игрока 42 (uniq player) и других игроков для добивки размеров
        # каждого клана. UNIQUE(player_id) запрещает 1 игрока в нескольких
        # кланах, поэтому используем разных игроков для добивки.
        target = await _seed_player(uow, tg_id=42)
        assert target.id is not None
        # Заполняем active_big: 3 «других» + наш игрок = 4 (>= 4).
        for tg in (101, 102, 103):
            other = await _seed_player(uow, tg_id=tg)
            assert other.id is not None
            async with uow:
                await member_repo.add(
                    ClanMember.new(clan_id=active_big.id, player_id=other.id, now=NOW),
                )
        async with uow:
            await member_repo.add(
                ClanMember.new(clan_id=active_big.id, player_id=target.id, now=NOW),
            )
        # Заполняем active_small: 3 других = 3 (< 4) — игрока сюда не положим
        # (один игрок = один клан).
        for tg in (201, 202, 203):
            other = await _seed_player(uow, tg_id=tg)
            assert other.id is not None
            async with uow:
                await member_repo.add(
                    ClanMember.new(clan_id=active_small.id, player_id=other.id, now=NOW),
                )
        # Заполняем frozen-клан 5 разными игроками.
        for tg in (301, 302, 303, 304, 305):
            other = await _seed_player(uow, tg_id=tg)
            assert other.id is not None
            async with uow:
                await member_repo.add(
                    ClanMember.new(clan_id=frozen.id, player_id=other.id, now=NOW),
                )
        # active_no_player: 4 чужих — игрока 42 нет.
        for tg in (401, 402, 403, 404):
            other = await _seed_player(uow, tg_id=tg)
            assert other.id is not None
            async with uow:
                await member_repo.add(
                    ClanMember.new(clan_id=active_no_player.id, player_id=other.id, now=NOW),
                )

        async with uow:
            n = await clan_repo.count_active_for_player(player_id=target.id, min_tribe_size=4)
            # Только `active_big` квалифицирован: ACTIVE + size>=4 + игрок-член.
            assert n == 1

            # Игрок без членств → 0 (используем заведомо несуществующий player_id).
            n_ghost = await clan_repo.count_active_for_player(player_id=999_999, min_tribe_size=4)
            assert n_ghost == 0

            # `min_tribe_size=1` не превратит frozen в активный.
            n_frozen = await clan_repo.count_active_for_player(
                player_id=target.id, min_tribe_size=1
            )
            # `target` сидит только в active_big (UNIQUE) → 1.
            assert n_frozen == 1

    @pytest.mark.asyncio
    async def test_list_by_clan_orders_by_joined_at(self, uow: SqlAlchemyUnitOfWork) -> None:
        clan = await _seed_clan(uow, chat_id=-100444)
        p1 = await _seed_player(uow, tg_id=1)
        p2 = await _seed_player(uow, tg_id=2)
        p3 = await _seed_player(uow, tg_id=3)
        assert clan.id is not None
        assert p1.id is not None and p2.id is not None and p3.id is not None

        repo = SqlAlchemyClanMembershipRepository(uow=uow)
        async with uow:
            # Добавляем «не по порядку» — третий, первый, второй.
            await repo.add(
                ClanMember.new(
                    clan_id=clan.id,
                    player_id=p3.id,
                    now=NOW + timedelta(seconds=30),
                )
            )
            await repo.add(
                ClanMember.new(
                    clan_id=clan.id,
                    player_id=p1.id,
                    now=NOW,
                )
            )
            await repo.add(
                ClanMember.new(
                    clan_id=clan.id,
                    player_id=p2.id,
                    now=NOW + timedelta(seconds=15),
                )
            )

        async with uow:
            members = await repo.list_by_clan(clan.id)
            assert [m.player_id for m in members] == [p1.id, p2.id, p3.id]
