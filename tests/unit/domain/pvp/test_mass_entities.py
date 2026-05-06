"""Тесты VO массового PvP (Спринт 2.2.B / ГДД §7.2).

Покрытие:

* Конструкторы валидируют входы (`__post_init__` поднимает
  `ValueError` на невалидных значениях).
* Все классы — frozen + slots (нельзя мутировать, нельзя
  добавлять неизвестные атрибуты).
* `MassDuelOutcome` обязан быть zero-sum:
  ``clan1_delta_cm + clan2_delta_cm == 0``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pipirik_wars.domain.pvp import (
    MassDamageEntry,
    MassDuelOutcome,
    MassDuelWinner,
    MassPairing,
    MassRoundChoice,
    MassRoundOutcome,
    Position,
)


class TestMassRoundChoice:
    """Выбор одного участника массового боя."""

    def test_valid(self) -> None:
        choice = MassRoundChoice(
            player_id=42,
            attack=Position.HIGH,
            block=Position.MID,
        )
        assert choice.player_id == 42
        assert choice.attack is Position.HIGH
        assert choice.block is Position.MID

    @pytest.mark.parametrize("player_id", [0, -1, -100])
    def test_player_id_must_be_positive(self, player_id: int) -> None:
        with pytest.raises(ValueError, match="player_id must be > 0"):
            MassRoundChoice(player_id=player_id, attack=Position.HIGH, block=Position.LOW)

    def test_frozen(self) -> None:
        choice = MassRoundChoice(player_id=1, attack=Position.HIGH, block=Position.LOW)
        with pytest.raises(FrozenInstanceError):
            choice.player_id = 2


class TestMassPairing:
    """Назначенная пара «атакующий → защитник»."""

    def test_valid(self) -> None:
        pair = MassPairing(attacker_id=1, defender_id=2)
        assert pair.attacker_id == 1
        assert pair.defender_id == 2

    @pytest.mark.parametrize("attacker_id", [0, -1])
    def test_attacker_id_must_be_positive(self, attacker_id: int) -> None:
        with pytest.raises(ValueError, match="attacker_id must be > 0"):
            MassPairing(attacker_id=attacker_id, defender_id=1)

    @pytest.mark.parametrize("defender_id", [0, -1])
    def test_defender_id_must_be_positive(self, defender_id: int) -> None:
        with pytest.raises(ValueError, match="defender_id must be > 0"):
            MassPairing(attacker_id=1, defender_id=defender_id)

    def test_self_pairing_rejected(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            MassPairing(attacker_id=7, defender_id=7)

    def test_frozen(self) -> None:
        pair = MassPairing(attacker_id=1, defender_id=2)
        with pytest.raises(FrozenInstanceError):
            pair.attacker_id = 5


class TestMassDamageEntry:
    """Один разрешённый удар внутри тика."""

    def test_valid_unblocked(self) -> None:
        entry = MassDamageEntry(
            attacker_id=1,
            defender_id=2,
            attacker_attack=Position.HIGH,
            defender_block=Position.LOW,
            blocked=False,
            damage_cm=10,
        )
        assert entry.blocked is False
        assert entry.damage_cm == 10

    def test_valid_blocked(self) -> None:
        entry = MassDamageEntry(
            attacker_id=1,
            defender_id=2,
            attacker_attack=Position.HIGH,
            defender_block=Position.HIGH,
            blocked=True,
            damage_cm=0,
        )
        assert entry.blocked is True
        assert entry.damage_cm == 0

    def test_self_hit_rejected(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            MassDamageEntry(
                attacker_id=1,
                defender_id=1,
                attacker_attack=Position.HIGH,
                defender_block=Position.LOW,
                blocked=False,
                damage_cm=5,
            )

    def test_negative_damage_rejected(self) -> None:
        with pytest.raises(ValueError, match="damage_cm must be >= 0"):
            MassDamageEntry(
                attacker_id=1,
                defender_id=2,
                attacker_attack=Position.HIGH,
                defender_block=Position.LOW,
                blocked=False,
                damage_cm=-1,
            )

    def test_blocked_must_have_zero_damage(self) -> None:
        with pytest.raises(ValueError, match="blocked hit must have damage_cm == 0"):
            MassDamageEntry(
                attacker_id=1,
                defender_id=2,
                attacker_attack=Position.HIGH,
                defender_block=Position.HIGH,
                blocked=True,
                damage_cm=10,
            )


class TestMassRoundOutcome:
    """Результат одного «тика» массового боя."""

    def test_valid_empty(self) -> None:
        outcome = MassRoundOutcome(
            damage_entries=(),
            clan1_total_dealt=0,
            clan2_total_dealt=0,
        )
        assert outcome.damage_entries == ()

    def test_valid_with_entries(self) -> None:
        e1 = MassDamageEntry(
            attacker_id=1,
            defender_id=2,
            attacker_attack=Position.HIGH,
            defender_block=Position.LOW,
            blocked=False,
            damage_cm=10,
        )
        outcome = MassRoundOutcome(
            damage_entries=(e1,),
            clan1_total_dealt=10,
            clan2_total_dealt=0,
        )
        assert outcome.damage_entries == (e1,)
        assert outcome.clan1_total_dealt == 10

    def test_negative_total_rejected(self) -> None:
        with pytest.raises(ValueError, match="clan1_total_dealt must be >= 0"):
            MassRoundOutcome(damage_entries=(), clan1_total_dealt=-1, clan2_total_dealt=0)
        with pytest.raises(ValueError, match="clan2_total_dealt must be >= 0"):
            MassRoundOutcome(damage_entries=(), clan1_total_dealt=0, clan2_total_dealt=-5)


class TestMassDuelOutcome:
    """Финальный итог массового боя."""

    def _outcome(self, **overrides: object) -> MassDuelOutcome:
        round_outcome = MassRoundOutcome(
            damage_entries=(), clan1_total_dealt=10, clan2_total_dealt=5
        )
        defaults: dict[str, object] = {
            "outcome": round_outcome,
            "clan1_total_dealt": 10,
            "clan2_total_dealt": 5,
            "clan1_delta_cm": 5,
            "clan2_delta_cm": -5,
            "winner": MassDuelWinner.CLAN1,
        }
        defaults.update(overrides)
        return MassDuelOutcome(**defaults)  # type: ignore[arg-type]

    def test_valid_clan1_wins(self) -> None:
        outcome = self._outcome()
        assert outcome.winner is MassDuelWinner.CLAN1
        assert outcome.clan1_delta_cm + outcome.clan2_delta_cm == 0

    def test_valid_draw(self) -> None:
        outcome = self._outcome(
            clan1_total_dealt=7,
            clan2_total_dealt=7,
            clan1_delta_cm=0,
            clan2_delta_cm=0,
            winner=MassDuelWinner.DRAW,
        )
        assert outcome.winner is MassDuelWinner.DRAW

    def test_zero_sum_invariant(self) -> None:
        with pytest.raises(ValueError, match="zero-sum"):
            self._outcome(clan1_delta_cm=10, clan2_delta_cm=-5)

    def test_negative_total_rejected(self) -> None:
        with pytest.raises(ValueError, match="clan1_total_dealt must be >= 0"):
            self._outcome(clan1_total_dealt=-1)
