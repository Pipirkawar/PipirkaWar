"""Тесты доменных ошибок `domain/bosses/errors.py` (Спринт 3.3-A)."""

from __future__ import annotations

from pipirik_wars.domain.bosses import (
    AlreadyInBossFightError,
    BossError,
    BossFightLobbyClosedError,
    BossFightNotFoundError,
    BossFightRequirementError,
    BossPlayerPoolEmptyError,
    BossSummonOnGlobalCooldownError,
    InvalidBossFightStateError,
    NotInBossFightError,
)
from pipirik_wars.shared.errors import DomainError


class TestErrorHierarchy:
    def test_boss_error_is_domain_error(self) -> None:
        err = BossError("base")
        assert isinstance(err, DomainError)

    def test_all_subclasses_inherit_from_boss_error(self) -> None:
        for cls in (
            AlreadyInBossFightError,
            BossFightLobbyClosedError,
            BossFightNotFoundError,
            BossFightRequirementError,
            BossPlayerPoolEmptyError,
            BossSummonOnGlobalCooldownError,
            InvalidBossFightStateError,
            NotInBossFightError,
        ):
            assert issubclass(cls, BossError)


class TestErrorPayloads:
    def test_boss_fight_not_found_carries_id(self) -> None:
        err = BossFightNotFoundError(boss_fight_id=42)
        assert err.boss_fight_id == 42
        assert "42" in str(err)

    def test_summon_global_cooldown_carries_remaining(self) -> None:
        err = BossSummonOnGlobalCooldownError(actual_remaining_seconds=3600)
        assert err.actual_remaining_seconds == 3600
        assert "3600" in str(err)

    def test_already_in_boss_fight_carries_player(self) -> None:
        err = AlreadyInBossFightError(player_id=99)
        assert err.player_id == 99
        assert "99" in str(err)

    def test_requirement_carries_all_fields(self) -> None:
        err = BossFightRequirementError(
            player_id=42,
            requirement="thickness",
            required=9,
            actual=5,
        )
        assert err.player_id == 42
        assert err.requirement == "thickness"
        assert err.required == 9
        assert err.actual == 5
        assert "thickness" in str(err)
        assert "9" in str(err)
        assert "5" in str(err)

    def test_lobby_closed_carries_status(self) -> None:
        err = BossFightLobbyClosedError(boss_fight_id=1, status="in_battle")
        assert err.boss_fight_id == 1
        assert err.status == "in_battle"
        assert "in_battle" in str(err)

    def test_not_in_boss_fight_carries_ids(self) -> None:
        err = NotInBossFightError(boss_fight_id=1, player_id=42)
        assert err.boss_fight_id == 1
        assert err.player_id == 42
        assert "1" in str(err)
        assert "42" in str(err)

    def test_pool_empty_carries_size(self) -> None:
        err = BossPlayerPoolEmptyError(pool_size=30)
        assert err.pool_size == 30
        assert "30" in str(err)

    def test_invalid_state_carries_expected_actual(self) -> None:
        err = InvalidBossFightStateError(boss_fight_id=1, expected="lobby", actual="in_battle")
        assert err.boss_fight_id == 1
        assert err.expected == "lobby"
        assert err.actual == "in_battle"
        assert "lobby" in str(err)
        assert "in_battle" in str(err)
