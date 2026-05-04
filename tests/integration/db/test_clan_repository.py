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
