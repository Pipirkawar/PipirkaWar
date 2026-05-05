"""Юнит-тесты `progression.thickness` (Спринт 1.4.A, ГДД §3.2 / §3.3).

Acceptance из `development_plan.md` 1.4.1 — «юнит-тесты на стоимости 2/10/15/16/20»
для формулы `n²·base` (по умолчанию `base=1000`):

    cost(1→2)  = 2²·1000 = 4 000
    cost(9→10) = 10²·1000 = 100 000
    cost(14→15) = 15²·1000 = 225 000
    cost(15→16) = 16²·1000 = 256 000
    cost(19→20) = 20²·1000 = 400 000

Acceptance из `development_plan.md` 1.4.3 — «юнит-тесты для каждого уровня
(1/2/3/4/5/6/7/9)» по дефолтной таблице ГДД §3.3.
"""

from __future__ import annotations

import pytest

from pipirik_wars.domain.progression import (
    ActivityLockedError,
    cost_for_upgrade,
    is_activity_unlocked,
    require_unlocked,
)

# ---- 1.4.1 — формула стоимости толщины ----


class TestCostForUpgrade:
    @pytest.mark.parametrize(
        ("current", "expected"),
        [
            (1, 4_000),  # → 2
            (9, 100_000),  # → 10
            (14, 225_000),  # → 15
            (15, 256_000),  # → 16
            (19, 400_000),  # → 20
        ],
    )
    def test_default_base_and_exponent_match_gdd(self, current: int, expected: int) -> None:
        # ГДД §3.2: cost_base=1000, cost_exponent=2.
        assert (
            cost_for_upgrade(current_thickness=current, cost_base=1000, cost_exponent=2) == expected
        )

    def test_other_base_and_exponent_combinations(self) -> None:
        # Формула универсальная: проверяем, что параметры реально применяются.
        # cost(1→2) при base=500, exp=3 = 500 * 2³ = 4_000.
        assert cost_for_upgrade(current_thickness=1, cost_base=500, cost_exponent=3) == 4_000
        # cost(2→3) при base=200, exp=2 = 200 * 3² = 1_800.
        assert cost_for_upgrade(current_thickness=2, cost_base=200, cost_exponent=2) == 1_800

    def test_strictly_increasing_in_current_thickness(self) -> None:
        prev = 0
        for n in range(1, 25):
            cur = cost_for_upgrade(current_thickness=n, cost_base=1000, cost_exponent=2)
            assert cur > prev
            prev = cur

    def test_rejects_invalid_current_thickness(self) -> None:
        with pytest.raises(ValueError, match="current_thickness must be >= 1"):
            cost_for_upgrade(current_thickness=0, cost_base=1000, cost_exponent=2)
        with pytest.raises(ValueError, match="current_thickness must be >= 1"):
            cost_for_upgrade(current_thickness=-3, cost_base=1000, cost_exponent=2)

    def test_rejects_invalid_cost_base(self) -> None:
        with pytest.raises(ValueError, match="cost_base must be > 0"):
            cost_for_upgrade(current_thickness=1, cost_base=0, cost_exponent=2)

    def test_rejects_invalid_cost_exponent(self) -> None:
        with pytest.raises(ValueError, match="cost_exponent must be >= 1"):
            cost_for_upgrade(current_thickness=1, cost_base=1000, cost_exponent=0)


# ---- 1.4.3 — table-driven unlock-проверки активностей ----


# Дефолтная таблица из `balance.yaml::thickness.unlock_levels` (ГДД §3.3).
_GDD_UNLOCK_LEVELS = {
    "forest": 1,
    "pvp_chat": 2,
    "mountains": 3,
    "raid_participate": 4,
    "caravan_raider": 5,
    "dungeon": 6,
    "caravan_create": 7,
    "raid_summon": 9,
}


class TestIsActivityUnlocked:
    @pytest.mark.parametrize(
        ("activity", "min_thickness"),
        sorted(_GDD_UNLOCK_LEVELS.items()),
    )
    def test_locked_when_below_threshold(self, activity: str, min_thickness: int) -> None:
        if min_thickness <= 1:
            pytest.skip("forest is unlocked at thickness=1 — нет «ниже»")
        assert (
            is_activity_unlocked(
                thickness=min_thickness - 1,
                activity=activity,
                unlock_levels=_GDD_UNLOCK_LEVELS,
            )
            is False
        )

    @pytest.mark.parametrize(
        ("activity", "min_thickness"),
        sorted(_GDD_UNLOCK_LEVELS.items()),
    )
    def test_unlocked_at_threshold(self, activity: str, min_thickness: int) -> None:
        assert (
            is_activity_unlocked(
                thickness=min_thickness,
                activity=activity,
                unlock_levels=_GDD_UNLOCK_LEVELS,
            )
            is True
        )

    @pytest.mark.parametrize(
        ("activity", "min_thickness"),
        sorted(_GDD_UNLOCK_LEVELS.items()),
    )
    def test_unlocked_above_threshold(self, activity: str, min_thickness: int) -> None:
        assert (
            is_activity_unlocked(
                thickness=min_thickness + 5,
                activity=activity,
                unlock_levels=_GDD_UNLOCK_LEVELS,
            )
            is True
        )

    def test_unknown_activity_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="unknown activity 'wormhole'"):
            is_activity_unlocked(
                thickness=10,
                activity="wormhole",
                unlock_levels=_GDD_UNLOCK_LEVELS,
            )

    def test_rejects_invalid_thickness(self) -> None:
        with pytest.raises(ValueError, match="thickness must be >= 1"):
            is_activity_unlocked(
                thickness=0,
                activity="forest",
                unlock_levels=_GDD_UNLOCK_LEVELS,
            )


class TestRequireUnlocked:
    def test_does_nothing_when_unlocked(self) -> None:
        require_unlocked(
            thickness=3,
            activity="mountains",
            unlock_levels=_GDD_UNLOCK_LEVELS,
        )

    def test_raises_with_payload_when_locked(self) -> None:
        with pytest.raises(ActivityLockedError) as exc_info:
            require_unlocked(
                thickness=2,
                activity="mountains",
                unlock_levels=_GDD_UNLOCK_LEVELS,
            )
        err = exc_info.value
        assert err.activity == "mountains"
        assert err.current_thickness == 2
        assert err.required_thickness == 3
        assert "thickness >= 3" in str(err)
        assert "got 2" in str(err)

    def test_unknown_activity_propagates_keyerror(self) -> None:
        with pytest.raises(KeyError):
            require_unlocked(
                thickness=10,
                activity="wormhole",
                unlock_levels=_GDD_UNLOCK_LEVELS,
            )
