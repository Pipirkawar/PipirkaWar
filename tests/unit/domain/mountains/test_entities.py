"""Тесты `MountainRun` (Спринт 3.1-A)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.balance.config import PveSign, Rarity, Slot
from pipirik_wars.domain.forest.entities import Item
from pipirik_wars.domain.mountains import (
    MountainRun,
    MountainRunStatus,
    PveItemDrop,
)
from pipirik_wars.domain.pve.entities import PveOutcomeBranch, PveRunOutcome


def _outcome(*, sign: PveSign = PveSign.GAIN, length_cm: int = 10) -> PveRunOutcome:
    branch = PveOutcomeBranch(
        name="normal_gain" if sign is PveSign.GAIN else "heavy_loss",
        sign=sign,
        length_cm=length_cm,
    )
    drop = PveItemDrop(
        item=Item(
            id="item.hat.test",
            slot=Slot.HAT,
            display_name="Шапка",
            rarity=Rarity.COMMON,
        )
    )
    return PveRunOutcome(
        branch=branch,
        length_delta_cm=length_cm if sign is PveSign.GAIN else -length_cm,
        drops=(drop,),
    )


def _now() -> datetime:
    return datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)


class TestMountainRunStarting:
    def test_creates_in_progress_run_with_id_none(self) -> None:
        started = _now()
        ends = started + timedelta(minutes=30)
        run = MountainRun.starting(
            player_id=42,
            outcome=_outcome(),
            started_at=started,
            ends_at=ends,
        )
        assert run.id is None
        assert run.player_id == 42
        assert run.status is MountainRunStatus.IN_PROGRESS
        assert run.is_in_progress is True
        assert run.started_at == started
        assert run.ends_at == ends
        assert run.branch_name == "normal_gain"
        assert run.length_delta_cm == 10
        assert len(run.drops) == 1
        assert run.finished_at is None

    def test_loss_outcome_negative_delta(self) -> None:
        started = _now()
        run = MountainRun.starting(
            player_id=1,
            outcome=_outcome(sign=PveSign.LOSS, length_cm=5),
            started_at=started,
            ends_at=started + timedelta(minutes=30),
        )
        assert run.length_delta_cm == -5
        assert run.branch_name == "heavy_loss"

    def test_ends_at_must_be_after_started_at(self) -> None:
        started = _now()
        with pytest.raises(ValueError, match="strictly after"):
            MountainRun.starting(
                player_id=1,
                outcome=_outcome(),
                started_at=started,
                ends_at=started,
            )

    def test_ends_at_before_started_at_rejected(self) -> None:
        started = _now()
        with pytest.raises(ValueError, match="strictly after"):
            MountainRun.starting(
                player_id=1,
                outcome=_outcome(),
                started_at=started,
                ends_at=started - timedelta(minutes=1),
            )


class TestMountainRunMarkFinished:
    def test_marks_in_progress_to_finished(self) -> None:
        started = _now()
        run = MountainRun.starting(
            player_id=1,
            outcome=_outcome(),
            started_at=started,
            ends_at=started + timedelta(minutes=30),
        )
        finished = started + timedelta(minutes=30, seconds=5)
        finished_run = run.mark_finished(finished_at=finished)
        assert finished_run.status is MountainRunStatus.FINISHED
        assert finished_run.is_in_progress is False
        assert finished_run.finished_at == finished
        # Остальные поля не меняются.
        assert finished_run.id == run.id
        assert finished_run.player_id == run.player_id
        assert finished_run.branch_name == run.branch_name
        assert finished_run.length_delta_cm == run.length_delta_cm
        assert finished_run.drops == run.drops

    def test_idempotent_on_already_finished(self) -> None:
        started = _now()
        run = MountainRun.starting(
            player_id=1,
            outcome=_outcome(),
            started_at=started,
            ends_at=started + timedelta(minutes=30),
        )
        first = run.mark_finished(finished_at=started + timedelta(minutes=30))
        second = first.mark_finished(finished_at=started + timedelta(hours=1))
        # Повторный финиш возвращает тот же объект (или эквивалентный — state не меняется).
        assert second is first
        assert second.finished_at == first.finished_at


class TestMountainRunImmutability:
    def test_run_is_frozen(self) -> None:
        started = _now()
        run = MountainRun.starting(
            player_id=1,
            outcome=_outcome(),
            started_at=started,
            ends_at=started + timedelta(minutes=30),
        )
        with pytest.raises(AttributeError):
            run.player_id = 999

    def test_drops_is_tuple(self) -> None:
        started = _now()
        run = MountainRun.starting(
            player_id=1,
            outcome=_outcome(),
            started_at=started,
            ends_at=started + timedelta(minutes=30),
        )
        assert isinstance(run.drops, tuple)


class TestMountainRunStatus:
    def test_values(self) -> None:
        assert MountainRunStatus.IN_PROGRESS.value == "in_progress"
        assert MountainRunStatus.FINISHED.value == "finished"


class TestMountainRunValidation:
    def test_empty_branch_name_rejected_via_direct_construction(self) -> None:
        # Прямая конструкция (не через .starting) должна валидироваться.
        started = _now()
        with pytest.raises(ValueError, match="non-empty"):
            MountainRun(
                id=None,
                player_id=1,
                status=MountainRunStatus.IN_PROGRESS,
                started_at=started,
                ends_at=started + timedelta(minutes=30),
                branch_name="",
                length_delta_cm=0,
                drops=(),
                finished_at=None,
            )
