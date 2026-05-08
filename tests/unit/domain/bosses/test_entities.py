"""Тесты `BossFight` и `BossParticipant` (Спринт 3.3-A)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightStatus,
    BossKind,
    BossParticipant,
)


def _now() -> datetime:
    return datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _times() -> tuple[datetime, datetime]:
    started = _now()
    lobby = started + timedelta(minutes=20)
    return started, lobby


class TestBossFightStarting:
    def test_creates_lobby_fight_with_id_none(self) -> None:
        started, lobby = _times()
        fight = BossFight.starting(
            kind=BossKind.RAID,
            summoner_player_id=42,
            boss_player_id=99,
            started_at=started,
            lobby_ends_at=lobby,
            random_seed=123456,
            initial_boss_length_cm=400,
        )
        assert fight.id is None
        assert fight.kind is BossKind.RAID
        assert fight.summoner_player_id == 42
        assert fight.boss_player_id == 99
        assert fight.status is BossFightStatus.LOBBY
        assert fight.is_in_lobby is True
        assert fight.is_in_battle is False
        assert fight.is_terminal is False
        assert fight.started_at == started
        assert fight.lobby_ends_at == lobby
        assert fight.random_seed == 123456
        assert fight.initial_boss_length_cm == 400
        assert fight.current_boss_length_cm == 400
        assert fight.current_round == 0
        assert fight.finished_at is None

    def test_summoner_must_differ_from_boss(self) -> None:
        started, lobby = _times()
        with pytest.raises(ValueError, match="must differ"):
            BossFight.starting(
                kind=BossKind.RAID,
                summoner_player_id=42,
                boss_player_id=42,
                started_at=started,
                lobby_ends_at=lobby,
                random_seed=0,
                initial_boss_length_cm=400,
            )

    def test_lobby_ends_at_must_be_after_started_at(self) -> None:
        started, _ = _times()
        with pytest.raises(ValueError, match="lobby_ends_at"):
            BossFight.starting(
                kind=BossKind.RAID,
                summoner_player_id=42,
                boss_player_id=99,
                started_at=started,
                lobby_ends_at=started,  # equals
                random_seed=0,
                initial_boss_length_cm=400,
            )

    def test_initial_boss_length_must_be_positive(self) -> None:
        started, lobby = _times()
        with pytest.raises(ValueError, match="initial_boss_length_cm"):
            BossFight.starting(
                kind=BossKind.RAID,
                summoner_player_id=42,
                boss_player_id=99,
                started_at=started,
                lobby_ends_at=lobby,
                random_seed=0,
                initial_boss_length_cm=0,
            )


class TestBossFightTransitions:
    def _fresh(self) -> BossFight:
        started, lobby = _times()
        return BossFight.starting(
            kind=BossKind.RAID,
            summoner_player_id=42,
            boss_player_id=99,
            started_at=started,
            lobby_ends_at=lobby,
            random_seed=0,
            initial_boss_length_cm=400,
        )

    def test_mark_in_battle_from_lobby(self) -> None:
        f = self._fresh()
        nxt = f.mark_in_battle()
        assert nxt.status is BossFightStatus.IN_BATTLE
        assert nxt.is_in_battle is True
        # Original is unchanged.
        assert f.status is BossFightStatus.LOBBY

    def test_mark_in_battle_idempotent(self) -> None:
        f = self._fresh().mark_in_battle()
        again = f.mark_in_battle()
        assert again is f

    def test_mark_in_battle_from_finished_raises(self) -> None:
        f = self._fresh().mark_in_battle().mark_finished(finished_at=_now() + timedelta(hours=1))
        with pytest.raises(ValueError, match="terminal"):
            f.mark_in_battle()

    def test_mark_in_battle_from_cancelled_raises(self) -> None:
        f = self._fresh().mark_cancelled(cancelled_at=_now() + timedelta(minutes=5))
        with pytest.raises(ValueError, match="terminal"):
            f.mark_in_battle()

    def test_mark_finished_from_in_battle(self) -> None:
        finished_at = _now() + timedelta(hours=1)
        f = self._fresh().mark_in_battle().mark_finished(finished_at=finished_at)
        assert f.status is BossFightStatus.FINISHED
        assert f.is_terminal is True
        assert f.finished_at == finished_at

    def test_mark_finished_idempotent(self) -> None:
        f = self._fresh().mark_in_battle().mark_finished(finished_at=_now() + timedelta(hours=1))
        again = f.mark_finished(finished_at=_now() + timedelta(hours=2))
        assert again is f

    def test_mark_finished_from_lobby_raises(self) -> None:
        f = self._fresh()
        with pytest.raises(ValueError, match="must be IN_BATTLE"):
            f.mark_finished(finished_at=_now())

    def test_mark_finished_from_cancelled_raises(self) -> None:
        f = self._fresh().mark_cancelled(cancelled_at=_now() + timedelta(minutes=5))
        with pytest.raises(ValueError, match="must be IN_BATTLE"):
            f.mark_finished(finished_at=_now() + timedelta(hours=1))

    def test_mark_cancelled_from_lobby(self) -> None:
        cancelled_at = _now() + timedelta(minutes=5)
        f = self._fresh().mark_cancelled(cancelled_at=cancelled_at)
        assert f.status is BossFightStatus.CANCELLED
        assert f.is_terminal is True
        assert f.finished_at == cancelled_at

    def test_mark_cancelled_from_in_battle_allowed(self) -> None:
        cancelled_at = _now() + timedelta(hours=1)
        f = self._fresh().mark_in_battle().mark_cancelled(cancelled_at=cancelled_at)
        assert f.status is BossFightStatus.CANCELLED

    def test_mark_cancelled_idempotent(self) -> None:
        f = self._fresh().mark_cancelled(cancelled_at=_now() + timedelta(minutes=5))
        again = f.mark_cancelled(cancelled_at=_now() + timedelta(minutes=10))
        assert again is f

    def test_mark_cancelled_from_finished_raises(self) -> None:
        f = self._fresh().mark_in_battle().mark_finished(finished_at=_now() + timedelta(hours=1))
        with pytest.raises(ValueError, match="already FINISHED"):
            f.mark_cancelled(cancelled_at=_now() + timedelta(hours=2))


class TestBossFightHpAndRound:
    def _fresh(self) -> BossFight:
        started, lobby = _times()
        return BossFight.starting(
            kind=BossKind.RAID,
            summoner_player_id=42,
            boss_player_id=99,
            started_at=started,
            lobby_ends_at=lobby,
            random_seed=0,
            initial_boss_length_cm=400,
        )

    def test_with_boss_length_updates_only_current(self) -> None:
        f = self._fresh().with_boss_length(length_cm=380)
        assert f.current_boss_length_cm == 380
        assert f.initial_boss_length_cm == 400  # snapshot intact

    def test_with_boss_length_zero_allowed(self) -> None:
        f = self._fresh().with_boss_length(length_cm=0)
        assert f.current_boss_length_cm == 0

    def test_with_boss_length_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            self._fresh().with_boss_length(length_cm=-1)

    def test_with_round_advanced(self) -> None:
        f = self._fresh()
        nxt = f.with_round_advanced()
        assert nxt.current_round == 1
        assert f.current_round == 0  # immutable original

    def test_round_advances_multiple_times(self) -> None:
        f = self._fresh().with_round_advanced().with_round_advanced().with_round_advanced()
        assert f.current_round == 3


class TestBossParticipant:
    def test_raider_factory(self) -> None:
        joined = _now()
        p = BossParticipant.raider(
            boss_fight_id=1,
            player_id=42,
            is_summoner=False,
            length_at_join_cm=50,
            joined_at=joined,
        )
        assert p.boss_fight_id == 1
        assert p.player_id == 42
        assert p.is_summoner is False
        assert p.length_at_join_cm == 50
        assert p.joined_at == joined

    def test_summoner_factory(self) -> None:
        p = BossParticipant.raider(
            boss_fight_id=1,
            player_id=42,
            is_summoner=True,
            length_at_join_cm=120,
            joined_at=_now(),
        )
        assert p.is_summoner is True

    def test_invariant_length_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            BossParticipant(
                boss_fight_id=1,
                player_id=42,
                is_summoner=False,
                length_at_join_cm=0,
                joined_at=_now(),
            )

    def test_frozen(self) -> None:
        p = BossParticipant.raider(
            boss_fight_id=1,
            player_id=42,
            is_summoner=False,
            length_at_join_cm=50,
            joined_at=_now(),
        )
        with pytest.raises(AttributeError):
            p.length_at_join_cm = 60
