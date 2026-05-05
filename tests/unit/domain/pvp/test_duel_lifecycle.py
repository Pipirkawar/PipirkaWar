"""Тесты жизненного цикла агрегата `Duel` — создание, accept, cancel.

Покрытие:

* **`create_challenge`** — конструктор pending-вызова: валидные/невалидные
  параметры (self-challenge, отрицательные `expected_rounds`/`hit_pct`,
  несоответствие `mode` ↔ `challenged_id`).
* **`accept`** — переход PENDING_ACCEPT → IN_PROGRESS, снапшот длин,
  валидация участника (`NotADuelParticipantError`), отрицательная длина
  (`InvalidLengthError`), повторный accept (`InvalidDuelStateError`).
* **`cancel`** — переход PENDING_ACCEPT → CANCELLED, идемпотентность
  на CANCELLED, отказ из IN_PROGRESS / COMPLETED.
* **Свойства** — `is_pending` / `is_in_progress` / `is_completed` /
  `is_cancelled` / `is_terminal` / `is_participant`.
* **Иммутабельность** — `Duel` frozen, попытка мутации ⇒ `FrozenInstanceError`.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelState,
    InvalidDuelStateError,
    InvalidLengthError,
    NotADuelParticipantError,
    SelfChallengeError,
)

_NOW = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
_LATER = _NOW + timedelta(minutes=1)
_MUCH_LATER = _NOW + timedelta(hours=1)


def _challenge(
    *,
    challenger_id: int = 1,
    challenged_id: int | None = 2,
    mode: DuelMode = DuelMode.CHAT_ONLY,
    hit_pct: int = 10,
    expected_rounds: int = 3,
    now: datetime = _NOW,
) -> Duel:
    return Duel.create_challenge(
        challenger_id=challenger_id,
        challenged_id=challenged_id,
        mode=mode,
        hit_pct=hit_pct,
        expected_rounds=expected_rounds,
        now=now,
    )


class TestCreateChallenge:
    def test_minimal_chat_challenge(self) -> None:
        d = _challenge()
        assert d.id is None
        assert d.challenger_id == 1
        assert d.challenged_id == 2
        assert d.mode is DuelMode.CHAT_ONLY
        assert d.state is DuelState.PENDING_ACCEPT
        assert d.hit_pct == 10
        assert d.expected_rounds == 3
        assert d.created_at == _NOW
        assert d.accepted_at is None
        assert d.completed_at is None
        assert d.cancelled_at is None
        assert d.p1_initial_length_cm is None
        assert d.p2_initial_length_cm is None
        assert d.completed_rounds == ()
        assert d.pending_round is None
        assert d.final_outcome is None

    def test_chat_then_global_with_challenged_id(self) -> None:
        d = _challenge(mode=DuelMode.CHAT_THEN_GLOBAL)
        assert d.mode is DuelMode.CHAT_THEN_GLOBAL
        assert d.challenged_id == 2

    def test_global_only_without_challenged_id(self) -> None:
        d = _challenge(mode=DuelMode.GLOBAL_ONLY, challenged_id=None)
        assert d.mode is DuelMode.GLOBAL_ONLY
        assert d.challenged_id is None

    def test_global_only_must_not_have_challenged_id(self) -> None:
        with pytest.raises(ValueError, match="GLOBAL_ONLY"):
            _challenge(mode=DuelMode.GLOBAL_ONLY, challenged_id=2)

    def test_chat_only_requires_challenged_id(self) -> None:
        with pytest.raises(ValueError, match="chat_only"):
            _challenge(mode=DuelMode.CHAT_ONLY, challenged_id=None)

    def test_chat_then_global_requires_challenged_id(self) -> None:
        with pytest.raises(ValueError, match="chat_then_global"):
            _challenge(mode=DuelMode.CHAT_THEN_GLOBAL, challenged_id=None)

    def test_self_challenge_forbidden(self) -> None:
        with pytest.raises(SelfChallengeError) as exc:
            _challenge(challenger_id=42, challenged_id=42)
        assert exc.value.player_id == 42

    def test_self_challenge_forbidden_in_chat_then_global(self) -> None:
        with pytest.raises(SelfChallengeError):
            _challenge(
                mode=DuelMode.CHAT_THEN_GLOBAL,
                challenger_id=99,
                challenged_id=99,
            )

    def test_global_only_self_challenge_not_possible(self) -> None:
        # GLOBAL_ONLY: challenged_id=None при создании ⇒ self-challenge
        # перехватывается только в accept-е.
        d = _challenge(mode=DuelMode.GLOBAL_ONLY, challenged_id=None)
        assert d.state is DuelState.PENDING_ACCEPT

    @pytest.mark.parametrize("rounds", [0, -1, -100])
    def test_invalid_expected_rounds(self, rounds: int) -> None:
        with pytest.raises(ValueError, match="expected_rounds"):
            _challenge(expected_rounds=rounds)

    @pytest.mark.parametrize("hit_pct", [-1, 101, 200, -50])
    def test_invalid_hit_pct(self, hit_pct: int) -> None:
        with pytest.raises(ValueError, match="hit_pct"):
            _challenge(hit_pct=hit_pct)

    @pytest.mark.parametrize("hit_pct", [0, 1, 50, 100])
    def test_valid_hit_pct_boundaries(self, hit_pct: int) -> None:
        d = _challenge(hit_pct=hit_pct)
        assert d.hit_pct == hit_pct

    @pytest.mark.parametrize("rounds", [1, 3, 5, 10])
    def test_valid_expected_rounds(self, rounds: int) -> None:
        d = _challenge(expected_rounds=rounds)
        assert d.expected_rounds == rounds


class TestAccept:
    def test_accept_chat_duel(self) -> None:
        d = _challenge(challenger_id=1, challenged_id=2)
        d2 = d.accept(accepter_id=2, p1_length_cm=100, p2_length_cm=80, now=_LATER)
        assert d2.state is DuelState.IN_PROGRESS
        assert d2.accepted_at == _LATER
        assert d2.p1_initial_length_cm == 100
        assert d2.p2_initial_length_cm == 80
        assert d2.pending_round is not None
        assert d2.pending_round.round_num == 1
        assert d2.pending_round.p1_choice is None
        assert d2.pending_round.p2_choice is None
        assert d2.completed_rounds == ()
        assert d2.final_outcome is None

    def test_accept_global_duel_sets_challenged_id(self) -> None:
        d = _challenge(mode=DuelMode.GLOBAL_ONLY, challenged_id=None, challenger_id=1)
        d2 = d.accept(accepter_id=99, p1_length_cm=50, p2_length_cm=50, now=_LATER)
        assert d2.challenged_id == 99
        assert d2.state is DuelState.IN_PROGRESS

    def test_accept_global_duel_self_challenge_blocked(self) -> None:
        d = _challenge(mode=DuelMode.GLOBAL_ONLY, challenged_id=None, challenger_id=42)
        with pytest.raises(NotADuelParticipantError) as exc:
            d.accept(accepter_id=42, p1_length_cm=100, p2_length_cm=100, now=_LATER)
        assert exc.value.player_id == 42

    def test_accept_by_non_invited_player(self) -> None:
        d = _challenge(challenger_id=1, challenged_id=2)
        with pytest.raises(NotADuelParticipantError) as exc:
            d.accept(accepter_id=3, p1_length_cm=100, p2_length_cm=80, now=_LATER)
        assert exc.value.player_id == 3

    def test_accept_by_challenger_blocked(self) -> None:
        d = _challenge(challenger_id=1, challenged_id=2)
        with pytest.raises(NotADuelParticipantError):
            d.accept(accepter_id=1, p1_length_cm=100, p2_length_cm=80, now=_LATER)

    def test_accept_negative_p1_length(self) -> None:
        d = _challenge()
        with pytest.raises(InvalidLengthError) as exc:
            d.accept(accepter_id=2, p1_length_cm=-1, p2_length_cm=80, now=_LATER)
        assert exc.value.side == "p1"

    def test_accept_negative_p2_length(self) -> None:
        d = _challenge()
        with pytest.raises(InvalidLengthError) as exc:
            d.accept(accepter_id=2, p1_length_cm=100, p2_length_cm=-1, now=_LATER)
        assert exc.value.side == "p2"

    def test_accept_zero_lengths_allowed(self) -> None:
        d = _challenge()
        d2 = d.accept(accepter_id=2, p1_length_cm=0, p2_length_cm=0, now=_LATER)
        assert d2.p1_initial_length_cm == 0
        assert d2.p2_initial_length_cm == 0

    def test_double_accept_blocked(self) -> None:
        d = _challenge()
        d2 = d.accept(accepter_id=2, p1_length_cm=100, p2_length_cm=80, now=_LATER)
        with pytest.raises(InvalidDuelStateError) as exc:
            d2.accept(
                accepter_id=2,
                p1_length_cm=100,
                p2_length_cm=80,
                now=_MUCH_LATER,
            )
        assert exc.value.op == "accept"
        assert exc.value.actual is DuelState.IN_PROGRESS
        assert exc.value.expected is DuelState.PENDING_ACCEPT

    def test_accept_after_cancel_blocked(self) -> None:
        d = _challenge()
        cancelled = d.cancel(now=_LATER)
        with pytest.raises(InvalidDuelStateError):
            cancelled.accept(
                accepter_id=2,
                p1_length_cm=100,
                p2_length_cm=80,
                now=_MUCH_LATER,
            )


class TestCancel:
    def test_cancel_pending(self) -> None:
        d = _challenge()
        d2 = d.cancel(now=_LATER)
        assert d2.state is DuelState.CANCELLED
        assert d2.cancelled_at == _LATER

    def test_cancel_idempotent_on_cancelled(self) -> None:
        d = _challenge()
        d2 = d.cancel(now=_LATER)
        d3 = d2.cancel(now=_MUCH_LATER)
        # Идемпотентен — то же самое состояние, cancelled_at не сдвигается
        assert d3.state is DuelState.CANCELLED
        assert d3.cancelled_at == _LATER  # не _MUCH_LATER
        assert d3 is d2

    def test_cancel_blocked_in_progress(self) -> None:
        d = _challenge().accept(accepter_id=2, p1_length_cm=100, p2_length_cm=80, now=_LATER)
        with pytest.raises(InvalidDuelStateError) as exc:
            d.cancel(now=_MUCH_LATER)
        assert exc.value.op == "cancel"
        assert exc.value.actual is DuelState.IN_PROGRESS


class TestProperties:
    def test_is_pending(self) -> None:
        d = _challenge()
        assert d.is_pending is True
        assert d.is_in_progress is False
        assert d.is_completed is False
        assert d.is_cancelled is False
        assert d.is_terminal is False

    def test_is_in_progress(self) -> None:
        d = _challenge().accept(accepter_id=2, p1_length_cm=100, p2_length_cm=80, now=_LATER)
        assert d.is_pending is False
        assert d.is_in_progress is True
        assert d.is_completed is False
        assert d.is_cancelled is False
        assert d.is_terminal is False

    def test_is_cancelled(self) -> None:
        d = _challenge().cancel(now=_LATER)
        assert d.is_cancelled is True
        assert d.is_terminal is True

    def test_is_participant_chat(self) -> None:
        d = _challenge(challenger_id=1, challenged_id=2)
        assert d.is_participant(1) is True
        assert d.is_participant(2) is True
        assert d.is_participant(3) is False

    def test_is_participant_global_pending(self) -> None:
        d = _challenge(mode=DuelMode.GLOBAL_ONLY, challenged_id=None, challenger_id=1)
        assert d.is_participant(1) is True
        assert d.is_participant(99) is False

    def test_is_participant_global_after_accept(self) -> None:
        d = _challenge(mode=DuelMode.GLOBAL_ONLY, challenged_id=None, challenger_id=1).accept(
            accepter_id=99, p1_length_cm=100, p2_length_cm=100, now=_LATER
        )
        assert d.is_participant(1) is True
        assert d.is_participant(99) is True
        assert d.is_participant(50) is False


class TestImmutability:
    def test_duel_is_frozen(self) -> None:
        d = _challenge()
        with pytest.raises(FrozenInstanceError):
            d.state = DuelState.IN_PROGRESS

    def test_accept_returns_new_instance(self) -> None:
        d = _challenge()
        d2 = d.accept(accepter_id=2, p1_length_cm=100, p2_length_cm=80, now=_LATER)
        assert d is not d2
        assert d.state is DuelState.PENDING_ACCEPT  # original unchanged
        assert d2.state is DuelState.IN_PROGRESS

    def test_cancel_returns_new_instance(self) -> None:
        d = _challenge()
        d2 = d.cancel(now=_LATER)
        assert d is not d2
        assert d.state is DuelState.PENDING_ACCEPT
        assert d2.state is DuelState.CANCELLED
