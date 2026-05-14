"""Тесты на агрегат `Player` (Спринт 1.1, ГДД §1.1, §2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.player.entities import Player, PlayerStatus
from pipirik_wars.domain.player.errors import PlayerFrozenError
from pipirik_wars.domain.player.value_objects import (
    Length,
    PlayerName,
    Thickness,
    Title,
    Username,
)

NOW = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(seconds=42)


class TestPlayerNew:
    def test_initial_state_matches_gdd(self) -> None:
        """Стартовая длина 2, толщина 1, без титула, без имени, ACTIVE."""
        p = Player.new(tg_id=42, username=None, now=NOW)

        assert p.id is None
        assert p.tg_id == 42
        assert p.username is None
        assert p.length == Length(cm=2)
        assert p.thickness == Thickness(level=1)
        assert p.title is None
        assert p.name is None
        assert p.status is PlayerStatus.ACTIVE
        assert p.created_at == NOW
        assert p.updated_at == NOW

    def test_with_username(self) -> None:
        p = Player.new(tg_id=42, username=Username(value="ivan"), now=NOW)
        assert p.username == Username(value="ivan")

    def test_is_not_frozen_initially(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        assert not p.is_frozen


class TestPlayerImmutability:
    def test_player_is_frozen_dataclass(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        with pytest.raises(AttributeError):
            p.length = Length(cm=99)

    def test_with_length_returns_new_instance(self) -> None:
        old = Player.new(tg_id=42, username=None, now=NOW)
        new = old.with_length(Length(cm=50), now=LATER)

        assert new is not old
        assert new.length == Length(cm=50)
        assert new.updated_at == LATER
        # original is unchanged
        assert old.length == Length(cm=2)
        assert old.updated_at == NOW


class TestPlayerWithUsername:
    def test_set_initial(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        p2 = p.with_username(Username(value="ivan42"), now=LATER)
        assert p2.username == Username(value="ivan42")
        assert p2.updated_at == LATER

    def test_clear(self) -> None:
        p = Player.new(tg_id=42, username=Username(value="ivan42"), now=NOW)
        p2 = p.with_username(None, now=LATER)
        assert p2.username is None
        assert p2.updated_at == LATER

    def test_idempotent_no_change(self) -> None:
        """Если username не изменился — возвращаем тот же инстанс (no-op)."""
        u = Username(value="ivan42")
        p = Player.new(tg_id=42, username=u, now=NOW)
        p2 = p.with_username(u, now=LATER)
        assert p2 is p


class TestPlayerWithLength:
    def test_increase(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        p2 = p.with_length(Length(cm=99), now=LATER)
        assert p2.length == Length(cm=99)
        assert p2.updated_at == LATER

    def test_decrease_to_zero_allowed(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        p2 = p.with_length(Length(cm=0), now=LATER)
        assert p2.length == Length(cm=0)


class TestPlayerWithThickness:
    def test_upgrade(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        p2 = p.with_thickness(Thickness(level=5), now=LATER)
        assert p2.thickness == Thickness(level=5)
        assert p2.updated_at == LATER


class TestPlayerWithTitle:
    def test_grant_first_title(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        p2 = p.with_title(Title.NEWBIE, now=LATER)
        assert p2.title is Title.NEWBIE
        assert p2.updated_at == LATER


class TestPlayerName:
    def test_set_first_name(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        new_name = PlayerName(value="Коляндр")
        p2 = p.with_name(new_name, now=LATER)
        assert p2.name == new_name
        assert p2.updated_at == LATER

    def test_replace_existing_name(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW).with_name(
            PlayerName(value="Иванушка"), now=NOW
        )
        p2 = p.with_name(PlayerName(value="Коляндр"), now=LATER)
        assert p2.name == PlayerName(value="Коляндр")

    def test_drop_name(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW).with_name(
            PlayerName(value="Иванушка"), now=NOW
        )
        p2 = p.without_name(now=LATER)
        assert p2.name is None
        assert p2.updated_at == LATER

    def test_drop_name_when_no_name_is_no_op(self) -> None:
        """Сброс имени у игрока без имени — возвращает тот же инстанс."""
        p = Player.new(tg_id=42, username=None, now=NOW)
        assert p.without_name(now=LATER) is p


class TestPlayerFreeze:
    def test_freeze_sets_status(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        p2 = p.freeze(now=LATER)
        assert p2.is_frozen
        assert p2.status is PlayerStatus.FROZEN
        assert p2.updated_at == LATER

    def test_freeze_is_idempotent(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW).freeze(now=NOW)
        p2 = p.freeze(now=LATER)
        assert p2 is p  # no-op, тот же инстанс

    def test_unfreeze_restores_active(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW).freeze(now=NOW)
        p2 = p.unfreeze(now=LATER)
        assert not p2.is_frozen
        assert p2.status is PlayerStatus.ACTIVE
        assert p2.updated_at == LATER

    def test_unfreeze_active_is_no_op(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        assert p.unfreeze(now=LATER) is p


class TestFrozenPlayerCannotBeMutated:
    """Любой `with_*` на замороженном игроке должен бросать `PlayerFrozenError`,
    кроме `freeze`/`unfreeze`."""

    def _frozen(self) -> Player:
        return Player.new(tg_id=42, username=None, now=NOW).freeze(now=NOW)

    def test_with_length_raises(self) -> None:
        with pytest.raises(PlayerFrozenError) as exc:
            self._frozen().with_length(Length(cm=99), now=LATER)
        assert exc.value.tg_id == 42

    def test_with_thickness_raises(self) -> None:
        with pytest.raises(PlayerFrozenError):
            self._frozen().with_thickness(Thickness(level=5), now=LATER)

    def test_with_title_raises(self) -> None:
        with pytest.raises(PlayerFrozenError):
            self._frozen().with_title(Title.NEWBIE, now=LATER)

    def test_with_name_raises(self) -> None:
        with pytest.raises(PlayerFrozenError):
            self._frozen().with_name(PlayerName(value="X"), now=LATER)

    def test_without_name_raises(self) -> None:
        # У замороженного игрока с именем сброс имени должен упасть, а не no-op.
        p = Player.new(tg_id=42, username=None, now=NOW).with_name(
            PlayerName(value="Иванушка"), now=NOW
        )
        frozen = p.freeze(now=NOW)
        with pytest.raises(PlayerFrozenError):
            frozen.without_name(now=LATER)

    def test_with_username_raises(self) -> None:
        with pytest.raises(PlayerFrozenError):
            self._frozen().with_username(Username(value="ivan"), now=LATER)

    def test_freeze_unfreeze_still_work_on_frozen(self) -> None:
        # Это «администраторский» путь, freezing не блокирует сам себя.
        f = self._frozen()
        f2 = f.freeze(now=LATER)  # idempotent no-op
        assert f2 is f
        f3 = f.unfreeze(now=LATER)
        assert not f3.is_frozen


class TestAnticheatBan:
    """Anti-cheat soft-ban (Спринт 1.6.A)."""

    def test_new_player_is_not_banned(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        assert p.anticheat_ban_until is None
        assert not p.is_anticheat_banned(now=NOW)

    def test_with_anticheat_ban_sets_until(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        until = NOW + timedelta(days=14)
        banned = p.with_anticheat_ban(until=until, now=NOW)

        assert banned is not p
        assert banned.anticheat_ban_until == until
        assert banned.is_anticheat_banned(now=NOW)
        assert banned.updated_at == NOW

    def test_is_anticheat_banned_false_after_until(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        until = NOW + timedelta(days=14)
        banned = p.with_anticheat_ban(until=until, now=NOW)
        future = until + timedelta(seconds=1)
        assert not banned.is_anticheat_banned(now=future)

    def test_is_anticheat_banned_at_until_is_false(self) -> None:
        # Граничный кейс: в момент `until` бан уже снят (строгое <).
        p = Player.new(tg_id=42, username=None, now=NOW)
        until = NOW + timedelta(days=14)
        banned = p.with_anticheat_ban(until=until, now=NOW)
        assert not banned.is_anticheat_banned(now=until)

    def test_ban_extends_monotonically(self) -> None:
        """Trip-wire может стрельнуть несколько раз; продлеваем только вверх."""
        p = Player.new(tg_id=42, username=None, now=NOW)
        first = p.with_anticheat_ban(until=NOW + timedelta(days=14), now=NOW)
        second = first.with_anticheat_ban(until=NOW + timedelta(days=7), now=LATER)
        # Меньшее `until` → не сокращаем (защита от случайного укорочения).
        assert second is first
        third = first.with_anticheat_ban(until=NOW + timedelta(days=21), now=LATER)
        assert third.anticheat_ban_until == NOW + timedelta(days=21)
        assert third.updated_at == LATER

    def test_ban_until_must_be_timezone_aware(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        naive = datetime(2026, 5, 5, 10, 0, 0)
        with pytest.raises(ValueError, match="timezone-aware"):
            p.with_anticheat_ban(until=naive, now=NOW)

    def test_ban_until_must_be_in_future(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        with pytest.raises(ValueError, match="in the future"):
            p.with_anticheat_ban(until=NOW, now=NOW)
        with pytest.raises(ValueError, match="in the future"):
            p.with_anticheat_ban(until=NOW - timedelta(days=1), now=NOW)

    def test_with_anticheat_ban_lifted(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        banned = p.with_anticheat_ban(until=NOW + timedelta(days=14), now=NOW)
        lifted = banned.with_anticheat_ban_lifted(now=LATER)

        assert lifted is not banned
        assert lifted.anticheat_ban_until is None
        assert not lifted.is_anticheat_banned(now=LATER)
        assert lifted.updated_at == LATER

    def test_lifting_already_clear_is_noop(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        same = p.with_anticheat_ban_lifted(now=LATER)
        assert same is p

    def test_ban_works_on_frozen_player(self) -> None:
        # Сервисное состояние не зависит от ACTIVE/FROZEN.
        p = Player.new(tg_id=42, username=None, now=NOW).freeze(now=NOW)
        banned = p.with_anticheat_ban(until=NOW + timedelta(days=14), now=NOW)
        assert banned.is_anticheat_banned(now=NOW)
        assert banned.is_frozen

    def test_ban_does_not_modify_other_fields(self) -> None:
        p = Player.new(tg_id=42, username=Username(value="ivan"), now=NOW).with_length(
            Length(cm=50), now=NOW
        )
        banned = p.with_anticheat_ban(until=NOW + timedelta(days=14), now=NOW)
        assert banned.length == Length(cm=50)
        assert banned.username == Username(value="ivan")
        assert banned.tg_id == 42


class TestAdminBan:
    """Необратимый бан (Спринт 2.5-B.4, ГДД §18.6)."""

    def test_ban_sets_status(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW)
        b = p.ban(now=LATER)
        assert b.status is PlayerStatus.BANNED
        assert b.updated_at == LATER

    def test_ban_is_idempotent(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW).ban(now=NOW)
        b = p.ban(now=LATER)
        assert b is p

    def test_freeze_on_banned_is_noop(self) -> None:
        """freeze() не должна понижать BANNED до FROZEN (иначе BANNED→FROZEN→ACTIVE)."""
        p = Player.new(tg_id=42, username=None, now=NOW).ban(now=NOW)
        f = p.freeze(now=LATER)
        assert f is p
        assert f.status is PlayerStatus.BANNED

    def test_unfreeze_on_banned_raises(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW).ban(now=NOW)
        with pytest.raises(PlayerFrozenError):
            p.unfreeze(now=LATER)


class TestBannedPlayerCannotBeMutated:
    """Любой with_* на забаненном игроке должен бросать PlayerFrozenError."""

    def _banned(self) -> Player:
        return Player.new(tg_id=42, username=None, now=NOW).ban(now=NOW)

    def test_with_length_raises(self) -> None:
        with pytest.raises(PlayerFrozenError):
            self._banned().with_length(Length(cm=99), now=LATER)

    def test_with_thickness_raises(self) -> None:
        with pytest.raises(PlayerFrozenError):
            self._banned().with_thickness(Thickness(level=5), now=LATER)

    def test_with_title_raises(self) -> None:
        with pytest.raises(PlayerFrozenError):
            self._banned().with_title(Title.NEWBIE, now=LATER)

    def test_with_name_raises(self) -> None:
        with pytest.raises(PlayerFrozenError):
            self._banned().with_name(PlayerName(value="X"), now=LATER)

    def test_without_name_raises(self) -> None:
        p = Player.new(tg_id=42, username=None, now=NOW).with_name(
            PlayerName(value="Иванушка"), now=NOW
        )
        banned = p.ban(now=NOW)
        with pytest.raises(PlayerFrozenError):
            banned.without_name(now=LATER)

    def test_with_username_raises(self) -> None:
        with pytest.raises(PlayerFrozenError):
            self._banned().with_username(Username(value="ivan"), now=LATER)
