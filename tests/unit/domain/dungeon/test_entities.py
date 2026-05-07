"""Тесты `DungeonRun` (Спринт 3.1-A)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.balance.config import PveSign, Rarity, Slot
from pipirik_wars.domain.dungeon import (
    DungeonRun,
    DungeonRunStatus,
    PveItemDrop,
)
from pipirik_wars.domain.forest.entities import Item
from pipirik_wars.domain.pve.entities import PveOutcomeBranch, PveRunOutcome


def _outcome(
    *,
    sign: PveSign = PveSign.GAIN,
    length_cm: int = 25,
    drops_count: int = 3,
) -> PveRunOutcome:
    branch = PveOutcomeBranch(
        name="normal_gain" if sign is PveSign.GAIN else "heavy_loss",
        sign=sign,
        length_cm=length_cm,
    )
    drops = tuple(
        PveItemDrop(
            item=Item(
                id=f"item.hat.test_{i}",
                slot=Slot.HAT,
                display_name=f"Шапка {i}",
                rarity=Rarity.COMMON,
            )
        )
        for i in range(drops_count)
    )
    return PveRunOutcome(
        branch=branch,
        length_delta_cm=length_cm if sign is PveSign.GAIN else -length_cm,
        drops=drops,
    )


def _now() -> datetime:
    return datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)


class TestDungeonRunStarting:
    def test_creates_in_progress_run_with_id_none(self) -> None:
        started = _now()
        ends = started + timedelta(minutes=50)
        run = DungeonRun.starting(
            player_id=42,
            outcome=_outcome(),
            started_at=started,
            ends_at=ends,
        )
        assert run.id is None
        assert run.player_id == 42
        assert run.status is DungeonRunStatus.IN_PROGRESS
        assert run.is_in_progress is True
        assert run.started_at == started
        assert run.ends_at == ends
        assert run.branch_name == "normal_gain"
        assert run.length_delta_cm == 25
        assert len(run.drops) == 3
        assert run.finished_at is None

    def test_loss_outcome_negative_delta(self) -> None:
        started = _now()
        run = DungeonRun.starting(
            player_id=1,
            outcome=_outcome(sign=PveSign.LOSS, length_cm=18, drops_count=0),
            started_at=started,
            ends_at=started + timedelta(minutes=50),
        )
        assert run.length_delta_cm == -18
        assert run.branch_name == "heavy_loss"
        assert run.drops == ()

    def test_zero_drops_supported(self) -> None:
        started = _now()
        run = DungeonRun.starting(
            player_id=1,
            outcome=_outcome(drops_count=0),
            started_at=started,
            ends_at=started + timedelta(minutes=50),
        )
        assert run.drops == ()

    def test_three_drops_supported(self) -> None:
        # Данжон даёт до 3 предметов (ГДД §8: "0–3 предмета").
        started = _now()
        run = DungeonRun.starting(
            player_id=1,
            outcome=_outcome(drops_count=3),
            started_at=started,
            ends_at=started + timedelta(minutes=50),
        )
        assert len(run.drops) == 3

    def test_ends_at_must_be_after_started_at(self) -> None:
        started = _now()
        with pytest.raises(ValueError, match="strictly after"):
            DungeonRun.starting(
                player_id=1,
                outcome=_outcome(),
                started_at=started,
                ends_at=started,
            )


class TestDungeonRunMarkFinished:
    def test_marks_in_progress_to_finished(self) -> None:
        started = _now()
        run = DungeonRun.starting(
            player_id=1,
            outcome=_outcome(),
            started_at=started,
            ends_at=started + timedelta(minutes=50),
        )
        finished = started + timedelta(minutes=50, seconds=5)
        finished_run = run.mark_finished(finished_at=finished)
        assert finished_run.status is DungeonRunStatus.FINISHED
        assert finished_run.is_in_progress is False
        assert finished_run.finished_at == finished
        assert finished_run.player_id == run.player_id
        assert finished_run.branch_name == run.branch_name
        assert finished_run.length_delta_cm == run.length_delta_cm
        assert finished_run.drops == run.drops

    def test_idempotent_on_already_finished(self) -> None:
        started = _now()
        run = DungeonRun.starting(
            player_id=1,
            outcome=_outcome(),
            started_at=started,
            ends_at=started + timedelta(minutes=50),
        )
        first = run.mark_finished(finished_at=started + timedelta(minutes=50))
        second = first.mark_finished(finished_at=started + timedelta(hours=2))
        assert second is first
        assert second.finished_at == first.finished_at


class TestDungeonRunImmutability:
    def test_run_is_frozen(self) -> None:
        started = _now()
        run = DungeonRun.starting(
            player_id=1,
            outcome=_outcome(),
            started_at=started,
            ends_at=started + timedelta(minutes=50),
        )
        with pytest.raises(AttributeError):
            run.player_id = 999  # type: ignore[misc]

    def test_drops_is_tuple(self) -> None:
        started = _now()
        run = DungeonRun.starting(
            player_id=1,
            outcome=_outcome(),
            started_at=started,
            ends_at=started + timedelta(minutes=50),
        )
        assert isinstance(run.drops, tuple)


class TestDungeonRunStatus:
    def test_values(self) -> None:
        assert DungeonRunStatus.IN_PROGRESS.value == "in_progress"
        assert DungeonRunStatus.FINISHED.value == "finished"


class TestDungeonRunValidation:
    def test_empty_branch_name_rejected_via_direct_construction(self) -> None:
        started = _now()
        with pytest.raises(ValueError, match="non-empty"):
            DungeonRun(
                id=None,
                player_id=1,
                status=DungeonRunStatus.IN_PROGRESS,
                started_at=started,
                ends_at=started + timedelta(minutes=50),
                branch_name="",
                length_delta_cm=0,
                drops=(),
                finished_at=None,
            )
