"""Тесты для `ClanMassDuelHistoryEntry` (Спринт 2.2.G / ПД 2.2.5).

Проверяем `__post_init__`-инварианты: zero-sum, согласованность
state↔outcome↔completed_at, полу-открытые границы участников и
маппинг outcome (`outcome_from_winner`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.clan.value_objects import ClanTitle
from pipirik_wars.domain.pvp import (
    ClanMassDuelHistoryEntry,
    ClanMassDuelOutcomeForUs,
    MassDuelState,
    MassDuelWinner,
)

_SENTINEL_COMPLETED_AT = datetime(1970, 1, 1, tzinfo=UTC)


def _entry(
    *,
    duel_id: int = 42,
    our_clan_id: int = 100,
    opponent_clan_id: int = 200,
    opponent_clan_title: ClanTitle | None = None,
    state: MassDuelState = MassDuelState.COMPLETED,
    outcome: ClanMassDuelOutcomeForUs = ClanMassDuelOutcomeForUs.VICTORY,
    our_total_dealt: int = 30,
    our_total_received: int = 10,
    our_delta_cm: int = 20,
    opponent_delta_cm: int = -20,
    our_participants_count: int = 3,
    opponent_participants_count: int = 3,
    created_at: datetime | None = None,
    completed_at: datetime | None = _SENTINEL_COMPLETED_AT,
) -> ClanMassDuelHistoryEntry:
    if opponent_clan_title is None:
        opponent_clan_title = ClanTitle("Жмыхи")
    if created_at is None:
        created_at = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    if completed_at is _SENTINEL_COMPLETED_AT:
        completed_at = (
            None if state is MassDuelState.CANCELLED else datetime(2026, 5, 6, 12, 5, tzinfo=UTC)
        )
    return ClanMassDuelHistoryEntry(
        duel_id=duel_id,
        our_clan_id=our_clan_id,
        opponent_clan_id=opponent_clan_id,
        opponent_clan_title=opponent_clan_title,
        state=state,
        outcome=outcome,
        our_total_dealt=our_total_dealt,
        our_total_received=our_total_received,
        our_delta_cm=our_delta_cm,
        opponent_delta_cm=opponent_delta_cm,
        our_participants_count=our_participants_count,
        opponent_participants_count=opponent_participants_count,
        created_at=created_at,
        completed_at=completed_at,
    )


class TestValidConstruction:
    def test_victory_entry_constructs(self) -> None:
        entry = _entry()
        assert entry.outcome is ClanMassDuelOutcomeForUs.VICTORY
        assert entry.state is MassDuelState.COMPLETED
        assert entry.completed_at is not None

    def test_defeat_entry(self) -> None:
        entry = _entry(
            outcome=ClanMassDuelOutcomeForUs.DEFEAT,
            our_total_dealt=10,
            our_total_received=30,
            our_delta_cm=-20,
            opponent_delta_cm=20,
        )
        assert entry.outcome is ClanMassDuelOutcomeForUs.DEFEAT

    def test_draw_entry(self) -> None:
        entry = _entry(
            outcome=ClanMassDuelOutcomeForUs.DRAW,
            our_total_dealt=15,
            our_total_received=15,
            our_delta_cm=0,
            opponent_delta_cm=0,
        )
        assert entry.outcome is ClanMassDuelOutcomeForUs.DRAW

    def test_cancelled_entry(self) -> None:
        entry = _entry(
            state=MassDuelState.CANCELLED,
            outcome=ClanMassDuelOutcomeForUs.CANCELLED,
            our_total_dealt=0,
            our_total_received=0,
            our_delta_cm=0,
            opponent_delta_cm=0,
            completed_at=None,
        )
        assert entry.state is MassDuelState.CANCELLED
        assert entry.completed_at is None


class TestInvariants:
    @pytest.mark.parametrize("bad", [0, -1, -100])
    def test_duel_id_must_be_positive(self, bad: int) -> None:
        with pytest.raises(ValueError, match="duel_id must be > 0"):
            _entry(duel_id=bad)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_our_clan_id_must_be_positive(self, bad: int) -> None:
        with pytest.raises(ValueError, match="our_clan_id must be > 0"):
            _entry(our_clan_id=bad)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_opponent_clan_id_must_be_positive(self, bad: int) -> None:
        with pytest.raises(ValueError, match="opponent_clan_id must be > 0"):
            _entry(opponent_clan_id=bad)

    def test_clan_ids_must_differ(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            _entry(our_clan_id=100, opponent_clan_id=100)

    def test_negative_total_dealt_rejected(self) -> None:
        with pytest.raises(ValueError, match="our_total_dealt must be >= 0"):
            _entry(our_total_dealt=-1)

    def test_negative_total_received_rejected(self) -> None:
        with pytest.raises(ValueError, match="our_total_received must be >= 0"):
            _entry(our_total_received=-1)

    def test_zero_sum_violated(self) -> None:
        with pytest.raises(ValueError, match="must equal 0 \\(zero-sum\\)"):
            _entry(our_delta_cm=15, opponent_delta_cm=-10)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_our_participants_must_be_positive(self, bad: int) -> None:
        with pytest.raises(ValueError, match="our_participants_count"):
            _entry(our_participants_count=bad)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_opponent_participants_must_be_positive(self, bad: int) -> None:
        with pytest.raises(ValueError, match="opponent_participants_count"):
            _entry(opponent_participants_count=bad)


class TestStateOutcomeAgreement:
    def test_completed_state_with_cancelled_outcome_rejected(self) -> None:
        with pytest.raises(ValueError, match="must agree"):
            _entry(
                state=MassDuelState.COMPLETED,
                outcome=ClanMassDuelOutcomeForUs.CANCELLED,
                completed_at=None,
            )

    def test_cancelled_state_with_victory_outcome_rejected(self) -> None:
        with pytest.raises(ValueError, match="must agree"):
            _entry(
                state=MassDuelState.CANCELLED,
                outcome=ClanMassDuelOutcomeForUs.VICTORY,
                completed_at=None,
            )

    def test_cancelled_with_completed_at_rejected(self) -> None:
        with pytest.raises(ValueError, match="completed_at must be None"):
            _entry(
                state=MassDuelState.CANCELLED,
                outcome=ClanMassDuelOutcomeForUs.CANCELLED,
                completed_at=datetime(2026, 5, 6, 12, 5, tzinfo=UTC),
                our_total_dealt=0,
                our_total_received=0,
                our_delta_cm=0,
                opponent_delta_cm=0,
            )

    def test_completed_without_completed_at_rejected(self) -> None:
        with pytest.raises(ValueError, match="completed_at must be set"):
            _entry(
                state=MassDuelState.COMPLETED,
                outcome=ClanMassDuelOutcomeForUs.VICTORY,
                completed_at=None,
            )


class TestOutcomeArithmeticAgreement:
    def test_victory_requires_dealt_gt_received(self) -> None:
        with pytest.raises(ValueError, match="VICTORY requires"):
            _entry(
                outcome=ClanMassDuelOutcomeForUs.VICTORY,
                our_total_dealt=10,
                our_total_received=15,
                our_delta_cm=-5,
                opponent_delta_cm=5,
            )

    def test_defeat_requires_dealt_lt_received(self) -> None:
        with pytest.raises(ValueError, match="DEFEAT requires"):
            _entry(
                outcome=ClanMassDuelOutcomeForUs.DEFEAT,
                our_total_dealt=15,
                our_total_received=10,
                our_delta_cm=5,
                opponent_delta_cm=-5,
            )

    def test_draw_requires_dealt_eq_received(self) -> None:
        with pytest.raises(ValueError, match="DRAW requires"):
            _entry(
                outcome=ClanMassDuelOutcomeForUs.DRAW,
                our_total_dealt=10,
                our_total_received=15,
                our_delta_cm=-5,
                opponent_delta_cm=5,
            )


class TestOutcomeFromWinner:
    @pytest.mark.parametrize(
        ("winner", "side", "expected"),
        [
            (MassDuelWinner.CLAN1, "clan1", ClanMassDuelOutcomeForUs.VICTORY),
            (MassDuelWinner.CLAN1, "clan2", ClanMassDuelOutcomeForUs.DEFEAT),
            (MassDuelWinner.CLAN2, "clan1", ClanMassDuelOutcomeForUs.DEFEAT),
            (MassDuelWinner.CLAN2, "clan2", ClanMassDuelOutcomeForUs.VICTORY),
            (MassDuelWinner.DRAW, "clan1", ClanMassDuelOutcomeForUs.DRAW),
            (MassDuelWinner.DRAW, "clan2", ClanMassDuelOutcomeForUs.DRAW),
        ],
    )
    def test_mapping(
        self,
        winner: MassDuelWinner,
        side: str,
        expected: ClanMassDuelOutcomeForUs,
    ) -> None:
        assert (
            ClanMassDuelHistoryEntry.outcome_from_winner(
                winner=winner,
                our_side=side,
            )
            is expected
        )

    def test_invalid_side_rejected(self) -> None:
        with pytest.raises(ValueError, match="our_side must be"):
            ClanMassDuelHistoryEntry.outcome_from_winner(
                winner=MassDuelWinner.CLAN1,
                our_side="clan3",
            )
