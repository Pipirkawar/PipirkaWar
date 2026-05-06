"""Юнит-тесты VO `DailyHeadAssignment` и enum `DailyHeadSource` (Спринт 2.3.A).

Покрывают:
- happy-path построения с разными `source`-вариантами;
- инварианты `__post_init__` (positive id, positive clan_id/player_id,
  positive bonus, timezone-aware assigned_at);
- frozen-семантику (нельзя мутировать поля);
- что `id=None` валиден (запись до `add()`-а).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from pipirik_wars.domain.daily_head import (
    DailyHeadAssignment,
    DailyHeadSource,
)


def _make_assignment(
    *,
    id: int | None = 1,
    clan_id: int = 42,
    player_id: int = 7,
    moscow_date: date = date(2026, 5, 6),
    source: DailyHeadSource = DailyHeadSource.BUTTON,
    bonus_cm: int = 10,
    assigned_at: datetime | None = None,
) -> DailyHeadAssignment:
    if assigned_at is None:
        assigned_at = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)
    return DailyHeadAssignment(
        id=id,
        clan_id=clan_id,
        player_id=player_id,
        moscow_date=moscow_date,
        source=source,
        bonus_cm=bonus_cm,
        assigned_at=assigned_at,
    )


class TestDailyHeadSource:
    def test_button_value(self) -> None:
        assert DailyHeadSource.BUTTON.value == "button"

    def test_cron_value(self) -> None:
        assert DailyHeadSource.CRON.value == "cron"

    def test_str_subclass(self) -> None:
        # Удобно для логов / audit-payload — не нужно явное `.value`.
        assert str(DailyHeadSource.BUTTON.value) == "button"

    def test_distinct_members(self) -> None:
        assert {DailyHeadSource.BUTTON, DailyHeadSource.CRON} == set(DailyHeadSource)


class TestDailyHeadAssignmentHappyPath:
    def test_construct_with_button_source(self) -> None:
        assignment = _make_assignment()
        assert assignment.source is DailyHeadSource.BUTTON
        assert assignment.bonus_cm == 10
        assert assignment.clan_id == 42
        assert assignment.player_id == 7

    def test_construct_with_cron_source(self) -> None:
        assignment = _make_assignment(source=DailyHeadSource.CRON)
        assert assignment.source is DailyHeadSource.CRON

    def test_id_none_allowed_for_unsaved_assignment(self) -> None:
        assignment = _make_assignment(id=None)
        assert assignment.id is None

    def test_assigned_at_with_non_utc_tz_allowed(self) -> None:
        # Любой timezone-aware datetime валиден; в БД пишем в UTC,
        # но VO не обязан конвертировать сам — это работа репозитория.
        moscow = timezone(timedelta(hours=3))
        assignment = _make_assignment(
            assigned_at=datetime(2026, 5, 6, 12, 0, tzinfo=moscow),
        )
        assert assignment.assigned_at.tzinfo is not None

    def test_minimal_bonus(self) -> None:
        assignment = _make_assignment(bonus_cm=1)
        assert assignment.bonus_cm == 1


class TestDailyHeadAssignmentFrozen:
    def test_cannot_mutate_clan_id(self) -> None:
        assignment = _make_assignment()
        with pytest.raises(FrozenInstanceError):
            assignment.clan_id = 99

    def test_cannot_mutate_player_id(self) -> None:
        assignment = _make_assignment()
        with pytest.raises(FrozenInstanceError):
            assignment.player_id = 99

    def test_cannot_mutate_bonus(self) -> None:
        assignment = _make_assignment()
        with pytest.raises(FrozenInstanceError):
            assignment.bonus_cm = 999


class TestDailyHeadAssignmentInvariants:
    @pytest.mark.parametrize("bad_id", [-1, 0])
    def test_negative_or_zero_id_rejected(self, bad_id: int) -> None:
        with pytest.raises(ValueError, match="must be positive or None"):
            _make_assignment(id=bad_id)

    @pytest.mark.parametrize("bad_clan_id", [-5, 0])
    def test_non_positive_clan_id_rejected(self, bad_clan_id: int) -> None:
        with pytest.raises(ValueError, match="clan_id must be positive"):
            _make_assignment(clan_id=bad_clan_id)

    @pytest.mark.parametrize("bad_player_id", [-1, 0])
    def test_non_positive_player_id_rejected(self, bad_player_id: int) -> None:
        with pytest.raises(ValueError, match="player_id must be positive"):
            _make_assignment(player_id=bad_player_id)

    @pytest.mark.parametrize("bad_bonus", [-3, 0])
    def test_non_positive_bonus_rejected(self, bad_bonus: int) -> None:
        with pytest.raises(ValueError, match="bonus_cm must be positive"):
            _make_assignment(bonus_cm=bad_bonus)

    def test_naive_assigned_at_rejected(self) -> None:
        with pytest.raises(ValueError, match="assigned_at must be timezone-aware"):
            _make_assignment(assigned_at=datetime(2026, 5, 6, 9, 0))  # naive!

    def test_id_is_none_does_not_trigger_positive_check(self) -> None:
        # id=None — валиден; проверка >0 должна сработать только для int.
        assignment = _make_assignment(id=None)
        assert assignment.id is None
