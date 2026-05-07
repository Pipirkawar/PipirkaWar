"""Тесты `Caravan` и `CaravanParticipant` (Спринт 3.2-A)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanContribution,
    CaravanParticipant,
    CaravanRole,
    CaravanStatus,
)


def _now() -> datetime:
    return datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)


def _times() -> tuple[datetime, datetime, datetime]:
    started = _now()
    lobby = started + timedelta(minutes=20)
    battle = lobby + timedelta(minutes=60)
    return started, lobby, battle


class TestCaravanStarting:
    def test_creates_lobby_caravan_with_id_none(self) -> None:
        started, lobby, battle = _times()
        caravan = Caravan.starting(
            sender_clan_id=10,
            receiver_clan_id=20,
            leader_player_id=42,
            started_at=started,
            lobby_ends_at=lobby,
            battle_ends_at=battle,
            random_seed=123456,
        )
        assert caravan.id is None
        assert caravan.sender_clan_id == 10
        assert caravan.receiver_clan_id == 20
        assert caravan.leader_player_id == 42
        assert caravan.status is CaravanStatus.LOBBY
        assert caravan.is_in_lobby is True
        assert caravan.is_in_battle is False
        assert caravan.is_terminal is False
        assert caravan.started_at == started
        assert caravan.lobby_ends_at == lobby
        assert caravan.battle_ends_at == battle
        assert caravan.random_seed == 123456
        assert caravan.finished_at is None

    def test_sender_must_differ_from_receiver(self) -> None:
        started, lobby, battle = _times()
        with pytest.raises(ValueError, match="must differ"):
            Caravan.starting(
                sender_clan_id=10,
                receiver_clan_id=10,
                leader_player_id=42,
                started_at=started,
                lobby_ends_at=lobby,
                battle_ends_at=battle,
                random_seed=0,
            )

    def test_lobby_ends_at_must_be_after_started_at(self) -> None:
        started, _lobby, battle = _times()
        with pytest.raises(ValueError, match="lobby_ends_at"):
            Caravan.starting(
                sender_clan_id=10,
                receiver_clan_id=20,
                leader_player_id=42,
                started_at=started,
                lobby_ends_at=started,  # equals
                battle_ends_at=battle,
                random_seed=0,
            )

    def test_battle_ends_at_must_be_after_lobby_ends_at(self) -> None:
        started, lobby, _battle = _times()
        with pytest.raises(ValueError, match="battle_ends_at"):
            Caravan.starting(
                sender_clan_id=10,
                receiver_clan_id=20,
                leader_player_id=42,
                started_at=started,
                lobby_ends_at=lobby,
                battle_ends_at=lobby,  # equals
                random_seed=0,
            )


class TestCaravanTransitions:
    def _fresh(self) -> Caravan:
        started, lobby, battle = _times()
        return Caravan.starting(
            sender_clan_id=10,
            receiver_clan_id=20,
            leader_player_id=42,
            started_at=started,
            lobby_ends_at=lobby,
            battle_ends_at=battle,
            random_seed=0,
        )

    def test_mark_in_battle_from_lobby(self) -> None:
        c = self._fresh()
        next_c = c.mark_in_battle()
        assert next_c.status is CaravanStatus.IN_BATTLE
        assert next_c.is_in_battle is True
        # Original is unchanged.
        assert c.status is CaravanStatus.LOBBY

    def test_mark_in_battle_idempotent(self) -> None:
        c = self._fresh().mark_in_battle()
        again = c.mark_in_battle()
        assert again is c

    def test_mark_in_battle_from_finished_raises(self) -> None:
        c = self._fresh().mark_in_battle().mark_finished(finished_at=_now() + timedelta(hours=2))
        with pytest.raises(ValueError, match="terminal"):
            c.mark_in_battle()

    def test_mark_in_battle_from_cancelled_raises(self) -> None:
        c = self._fresh().mark_cancelled(cancelled_at=_now() + timedelta(minutes=5))
        with pytest.raises(ValueError, match="terminal"):
            c.mark_in_battle()

    def test_mark_finished_from_in_battle(self) -> None:
        finished_at = _now() + timedelta(hours=2)
        c = self._fresh().mark_in_battle().mark_finished(finished_at=finished_at)
        assert c.status is CaravanStatus.FINISHED
        assert c.is_terminal is True
        assert c.finished_at == finished_at

    def test_mark_finished_idempotent(self) -> None:
        c = self._fresh().mark_in_battle().mark_finished(finished_at=_now() + timedelta(hours=2))
        again = c.mark_finished(finished_at=_now() + timedelta(hours=3))
        assert again is c

    def test_mark_finished_from_lobby_raises(self) -> None:
        c = self._fresh()
        with pytest.raises(ValueError, match="must be IN_BATTLE"):
            c.mark_finished(finished_at=_now())

    def test_mark_finished_from_cancelled_raises(self) -> None:
        c = self._fresh().mark_cancelled(cancelled_at=_now() + timedelta(minutes=5))
        with pytest.raises(ValueError, match="must be IN_BATTLE"):
            c.mark_finished(finished_at=_now() + timedelta(hours=2))

    def test_mark_cancelled_from_lobby(self) -> None:
        cancelled_at = _now() + timedelta(minutes=5)
        c = self._fresh().mark_cancelled(cancelled_at=cancelled_at)
        assert c.status is CaravanStatus.CANCELLED
        assert c.is_terminal is True
        assert c.finished_at == cancelled_at

    def test_mark_cancelled_from_in_battle_allowed(self) -> None:
        cancelled_at = _now() + timedelta(hours=1)
        c = self._fresh().mark_in_battle().mark_cancelled(cancelled_at=cancelled_at)
        assert c.status is CaravanStatus.CANCELLED

    def test_mark_cancelled_idempotent(self) -> None:
        c = self._fresh().mark_cancelled(cancelled_at=_now() + timedelta(minutes=5))
        again = c.mark_cancelled(cancelled_at=_now() + timedelta(minutes=10))
        assert again is c

    def test_mark_cancelled_from_finished_raises(self) -> None:
        c = self._fresh().mark_in_battle().mark_finished(finished_at=_now() + timedelta(hours=2))
        with pytest.raises(ValueError, match="already FINISHED"):
            c.mark_cancelled(cancelled_at=_now() + timedelta(hours=3))


class TestCaravanParticipant:
    def test_caravaneer_factory(self) -> None:
        joined = _now()
        p = CaravanParticipant.caravaneer(
            caravan_id=1,
            player_id=42,
            contribution=CaravanContribution(cm=15),
            is_leader=False,
            joined_at=joined,
        )
        assert p.caravan_id == 1
        assert p.player_id == 42
        assert p.role is CaravanRole.CARAVANEER
        assert p.is_leader is False
        assert p.contribution == CaravanContribution(cm=15)
        assert p.joined_at == joined

    def test_leader_factory(self) -> None:
        p = CaravanParticipant.caravaneer(
            caravan_id=1,
            player_id=42,
            contribution=CaravanContribution(cm=20),
            is_leader=True,
            joined_at=_now(),
        )
        assert p.role is CaravanRole.CARAVANEER
        assert p.is_leader is True

    def test_defender_factory(self) -> None:
        p = CaravanParticipant.defender(caravan_id=1, player_id=43, joined_at=_now())
        assert p.role is CaravanRole.DEFENDER
        assert p.is_leader is False
        assert p.contribution is None

    def test_raider_factory(self) -> None:
        p = CaravanParticipant.raider(caravan_id=1, player_id=44, joined_at=_now())
        assert p.role is CaravanRole.RAIDER
        assert p.is_leader is False
        assert p.contribution is None

    def test_invariant_leader_must_be_caravaneer(self) -> None:
        with pytest.raises(ValueError, match="leader must have role"):
            CaravanParticipant(
                caravan_id=1,
                player_id=42,
                role=CaravanRole.DEFENDER,
                is_leader=True,
                contribution=None,
                joined_at=_now(),
            )

    def test_invariant_caravaneer_requires_contribution(self) -> None:
        with pytest.raises(ValueError, match="must have contribution"):
            CaravanParticipant(
                caravan_id=1,
                player_id=42,
                role=CaravanRole.CARAVANEER,
                is_leader=False,
                contribution=None,
                joined_at=_now(),
            )

    def test_invariant_defender_must_not_have_contribution(self) -> None:
        with pytest.raises(ValueError, match="must NOT have contribution"):
            CaravanParticipant(
                caravan_id=1,
                player_id=42,
                role=CaravanRole.DEFENDER,
                is_leader=False,
                contribution=CaravanContribution(cm=10),
                joined_at=_now(),
            )

    def test_invariant_raider_must_not_have_contribution(self) -> None:
        with pytest.raises(ValueError, match="must NOT have contribution"):
            CaravanParticipant(
                caravan_id=1,
                player_id=42,
                role=CaravanRole.RAIDER,
                is_leader=False,
                contribution=CaravanContribution(cm=10),
                joined_at=_now(),
            )
