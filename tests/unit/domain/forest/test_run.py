"""Тесты сущности `ForestRun` (Спринт 1.3.B).

`ForestRun` — frozen dataclass, поэтому проверяем:
- фабрика `starting()` корректно проставляет статус и outcome;
- инвариант `ends_at > started_at` охраняется;
- мутатор `mark_finished` идемпотентен и возвращает новый экземпляр;
- иммутабельность поля `status` (нельзя присвоить напрямую).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.forest import (
    ForestRun,
    ForestRunStatus,
    Item,
    ItemDrop,
    NoDrop,
    OutcomeBranch,
    Rarity,
    Slot,
)
from pipirik_wars.domain.forest.entities import ForestRunOutcome


def _outcome_no_drop() -> ForestRunOutcome:
    return ForestRunOutcome(
        branch=OutcomeBranch(name="scarce", length_cm=3),
        length_cm=3,
        drop=NoDrop(),
    )


def _outcome_with_item() -> ForestRunOutcome:
    item = Item(
        id="item.hat.test",
        slot=Slot.HAT,
        display_name="Тест",
        rarity=Rarity.COMMON,
    )
    return ForestRunOutcome(
        branch=OutcomeBranch(name="normal", length_cm=12),
        length_cm=12,
        drop=ItemDrop(item=item),
    )


_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


class TestStartingFactory:
    def test_starting_status_is_in_progress(self) -> None:
        run = ForestRun.starting(
            player_id=42,
            outcome=_outcome_no_drop(),
            started_at=_NOW,
            ends_at=_NOW + timedelta(minutes=10),
        )
        assert run.status is ForestRunStatus.IN_PROGRESS
        assert run.is_in_progress is True
        assert run.id is None
        assert run.player_id == 42
        assert run.finished_at is None

    def test_starting_copies_outcome_fields(self) -> None:
        outcome = _outcome_with_item()
        run = ForestRun.starting(
            player_id=7,
            outcome=outcome,
            started_at=_NOW,
            ends_at=_NOW + timedelta(minutes=15),
        )
        assert run.branch_name == "normal"
        assert run.length_delta_cm == 12
        assert run.drop == outcome.drop
        assert run.started_at == _NOW
        assert run.ends_at == _NOW + timedelta(minutes=15)

    def test_starting_rejects_ends_at_equal_started_at(self) -> None:
        with pytest.raises(ValueError, match="ends_at must be strictly after started_at"):
            ForestRun.starting(
                player_id=1,
                outcome=_outcome_no_drop(),
                started_at=_NOW,
                ends_at=_NOW,
            )

    def test_starting_rejects_ends_at_before_started_at(self) -> None:
        with pytest.raises(ValueError, match="ends_at must be strictly after started_at"):
            ForestRun.starting(
                player_id=1,
                outcome=_outcome_no_drop(),
                started_at=_NOW,
                ends_at=_NOW - timedelta(minutes=1),
            )


class TestMarkFinished:
    def test_mark_finished_returns_new_instance_with_finished_status(self) -> None:
        run = ForestRun.starting(
            player_id=1,
            outcome=_outcome_no_drop(),
            started_at=_NOW,
            ends_at=_NOW + timedelta(minutes=10),
        )
        finish_at = _NOW + timedelta(minutes=11)
        finished = run.mark_finished(finished_at=finish_at)

        assert finished.status is ForestRunStatus.FINISHED
        assert finished.finished_at == finish_at
        assert finished.is_in_progress is False
        # старый экземпляр не мутировал
        assert run.status is ForestRunStatus.IN_PROGRESS
        assert run.finished_at is None

    def test_mark_finished_idempotent(self) -> None:
        run = ForestRun.starting(
            player_id=1,
            outcome=_outcome_no_drop(),
            started_at=_NOW,
            ends_at=_NOW + timedelta(minutes=10),
        )
        first = run.mark_finished(finished_at=_NOW + timedelta(minutes=11))
        # повторный вызов на уже финишированном — no-op
        second = first.mark_finished(finished_at=_NOW + timedelta(minutes=99))
        assert second is first

    def test_mark_finished_keeps_outcome_fields(self) -> None:
        outcome = _outcome_with_item()
        run = ForestRun.starting(
            player_id=1,
            outcome=outcome,
            started_at=_NOW,
            ends_at=_NOW + timedelta(minutes=10),
        )
        finished = run.mark_finished(finished_at=_NOW + timedelta(minutes=11))
        assert finished.branch_name == "normal"
        assert finished.length_delta_cm == 12
        assert finished.drop == outcome.drop


class TestImmutability:
    def test_cannot_assign_status(self) -> None:
        run = ForestRun.starting(
            player_id=1,
            outcome=_outcome_no_drop(),
            started_at=_NOW,
            ends_at=_NOW + timedelta(minutes=10),
        )
        with pytest.raises(AttributeError):
            run.status = ForestRunStatus.FINISHED
