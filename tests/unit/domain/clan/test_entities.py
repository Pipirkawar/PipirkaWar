"""Тесты на агрегаты `Clan` / `ClanMember` (Спринт 1.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.clan.entities import (
    Clan,
    ClanMember,
    ClanMemberRole,
)
from pipirik_wars.domain.clan.errors import ClanFrozenError
from pipirik_wars.domain.clan.value_objects import (
    ChatKind,
    ClanStatus,
    ClanTitle,
)

NOW = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(seconds=42)


def _new_clan(*, status: ClanStatus = ClanStatus.ACTIVE) -> Clan:
    clan = Clan.new(
        chat_id=-100123,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value="Лесные братья"),
        now=NOW,
    )
    if status is ClanStatus.FROZEN:
        return clan.freeze(now=NOW)
    return clan


class TestClanNew:
    def test_initial_state(self) -> None:
        clan = _new_clan()
        assert clan.id is None
        assert clan.chat_id == -100123
        assert clan.chat_kind is ChatKind.SUPERGROUP
        assert clan.title == ClanTitle(value="Лесные братья")
        assert clan.status is ClanStatus.ACTIVE
        assert clan.created_at == NOW
        assert clan.updated_at == NOW
        assert not clan.is_frozen


class TestClanImmutability:
    def test_frozen_dataclass(self) -> None:
        clan = _new_clan()
        with pytest.raises(AttributeError):
            clan.title = ClanTitle(value="New")

    def test_with_title_returns_new_instance(self) -> None:
        clan = _new_clan()
        clan2 = clan.with_title(ClanTitle(value="Banana Bros"), now=LATER)
        assert clan2 is not clan
        assert clan2.title == ClanTitle(value="Banana Bros")
        assert clan2.updated_at == LATER
        assert clan.title == ClanTitle(value="Лесные братья")  # original unchanged

    def test_with_title_idempotent(self) -> None:
        clan = _new_clan()
        clan2 = clan.with_title(ClanTitle(value="Лесные братья"), now=LATER)
        assert clan2 is clan  # no-op


class TestClanChatIdMigration:
    def test_group_to_supergroup_changes_chat_id_and_kind(self) -> None:
        # Имитируем создание клана как обычной группы (chat_id = positive int).
        clan = Clan.new(
            chat_id=12345,
            chat_kind=ChatKind.GROUP,
            title=ClanTitle(value="Old Group"),
            now=NOW,
        )
        # Telegram «промоутит» в супергруппу с новым chat_id (-100…).
        clan2 = clan.with_chat_id(
            new_chat_id=-100012345,
            new_chat_kind=ChatKind.SUPERGROUP,
            now=LATER,
        )
        assert clan2.chat_id == -100012345
        assert clan2.chat_kind is ChatKind.SUPERGROUP
        assert clan2.id == clan.id  # внутренний id не меняется
        assert clan2.title == clan.title
        assert clan2.updated_at == LATER

    def test_idempotent_when_no_change(self) -> None:
        clan = _new_clan()
        clan2 = clan.with_chat_id(
            new_chat_id=clan.chat_id,
            new_chat_kind=clan.chat_kind,
            now=LATER,
        )
        assert clan2 is clan


class TestClanFreeze:
    def test_freeze_sets_status(self) -> None:
        clan = _new_clan()
        frozen = clan.freeze(now=LATER)
        assert frozen.is_frozen
        assert frozen.status is ClanStatus.FROZEN
        assert frozen.updated_at == LATER

    def test_freeze_idempotent(self) -> None:
        clan = _new_clan().freeze(now=NOW)
        clan2 = clan.freeze(now=LATER)
        assert clan2 is clan

    def test_unfreeze_restores_active(self) -> None:
        clan = _new_clan().freeze(now=NOW)
        clan2 = clan.unfreeze(now=LATER)
        assert clan2.status is ClanStatus.ACTIVE
        assert clan2.updated_at == LATER

    def test_unfreeze_active_is_no_op(self) -> None:
        clan = _new_clan()
        assert clan.unfreeze(now=LATER) is clan


class TestFrozenClanCannotBeMutated:
    """`with_*` на frozen-клане должны бросать `ClanFrozenError`,
    кроме `freeze`/`unfreeze`."""

    def test_with_title_raises(self) -> None:
        clan = _new_clan(status=ClanStatus.FROZEN)
        with pytest.raises(ClanFrozenError) as exc:
            clan.with_title(ClanTitle(value="New"), now=LATER)
        assert exc.value.chat_id == -100123

    def test_with_chat_id_raises(self) -> None:
        clan = _new_clan(status=ClanStatus.FROZEN)
        with pytest.raises(ClanFrozenError):
            clan.with_chat_id(
                new_chat_id=-100456,
                new_chat_kind=ChatKind.SUPERGROUP,
                now=LATER,
            )

    def test_unfreeze_works(self) -> None:
        # Это путь «бот добавили обратно» — он должен работать.
        clan = _new_clan(status=ClanStatus.FROZEN)
        clan2 = clan.unfreeze(now=LATER)
        assert not clan2.is_frozen


class TestClanMember:
    def test_new(self) -> None:
        m = ClanMember.new(clan_id=10, player_id=20, now=NOW)
        assert m.clan_id == 10
        assert m.player_id == 20
        assert m.role is ClanMemberRole.MEMBER
        assert m.joined_at == NOW

    def test_new_with_role(self) -> None:
        m = ClanMember.new(
            clan_id=10,
            player_id=20,
            role=ClanMemberRole.LEADER,
            now=NOW,
        )
        assert m.role is ClanMemberRole.LEADER

    def test_with_role_changes(self) -> None:
        m = ClanMember.new(clan_id=10, player_id=20, now=NOW)
        m2 = m.with_role(ClanMemberRole.LEADER)
        assert m2.role is ClanMemberRole.LEADER
        assert m2 is not m
        assert m.role is ClanMemberRole.MEMBER  # original unchanged

    def test_with_role_idempotent(self) -> None:
        m = ClanMember.new(clan_id=10, player_id=20, now=NOW)
        assert m.with_role(ClanMemberRole.MEMBER) is m

    def test_is_frozen_dataclass(self) -> None:
        m = ClanMember.new(clan_id=10, player_id=20, now=NOW)
        with pytest.raises(AttributeError):
            m.role = ClanMemberRole.LEADER
