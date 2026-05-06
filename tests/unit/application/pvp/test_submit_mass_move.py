"""Unit-тесты `SubmitMassMove` (Спринт 2.2.E)."""

from __future__ import annotations

import pytest

from pipirik_wars.application.dto.inputs import SubmitMassMoveInput
from pipirik_wars.application.pvp import MassMoveSubmitted, SubmitMassMove
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.pvp import (
    InvalidMassDuelStateError,
    MassDuel,
    MassDuelNotFoundError,
    MassMoveAlreadySubmittedError,
    MassRoundChoice,
    NotAMassDuelParticipantError,
    Position,
)
from tests.fakes import (
    FakeClock,
    FakeMassDuelRepository,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.application.pvp._helpers import seed_pvp_eligible_player
from tests.unit.application.pvp._mass_helpers import MASS_NOW


def _build() -> tuple[
    SubmitMassMove,
    FakePlayerRepository,
    FakeMassDuelRepository,
    FakeUnitOfWork,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    duels = FakeMassDuelRepository()
    clock = FakeClock(MASS_NOW)
    use_case = SubmitMassMove(uow=uow, players=players, duels=duels, clock=clock)
    return use_case, players, duels, uow, clock


async def _seed_in_progress_duel(
    *,
    players: FakePlayerRepository,
    duels: FakeMassDuelRepository,
) -> tuple[MassDuel, int, int, int, int]:
    """Создать 2×2 mass-duel и вернуть `(duel, a1, a2, d1, d2)`."""
    a1_player = await seed_pvp_eligible_player(players, tg_id=1, username="a1")
    a2_player = await seed_pvp_eligible_player(players, tg_id=2, username="a2")
    d1_player = await seed_pvp_eligible_player(players, tg_id=3, username="d1")
    d2_player = await seed_pvp_eligible_player(players, tg_id=4, username="d2")
    assert a1_player.id is not None
    assert a2_player.id is not None
    assert d1_player.id is not None
    assert d2_player.id is not None
    a1, a2, d1, d2 = a1_player.id, a2_player.id, d1_player.id, d2_player.id
    duel = MassDuel.create_battle(
        clan1_id=10,
        clan2_id=20,
        clan1_lengths={a1: a1_player.length.cm, a2: a2_player.length.cm},
        clan2_lengths={d1: d1_player.length.cm, d2: d2_player.length.cm},
        hit_pct=10,
        now=MASS_NOW,
    )
    saved = await duels.add(duel)
    return saved, a1, a2, d1, d2


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_first_submit_keeps_duel_in_progress(self) -> None:
        use_case, players, duels, uow, _clock = _build()
        duel, a1, _a2, _d1, _d2 = await _seed_in_progress_duel(players=players, duels=duels)
        assert duel.id is not None

        result = await use_case.execute(
            SubmitMassMoveInput(
                duel_id=duel.id,
                tg_id=1,  # a1
                attack="high",
                block="mid",
            )
        )
        assert isinstance(result, MassMoveSubmitted)
        assert result.is_ready_to_resolve is False
        assert result.duel.state.value == "in_progress"
        # Один выбор уже не None.
        choices = (*result.duel.clan1_choices, *result.duel.clan2_choices)
        assert sum(1 for c in choices if c is not None) == 1
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_last_submit_marks_ready_to_resolve(self) -> None:
        use_case, players, duels, _uow, _clock = _build()
        duel, a1, a2, d1, d2 = await _seed_in_progress_duel(players=players, duels=duels)
        assert duel.id is not None

        for tg_id in (1, 2, 3, 4):
            await use_case.execute(
                SubmitMassMoveInput(
                    duel_id=duel.id,
                    tg_id=tg_id,
                    attack="high",
                    block="mid",
                )
            )
        loaded = await duels.get_by_id(duel_id=duel.id)
        assert loaded is not None
        assert loaded.is_ready_to_resolve is True

    @pytest.mark.asyncio
    async def test_choice_payload_persisted(self) -> None:
        use_case, players, duels, *_ = _build()
        duel, a1, _a2, _d1, _d2 = await _seed_in_progress_duel(players=players, duels=duels)
        assert duel.id is not None

        await use_case.execute(
            SubmitMassMoveInput(
                duel_id=duel.id,
                tg_id=1,
                attack="low",
                block="high",
            )
        )
        loaded = await duels.get_by_id(duel_id=duel.id)
        assert loaded is not None
        idx = loaded.clan1_member_ids.index(a1)
        choice = loaded.clan1_choices[idx]
        assert choice == MassRoundChoice(
            player_id=a1,
            attack=Position.LOW,
            block=Position.HIGH,
        )


class TestErrors:
    @pytest.mark.asyncio
    async def test_duel_not_found_raises(self) -> None:
        use_case, players, _duels, _uow, _clock = _build()
        await seed_pvp_eligible_player(players, tg_id=1)
        with pytest.raises(MassDuelNotFoundError):
            await use_case.execute(
                SubmitMassMoveInput(
                    duel_id=999,
                    tg_id=1,
                    attack="high",
                    block="mid",
                )
            )

    @pytest.mark.asyncio
    async def test_unknown_player_raises(self) -> None:
        use_case, players, duels, *_ = _build()
        duel, *_ = await _seed_in_progress_duel(players=players, duels=duels)
        assert duel.id is not None
        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(
                SubmitMassMoveInput(
                    duel_id=duel.id,
                    tg_id=999,
                    attack="high",
                    block="mid",
                )
            )

    @pytest.mark.asyncio
    async def test_non_participant_raises(self) -> None:
        use_case, players, duels, *_ = _build()
        duel, *_ = await _seed_in_progress_duel(players=players, duels=duels)
        outsider = await seed_pvp_eligible_player(players, tg_id=99, username="x")
        assert duel.id is not None
        assert outsider.id is not None
        with pytest.raises(NotAMassDuelParticipantError):
            await use_case.execute(
                SubmitMassMoveInput(
                    duel_id=duel.id,
                    tg_id=99,
                    attack="high",
                    block="mid",
                )
            )

    @pytest.mark.asyncio
    async def test_double_submit_same_player_raises(self) -> None:
        use_case, players, duels, *_ = _build()
        duel, *_ = await _seed_in_progress_duel(players=players, duels=duels)
        assert duel.id is not None
        await use_case.execute(
            SubmitMassMoveInput(duel_id=duel.id, tg_id=1, attack="high", block="mid")
        )
        with pytest.raises(MassMoveAlreadySubmittedError):
            await use_case.execute(
                SubmitMassMoveInput(duel_id=duel.id, tg_id=1, attack="low", block="high")
            )

    @pytest.mark.asyncio
    async def test_cancelled_duel_raises_invalid_state(self) -> None:
        use_case, players, duels, *_ = _build()
        duel, *_ = await _seed_in_progress_duel(players=players, duels=duels)
        assert duel.id is not None
        cancelled = duel.cancel(now=MASS_NOW)
        await duels.save(cancelled)
        with pytest.raises(InvalidMassDuelStateError):
            await use_case.execute(
                SubmitMassMoveInput(duel_id=duel.id, tg_id=1, attack="high", block="mid")
            )
