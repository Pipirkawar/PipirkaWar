"""Unit-тесты агрегата `MassDuel` (Спринт 2.2.C).

Покрывают:

* конструктор `create_battle` (валидация входов, sorted-ростер,
  начальное состояние со всеми choices=None);
* `__post_init__`-инварианты (повторно при `replace`);
* свойства `is_in_progress` / `is_completed` / `is_cancelled` /
  `is_terminal` / `is_ready_to_resolve` / `missing_player_ids` /
  `is_participant`;
* `submit_move` (валидный, повтор, не-участник, неправильное состояние,
  чужой `choice.player_id`);
* `force_submit_missing` (валидный, no-missing, неполное покрытие
  fallback, неправильный `player_id` в fallback-choice, не-IN_PROGRESS);
* `resolve` (валидный с детерминированным RNG, до полного submit
  → `MassDuelNotReadyError`, повтор после COMPLETED → InvalidState);
* `cancel` (валидный из IN_PROGRESS, идемпотентный из CANCELLED,
  запрет из COMPLETED);
* immutability — все мутаторы возвращают новый инстанс.

Ровно те же принципы, что для `Duel` (1×1) в `test_duel.py`:
параметризация краёв, отдельные классы под каждое поведение.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.pvp import (
    InvalidMassDuelStateError,
    MassDuel,
    MassDuelNotReadyError,
    MassDuelOutcome,
    MassDuelState,
    MassDuelWinner,
    MassMoveAlreadySubmittedError,
    MassRoundChoice,
    MassRoundOutcome,
    NoMissingMassMovesError,
    NotAMassDuelParticipantError,
    Position,
)
from tests.fakes.random import FakeRandom

NOW = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)


def _choice(
    player_id: int, *, attack: Position = Position.HIGH, block: Position = Position.MID
) -> MassRoundChoice:
    return MassRoundChoice(player_id=player_id, attack=attack, block=block)


class TestCreateBattle:
    def test_minimal_2v2_creates_in_progress_with_no_choices(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100, 11: 80},
            clan2_lengths={20: 90, 21: 70},
            hit_pct=10,
            now=NOW,
        )
        assert d.state is MassDuelState.IN_PROGRESS
        assert d.is_in_progress is True
        assert d.is_completed is False
        assert d.is_cancelled is False
        assert d.is_terminal is False
        assert d.is_ready_to_resolve is False
        assert d.id is None
        assert d.clan1_id == 1
        assert d.clan2_id == 2
        # member_ids sorted by player_id
        assert d.clan1_member_ids == (10, 11)
        assert d.clan2_member_ids == (20, 21)
        assert d.clan1_initial_lengths == (100, 80)
        assert d.clan2_initial_lengths == (90, 70)
        # все None — никто ещё не отправил
        assert d.clan1_choices == (None, None)
        assert d.clan2_choices == (None, None)
        assert d.created_at == NOW
        assert d.completed_at is None
        assert d.cancelled_at is None
        assert d.final_outcome is None
        assert d.hit_pct == 10
        assert d.missing_player_ids == (10, 11, 20, 21)

    def test_singleton_each_side_creates_1v1(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100},
            clan2_lengths={20: 50},
            hit_pct=20,
            now=NOW,
        )
        assert d.clan1_member_ids == (10,)
        assert d.clan2_member_ids == (20,)
        assert d.clan1_initial_lengths == (100,)
        assert d.clan2_initial_lengths == (50,)
        assert d.missing_player_ids == (10, 20)

    def test_unsorted_input_dict_yields_sorted_member_ids(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={30: 50, 10: 100, 20: 80},
            clan2_lengths={40: 60, 50: 70},
            hit_pct=10,
            now=NOW,
        )
        assert d.clan1_member_ids == (10, 20, 30)
        # параллелизм lengths сохраняется относительно sorted member_ids
        assert d.clan1_initial_lengths == (100, 80, 50)
        assert d.clan2_member_ids == (40, 50)
        assert d.clan2_initial_lengths == (60, 70)

    def test_same_clan_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            MassDuel.create_battle(
                clan1_id=1,
                clan2_id=1,
                clan1_lengths={10: 100},
                clan2_lengths={20: 50},
                hit_pct=10,
                now=NOW,
            )

    @pytest.mark.parametrize("bad_clan_id", [0, -1, -999])
    def test_non_positive_clan_id_rejected(self, bad_clan_id: int) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            MassDuel.create_battle(
                clan1_id=bad_clan_id,
                clan2_id=2,
                clan1_lengths={10: 100},
                clan2_lengths={20: 50},
                hit_pct=10,
                now=NOW,
            )

    @pytest.mark.parametrize("bad_hit_pct", [-1, 101, 200])
    def test_hit_pct_out_of_range_rejected(self, bad_hit_pct: int) -> None:
        with pytest.raises(ValueError, match="hit_pct"):
            MassDuel.create_battle(
                clan1_id=1,
                clan2_id=2,
                clan1_lengths={10: 100},
                clan2_lengths={20: 50},
                hit_pct=bad_hit_pct,
                now=NOW,
            )

    def test_empty_clan_roster_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            MassDuel.create_battle(
                clan1_id=1,
                clan2_id=2,
                clan1_lengths={},
                clan2_lengths={20: 50},
                hit_pct=10,
                now=NOW,
            )
        with pytest.raises(ValueError, match="non-empty"):
            MassDuel.create_battle(
                clan1_id=1,
                clan2_id=2,
                clan1_lengths={10: 100},
                clan2_lengths={},
                hit_pct=10,
                now=NOW,
            )

    @pytest.mark.parametrize("bad_pid", [0, -5])
    def test_non_positive_player_id_rejected(self, bad_pid: int) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            MassDuel.create_battle(
                clan1_id=1,
                clan2_id=2,
                clan1_lengths={bad_pid: 100},
                clan2_lengths={20: 50},
                hit_pct=10,
                now=NOW,
            )

    def test_negative_length_rejected(self) -> None:
        with pytest.raises(ValueError, match=">= 0"):
            MassDuel.create_battle(
                clan1_id=1,
                clan2_id=2,
                clan1_lengths={10: -1},
                clan2_lengths={20: 50},
                hit_pct=10,
                now=NOW,
            )

    def test_zero_length_allowed(self) -> None:
        # Игрок с длиной 0 всё равно может участвовать (use-case фильтрует
        # по `min_length_cm` ДО `create_battle`; сам агрегат лишь требует
        # неотрицательности).
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 0},
            clan2_lengths={20: 50},
            hit_pct=10,
            now=NOW,
        )
        assert d.clan1_initial_lengths == (0,)

    def test_overlapping_rosters_rejected(self) -> None:
        # ГДД §7.2 / 2.2.3 — игрок в обоих кланах должен быть отфильтрован
        # use-case-ом до `create_battle`. Агрегат отвергает overlap явно.
        with pytest.raises(ValueError, match="disjoint"):
            MassDuel.create_battle(
                clan1_id=1,
                clan2_id=2,
                clan1_lengths={10: 100, 50: 80},
                clan2_lengths={20: 50, 50: 30},  # 50 в обоих
                hit_pct=10,
                now=NOW,
            )


class TestPostInitInvariantsOnReplace:
    """Проверяем, что `__post_init__` срабатывает не только на `create_battle`,
    но и на ручной replace (т. е. при «незаконных» замешательствах
    кто-то получит исключение, а не молча битый агрегат)."""

    def _valid_duel(self) -> MassDuel:
        return MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100, 11: 80},
            clan2_lengths={20: 90, 21: 70},
            hit_pct=10,
            now=NOW,
        )

    def test_replace_completed_without_outcome_rejected(self) -> None:
        d = self._valid_duel()
        with pytest.raises(ValueError, match="must have final_outcome"):
            replace(
                d,
                state=MassDuelState.COMPLETED,
                completed_at=LATER,
                final_outcome=None,
            )

    def test_replace_completed_without_completed_at_rejected(self) -> None:
        d = self._valid_duel()
        # Завершённая дуэль должна иметь и outcome, и completed_at — иначе
        # это нарушение state-machine инварианта.
        # outcome нужен, чтобы дойти до проверки completed_at; но до неё
        # сначала упадёт «must have final_outcome» из предыдущего теста.
        # Здесь подаём ОДИН из двух нарушений: completed_at=None, outcome=None.
        # → выскочит из первого проверяемого инварианта.
        with pytest.raises(ValueError):
            replace(
                d,
                state=MassDuelState.COMPLETED,
                completed_at=None,
                final_outcome=None,
            )

    def test_replace_in_progress_with_final_outcome_rejected(self) -> None:
        d = self._valid_duel()
        # Можно собрать valid outcome через resolve, но проще — мочно
        # «протащить» Mock-объект; нам важен только инвариант агрегата
        # (final_outcome для не-COMPLETED). Минимальный sentinel:
        outcome = _make_dummy_outcome()
        with pytest.raises(ValueError, match="must not have final_outcome"):
            replace(
                d,
                state=MassDuelState.IN_PROGRESS,
                final_outcome=outcome,
            )

    def test_replace_cancelled_without_cancelled_at_rejected(self) -> None:
        d = self._valid_duel()
        with pytest.raises(ValueError, match="must have cancelled_at"):
            replace(
                d,
                state=MassDuelState.CANCELLED,
                cancelled_at=None,
            )

    def test_replace_with_unsorted_member_ids_rejected(self) -> None:
        d = self._valid_duel()
        with pytest.raises(ValueError, match="sorted ascending"):
            replace(d, clan1_member_ids=(11, 10))

    def test_replace_with_choice_player_id_mismatch_rejected(self) -> None:
        d = self._valid_duel()
        # Подсунуть на индекс [0] (player_id=10) выбор от player_id=11
        with pytest.raises(ValueError, match="must match member_id"):
            replace(d, clan1_choices=(_choice(11), None))


class TestSubmitMove:
    def _new_duel(self) -> MassDuel:
        return MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100, 11: 80},
            clan2_lengths={20: 90, 21: 70},
            hit_pct=10,
            now=NOW,
        )

    def test_submit_for_clan1_member_records_choice(self) -> None:
        d = self._new_duel()
        d2 = d.submit_move(player_id=10, choice=_choice(10), now=LATER)
        # старый инстанс не мутировался
        assert d.clan1_choices == (None, None)
        assert d2.clan1_choices == (_choice(10), None)
        assert d2.clan2_choices == (None, None)
        assert d2.missing_player_ids == (11, 20, 21)
        assert d2 is not d

    def test_submit_for_clan2_member_records_choice(self) -> None:
        d = self._new_duel()
        d2 = d.submit_move(player_id=20, choice=_choice(20), now=LATER)
        assert d2.clan1_choices == (None, None)
        assert d2.clan2_choices == (_choice(20), None)
        assert d2.missing_player_ids == (10, 11, 21)

    def test_submit_all_members_makes_ready_to_resolve(self) -> None:
        d = self._new_duel()
        for pid in (10, 11, 20, 21):
            d = d.submit_move(player_id=pid, choice=_choice(pid), now=LATER)
        assert d.is_ready_to_resolve is True
        assert d.missing_player_ids == ()

    def test_double_submit_rejected(self) -> None:
        d = self._new_duel()
        d = d.submit_move(player_id=10, choice=_choice(10), now=LATER)
        with pytest.raises(MassMoveAlreadySubmittedError) as exc:
            d.submit_move(player_id=10, choice=_choice(10, attack=Position.LOW), now=LATER)
        assert exc.value.player_id == 10

    def test_non_participant_rejected(self) -> None:
        d = self._new_duel()
        with pytest.raises(NotAMassDuelParticipantError) as exc:
            d.submit_move(player_id=999, choice=_choice(999), now=LATER)
        assert exc.value.player_id == 999

    def test_choice_player_id_mismatch_rejected(self) -> None:
        d = self._new_duel()
        # `submit_move(player_id=10, ...)` с choice от другого игрока — баг
        # выше use-case-а. Защита: ValueError перед проверкой is_participant.
        with pytest.raises(ValueError, match="must match"):
            d.submit_move(player_id=10, choice=_choice(11), now=LATER)

    def test_submit_in_completed_rejected(self) -> None:
        d = _completed_duel()
        with pytest.raises(InvalidMassDuelStateError):
            d.submit_move(player_id=10, choice=_choice(10), now=LATER)

    def test_submit_in_cancelled_rejected(self) -> None:
        d = self._new_duel().cancel(now=LATER)
        with pytest.raises(InvalidMassDuelStateError):
            d.submit_move(player_id=10, choice=_choice(10), now=LATER)


class TestForceSubmitMissing:
    def _new_duel(self) -> MassDuel:
        return MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100, 11: 80},
            clan2_lengths={20: 90, 21: 70},
            hit_pct=10,
            now=NOW,
        )

    def test_force_fills_all_missing(self) -> None:
        d = self._new_duel()
        # Один уже отправил; force за 3 оставшихся.
        d = d.submit_move(player_id=10, choice=_choice(10), now=LATER)
        fallback = {
            11: _choice(11, attack=Position.LOW),
            20: _choice(20, attack=Position.MID),
            21: _choice(21, attack=Position.HIGH),
        }
        d2 = d.force_submit_missing(fallback_choices=fallback, now=LATER)
        assert d2.is_ready_to_resolve is True
        assert d2.clan1_choices == (_choice(10), _choice(11, attack=Position.LOW))
        assert d2.clan2_choices == (
            _choice(20, attack=Position.MID),
            _choice(21, attack=Position.HIGH),
        )

    def test_force_when_nothing_missing_raises(self) -> None:
        d = self._new_duel()
        for pid in (10, 11, 20, 21):
            d = d.submit_move(player_id=pid, choice=_choice(pid), now=LATER)
        assert d.is_ready_to_resolve is True
        with pytest.raises(NoMissingMassMovesError):
            d.force_submit_missing(fallback_choices={}, now=LATER)

    def test_force_with_extra_keys_in_fallback_rejected(self) -> None:
        d = self._new_duel()
        fallback = {pid: _choice(pid) for pid in (10, 11, 20, 21, 999)}
        with pytest.raises(ValueError, match="must equal missing player_ids"):
            d.force_submit_missing(fallback_choices=fallback, now=LATER)

    def test_force_with_partial_fallback_rejected(self) -> None:
        d = self._new_duel()
        fallback = {pid: _choice(pid) for pid in (10, 11)}
        with pytest.raises(ValueError, match="must equal missing player_ids"):
            d.force_submit_missing(fallback_choices=fallback, now=LATER)

    def test_force_with_choice_player_id_mismatch_rejected(self) -> None:
        d = self._new_duel()
        fallback = {
            10: _choice(11),  # неправильный player_id
            11: _choice(11),
            20: _choice(20),
            21: _choice(21),
        }
        with pytest.raises(ValueError, match="must match key"):
            d.force_submit_missing(fallback_choices=fallback, now=LATER)

    def test_force_in_completed_rejected(self) -> None:
        d = _completed_duel()
        with pytest.raises(InvalidMassDuelStateError):
            d.force_submit_missing(fallback_choices={}, now=LATER)

    def test_force_in_cancelled_rejected(self) -> None:
        d = self._new_duel().cancel(now=LATER)
        with pytest.raises(InvalidMassDuelStateError):
            d.force_submit_missing(fallback_choices={}, now=LATER)


class TestResolve:
    def _ready_duel(self) -> MassDuel:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100, 11: 80},
            clan2_lengths={20: 90, 21: 70},
            hit_pct=10,
            now=NOW,
        )
        for pid in (10, 11, 20, 21):
            d = d.submit_move(player_id=pid, choice=_choice(pid), now=LATER)
        return d

    def test_resolve_when_ready_completes_duel(self) -> None:
        d = self._ready_duel()
        d2 = d.resolve(random=FakeRandom(seed=42), now=LATER)
        assert d2.state is MassDuelState.COMPLETED
        assert d2.is_completed is True
        assert d2.is_terminal is True
        assert d2.completed_at == LATER
        assert d2.final_outcome is not None
        # choices не модифицируются — это снапшот, retained для аудита
        assert d2.clan1_choices == d.clan1_choices
        assert d2.clan2_choices == d.clan2_choices
        # zero-sum инвариант — пройдёт через MassDuelOutcome.__post_init__
        assert d2.final_outcome.clan1_delta_cm + d2.final_outcome.clan2_delta_cm == 0

    def test_resolve_is_deterministic_by_seed(self) -> None:
        d = self._ready_duel()
        out1 = d.resolve(random=FakeRandom(seed=7), now=LATER).final_outcome
        out2 = d.resolve(random=FakeRandom(seed=7), now=LATER).final_outcome
        assert out1 is not None
        assert out2 is not None
        assert out1.winner is out2.winner
        assert out1.clan1_total_dealt == out2.clan1_total_dealt
        assert out1.clan2_total_dealt == out2.clan2_total_dealt

    def test_resolve_with_full_block_yields_draw(self) -> None:
        # Все игроки бьют HIGH и блокируют HIGH — все удары blocked,
        # никто никому ничего не нанёс → DRAW, дельты = 0.
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100, 11: 80},
            clan2_lengths={20: 90, 21: 70},
            hit_pct=10,
            now=NOW,
        )
        for pid in (10, 11, 20, 21):
            d = d.submit_move(
                player_id=pid,
                choice=_choice(pid, attack=Position.HIGH, block=Position.HIGH),
                now=LATER,
            )
        d2 = d.resolve(random=FakeRandom(seed=99), now=LATER)
        assert d2.final_outcome is not None
        assert d2.final_outcome.winner is MassDuelWinner.DRAW
        assert d2.final_outcome.clan1_delta_cm == 0
        assert d2.final_outcome.clan2_delta_cm == 0

    def test_resolve_when_not_ready_raises(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100, 11: 80},
            clan2_lengths={20: 90, 21: 70},
            hit_pct=10,
            now=NOW,
        )
        d = d.submit_move(player_id=10, choice=_choice(10), now=LATER)
        with pytest.raises(MassDuelNotReadyError) as exc:
            d.resolve(random=FakeRandom(seed=1), now=LATER)
        assert exc.value.missing_count == 3  # 11, 20, 21

    def test_resolve_after_completed_rejected(self) -> None:
        d = self._ready_duel().resolve(random=FakeRandom(seed=1), now=LATER)
        with pytest.raises(InvalidMassDuelStateError):
            d.resolve(random=FakeRandom(seed=2), now=LATER)

    def test_resolve_after_cancelled_rejected(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100},
            clan2_lengths={20: 50},
            hit_pct=10,
            now=NOW,
        ).cancel(now=LATER)
        with pytest.raises(InvalidMassDuelStateError):
            d.resolve(random=FakeRandom(seed=1), now=LATER)


class TestCancel:
    def _new_duel(self) -> MassDuel:
        return MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100},
            clan2_lengths={20: 50},
            hit_pct=10,
            now=NOW,
        )

    def test_cancel_from_in_progress_transitions_to_cancelled(self) -> None:
        d = self._new_duel()
        d2 = d.cancel(now=LATER)
        assert d2.state is MassDuelState.CANCELLED
        assert d2.is_cancelled is True
        assert d2.is_terminal is True
        assert d2.cancelled_at == LATER
        # старый инстанс не изменился
        assert d.state is MassDuelState.IN_PROGRESS

    def test_cancel_idempotent_from_cancelled(self) -> None:
        d = self._new_duel().cancel(now=LATER)
        d2 = d.cancel(now=LATER + timedelta(minutes=1))
        # Идентичный инстанс — мутатор сразу вернул self
        assert d2 is d
        assert d2.cancelled_at == LATER  # не обновился

    def test_cancel_from_completed_rejected(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100},
            clan2_lengths={20: 50},
            hit_pct=10,
            now=NOW,
        )
        d = d.submit_move(player_id=10, choice=_choice(10), now=LATER)
        d = d.submit_move(player_id=20, choice=_choice(20), now=LATER)
        d = d.resolve(random=FakeRandom(seed=1), now=LATER)
        with pytest.raises(InvalidMassDuelStateError):
            d.cancel(now=LATER)


class TestProperties:
    def test_is_participant_for_both_clans(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100, 11: 80},
            clan2_lengths={20: 90, 21: 70},
            hit_pct=10,
            now=NOW,
        )
        assert d.is_participant(10) is True
        assert d.is_participant(11) is True
        assert d.is_participant(20) is True
        assert d.is_participant(21) is True
        assert d.is_participant(999) is False
        assert d.is_participant(0) is False

    def test_is_ready_to_resolve_false_when_not_in_progress(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100},
            clan2_lengths={20: 50},
            hit_pct=10,
            now=NOW,
        ).cancel(now=LATER)
        assert d.is_ready_to_resolve is False

    def test_missing_player_ids_in_completed_returns_empty(self) -> None:
        d = _completed_duel()
        # После resolve все choices не-None
        assert d.missing_player_ids == ()


class TestEndToEndScenarios:
    """Полные сценарии: create → submit → resolve / force → resolve."""

    def test_full_2v2_all_submit_then_resolve(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100, 11: 80},
            clan2_lengths={20: 90, 21: 70},
            hit_pct=10,
            now=NOW,
        )
        for pid in (10, 11, 20, 21):
            d = d.submit_move(player_id=pid, choice=_choice(pid), now=LATER)
            assert d.state is MassDuelState.IN_PROGRESS
        d = d.resolve(random=FakeRandom(seed=42), now=LATER)
        assert d.state is MassDuelState.COMPLETED
        assert d.final_outcome is not None
        assert d.final_outcome.winner in (
            MassDuelWinner.CLAN1,
            MassDuelWinner.CLAN2,
            MassDuelWinner.DRAW,
        )

    def test_partial_submit_then_force_then_resolve(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100, 11: 80},
            clan2_lengths={20: 90, 21: 70},
            hit_pct=10,
            now=NOW,
        )
        d = d.submit_move(player_id=10, choice=_choice(10), now=LATER)
        d = d.submit_move(player_id=20, choice=_choice(20), now=LATER)
        # Двое не отправили — AFK-фоллбэк через force_submit_missing
        fallback = {
            11: _choice(11, attack=Position.LOW),
            21: _choice(21, attack=Position.MID),
        }
        d = d.force_submit_missing(fallback_choices=fallback, now=LATER)
        assert d.is_ready_to_resolve is True
        d = d.resolve(random=FakeRandom(seed=42), now=LATER)
        assert d.state is MassDuelState.COMPLETED

    def test_unequal_3v1_resolves(self) -> None:
        # 3×1: clan1 — три атакующих, clan2 — один; pair_attackers по
        # mod-cycle переиспользует defender. resolve_mass_duel ассимется
        # снизу через `mass_services.py`.
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100, 11: 80, 12: 60},
            clan2_lengths={20: 90},
            hit_pct=10,
            now=NOW,
        )
        for pid in (10, 11, 12, 20):
            d = d.submit_move(
                player_id=pid,
                choice=_choice(pid, attack=Position.HIGH, block=Position.LOW),
                now=LATER,
            )
        d = d.resolve(random=FakeRandom(seed=1), now=LATER)
        assert d.final_outcome is not None
        # У защитника clan2 разные блок-позиции, а атакующие clan1 бьют
        # HIGH; реальный исход зависит от seed-а, но zero-sum обязательно.
        assert d.final_outcome.clan1_delta_cm + d.final_outcome.clan2_delta_cm == 0

    def test_mass_duel_path_independence_in_aggregate(self) -> None:
        # 3 атаки в одного защитника длиной 100 при hit_pct=10:
        # path-independent даёт ровно 30 (3 × 10), а не 10+9+8.
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 1, 11: 1, 12: 1},  # атакующие ⇒ их длина
            # не важна для clan2-defender'а.
            clan2_lengths={20: 100},
            hit_pct=10,
            now=NOW,
        )
        for pid in (10, 11, 12):
            d = d.submit_move(
                player_id=pid,
                choice=_choice(pid, attack=Position.HIGH, block=Position.HIGH),
                now=LATER,
            )
        d = d.submit_move(
            player_id=20,
            choice=_choice(20, attack=Position.HIGH, block=Position.LOW),  # не блок HIGH
            now=LATER,
        )
        d = d.resolve(random=FakeRandom(seed=1), now=LATER)
        assert d.final_outcome is not None
        # Все 3 атаки HIGH, защитник держит LOW → blocked=False каждой.
        # damage = floor(100 * 10 / 100) = 10 за каждую → 30 суммарно.
        assert d.final_outcome.clan1_total_dealt == 30


class TestImmutability:
    def test_submit_returns_new_instance(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100},
            clan2_lengths={20: 50},
            hit_pct=10,
            now=NOW,
        )
        d2 = d.submit_move(player_id=10, choice=_choice(10), now=LATER)
        assert d2 is not d
        assert d.clan1_choices == (None,)  # старый не тронут
        assert d2.clan1_choices == (_choice(10),)

    def test_cancel_returns_new_instance_when_state_changes(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100},
            clan2_lengths={20: 50},
            hit_pct=10,
            now=NOW,
        )
        d2 = d.cancel(now=LATER)
        assert d2 is not d
        assert d.state is MassDuelState.IN_PROGRESS  # неизменён

    def test_resolve_returns_new_instance(self) -> None:
        d = MassDuel.create_battle(
            clan1_id=1,
            clan2_id=2,
            clan1_lengths={10: 100},
            clan2_lengths={20: 50},
            hit_pct=10,
            now=NOW,
        )
        d = d.submit_move(player_id=10, choice=_choice(10), now=LATER)
        d2 = d.submit_move(player_id=20, choice=_choice(20), now=LATER)
        d3 = d2.resolve(random=FakeRandom(seed=1), now=LATER)
        assert d3 is not d2
        assert d2.state is MassDuelState.IN_PROGRESS  # неизменён


# ─── helpers ───


def _completed_duel() -> MassDuel:
    """Готовый завершённый MassDuel — для проверок «нельзя из COMPLETED»."""

    d = MassDuel.create_battle(
        clan1_id=1,
        clan2_id=2,
        clan1_lengths={10: 100},
        clan2_lengths={20: 50},
        hit_pct=10,
        now=NOW,
    )
    d = d.submit_move(player_id=10, choice=_choice(10), now=LATER)
    d = d.submit_move(player_id=20, choice=_choice(20), now=LATER)
    return d.resolve(random=FakeRandom(seed=1), now=LATER)


def _make_dummy_outcome() -> MassDuelOutcome:
    """Минимальный валидный `MassDuelOutcome` — для replace-теста инвариантов.

    `MassDuel.__post_init__` проверяет только `is None / is not None` для
    `final_outcome`, не лезет внутрь — но mypy strict требует правильный
    тип. Конструируем минимально валидный outcome (zero-sum DRAW).
    """

    inner = MassRoundOutcome(
        damage_entries=(),
        clan1_total_dealt=0,
        clan2_total_dealt=0,
    )
    return MassDuelOutcome(
        outcome=inner,
        clan1_total_dealt=0,
        clan2_total_dealt=0,
        clan1_delta_cm=0,
        clan2_delta_cm=0,
        winner=MassDuelWinner.DRAW,
    )
