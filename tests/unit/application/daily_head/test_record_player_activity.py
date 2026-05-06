"""Юнит-тесты `RecordPlayerActivity` (Спринт 2.3.F.1)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pipirik_wars.application.daily_head import RecordPlayerActivity
from pipirik_wars.application.dto.inputs import RecordPlayerActivityInput
from pipirik_wars.domain.player import Player, PlayerStatus
from tests.fakes import (
    FakeClock,
    FakeDailyActivityRepository,
    FakePlayerRepository,
    FakeUnitOfWork,
)

_NOW = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)
_TODAY_MSK = date(2026, 5, 6)


def _player(*, tg_id: int = 42, status: PlayerStatus = PlayerStatus.ACTIVE) -> Player:
    base = Player.new(tg_id=tg_id, username=None, now=_NOW)
    if status is PlayerStatus.ACTIVE:
        return replace(base, id=100)
    if status is PlayerStatus.FROZEN:
        # `freeze()` валиден только когда `id` уже выставлен.
        seeded = replace(base, id=100)
        return seeded.freeze(now=_NOW)
    raise AssertionError(f"unsupported status {status}")


def _build_use_case(
    *,
    players: FakePlayerRepository,
    activity: FakeDailyActivityRepository,
    clock: FakeClock | None = None,
) -> RecordPlayerActivity:
    return RecordPlayerActivity(
        uow=FakeUnitOfWork(),
        players=players,
        daily_activity=activity,
        clock=clock or FakeClock(_NOW),
    )


@pytest.mark.asyncio
class TestRecordPlayerActivity:
    async def test_unknown_player_is_noop(self) -> None:
        players = FakePlayerRepository()
        activity = FakeDailyActivityRepository()
        uc = _build_use_case(players=players, activity=activity)

        result = await uc.execute(RecordPlayerActivityInput(tg_user_id=999))

        assert result is False
        assert activity.record_calls == []

    async def test_active_player_records_with_clock_values(self) -> None:
        players = FakePlayerRepository(rows=[_player(tg_id=42)])
        activity = FakeDailyActivityRepository()
        uc = _build_use_case(players=players, activity=activity)

        result = await uc.execute(RecordPlayerActivityInput(tg_user_id=42))

        assert result is True
        assert len(activity.record_calls) == 1
        user_id, last_at, moscow_date = activity.record_calls[0]
        assert user_id == 100
        assert last_at == _NOW
        assert moscow_date == _TODAY_MSK
        assert activity.activity == {(_TODAY_MSK, 100): _NOW}

    async def test_frozen_player_is_noop(self) -> None:
        frozen = _player(tg_id=42, status=PlayerStatus.FROZEN)
        players = FakePlayerRepository(rows=[frozen])
        activity = FakeDailyActivityRepository()
        uc = _build_use_case(players=players, activity=activity)

        result = await uc.execute(RecordPlayerActivityInput(tg_user_id=42))

        assert result is False
        assert activity.record_calls == []

    async def test_player_without_id_is_noop(self) -> None:
        # Гипотетический случай — не должен бить FK; use-case skip-ит
        # игроков без `id` (они по факту не зарегистрированы в БД).
        unsaved = Player.new(tg_id=42, username=None, now=_NOW)  # id=None
        players = FakePlayerRepository(rows=[unsaved])
        activity = FakeDailyActivityRepository()
        uc = _build_use_case(players=players, activity=activity)

        result = await uc.execute(RecordPlayerActivityInput(tg_user_id=42))

        assert result is False
        assert activity.record_calls == []

    async def test_repeated_record_uses_fresh_clock(self) -> None:
        """Каждый вызов берёт свежий `now()` / `moscow_date()` из `IClock`."""
        players = FakePlayerRepository(rows=[_player(tg_id=42)])
        activity = FakeDailyActivityRepository()
        clock = FakeClock(_NOW)
        uc = _build_use_case(players=players, activity=activity, clock=clock)

        # Первый вызов в день D.
        await uc.execute(RecordPlayerActivityInput(tg_user_id=42))
        # Second call later in same day.
        clock.set(_NOW.replace(hour=18))
        await uc.execute(RecordPlayerActivityInput(tg_user_id=42))
        # Third call next day.
        clock.set(_NOW.replace(day=7, hour=9))
        await uc.execute(RecordPlayerActivityInput(tg_user_id=42))

        assert len(activity.record_calls) == 3
        # Свежий `now()` и `moscow_date()` каждый раз.
        assert activity.record_calls[0][1] == _NOW
        assert activity.record_calls[0][2] == _TODAY_MSK
        assert activity.record_calls[1][1] == _NOW.replace(hour=18)
        # `moscow_date` остался TODAY (тот же день).
        assert activity.record_calls[1][2] == _TODAY_MSK
        assert activity.record_calls[2][1] == _NOW.replace(day=7, hour=9)
        assert activity.record_calls[2][2] == date(2026, 5, 7)

    async def test_input_validation_rejects_zero_tg_id(self) -> None:
        with pytest.raises(ValidationError):
            RecordPlayerActivityInput(tg_user_id=0)

    async def test_input_validation_rejects_negative_tg_id(self) -> None:
        with pytest.raises(ValidationError):
            RecordPlayerActivityInput(tg_user_id=-1)
