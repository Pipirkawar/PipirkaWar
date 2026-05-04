"""Юнит-тесты презентеров `/upgrade` (Спринт 1.4.A)."""

from __future__ import annotations

import pytest

from pipirik_wars.bot.presenters.upgrade import (
    UpgradeCallbackData,
    build_upgrade_proposal_keyboard,
    parse_upgrade_callback_data,
    render_upgrade_insufficient,
    render_upgrade_proposal,
    render_upgrade_success,
    upgrade_callback_data,
)


class TestRenderUpgradeProposal:
    def test_contains_levels_cost_and_remaining(self) -> None:
        text = render_upgrade_proposal(
            current_thickness=1,
            cost_cm=4_000,
            current_length_cm=5_000,
            min_after_spend_cm=20,
        )
        assert "Прокачка толщины" in text
        assert "Текущий уровень: 1" in text
        assert "Целевой уровень: 2" in text
        assert "4000 см" in text
        assert "У тебя: 5000 см" in text
        assert "Останется: 1000 см" in text
        assert "минимум по правилу 20 см" in text


class TestRenderUpgradeSuccess:
    def test_contains_new_thickness_and_remainder(self) -> None:
        text = render_upgrade_success(
            new_thickness=2,
            cost_cm=4_000,
            new_length_cm=1_000,
        )
        assert "Толщина прокачана до 2" in text
        assert "Списано: 4000 см" in text
        assert "Осталось: 1000 см" in text


class TestRenderUpgradeInsufficient:
    def test_contains_deficit(self) -> None:
        text = render_upgrade_insufficient(
            current_thickness=1,
            cost_cm=4_000,
            current_length_cm=10,
            deficit_cm=4_010,
            min_after_spend_cm=20,
        )
        assert "Недостаточно длины" in text
        assert "до 2" in text
        assert "4000 см" in text
        assert "4010" in text


class TestBuildUpgradeProposalKeyboard:
    def test_layout_two_buttons_with_correct_callback_data(self) -> None:
        kb = build_upgrade_proposal_keyboard(expected_cost_cm=4_000)
        assert len(kb.inline_keyboard) == 1
        row = kb.inline_keyboard[0]
        assert len(row) == 2
        confirm, cancel = row
        assert confirm.text == "Подтвердить (4000 см)"
        assert confirm.callback_data == "upgrade:confirm:4000"
        assert cancel.text == "Отменить"
        assert cancel.callback_data == "upgrade:cancel:0"


class TestUpgradeCallbackDataRoundTrip:
    @pytest.mark.parametrize(
        ("action", "expected_cost"),
        [("confirm", 1_000), ("confirm", 100_000), ("cancel", 0)],
    )
    def test_round_trip(self, action: str, expected_cost: int) -> None:
        # type: ignore[arg-type]
        if action == "confirm":
            raw = upgrade_callback_data("confirm", expected_cost)
        else:
            raw = upgrade_callback_data("cancel", expected_cost)
        parsed = parse_upgrade_callback_data(raw)
        assert isinstance(parsed, UpgradeCallbackData)
        assert parsed.action == action
        assert parsed.expected_cost_cm == expected_cost

    def test_telegram_64_byte_limit(self) -> None:
        # Самый длинный action + 10-значное число → должно умещаться.
        raw = upgrade_callback_data("confirm", 9_999_999_999)
        assert len(raw.encode("utf-8")) <= 64

    def test_invalid_prefix_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid upgrade callback_data prefix"):
            parse_upgrade_callback_data("forest:confirm:1000")

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid upgrade callback_data"):
            parse_upgrade_callback_data("upgrade:confirm")

    def test_unknown_action_raises_in_parser(self) -> None:
        with pytest.raises(ValueError, match="unknown upgrade action"):
            parse_upgrade_callback_data("upgrade:explode:1000")

    def test_unknown_action_raises_in_serializer(self) -> None:
        with pytest.raises(ValueError, match="unknown upgrade action"):
            upgrade_callback_data("explode", 1_000)  # type: ignore[arg-type]

    def test_negative_cost_rejected_in_serializer(self) -> None:
        with pytest.raises(ValueError, match="expected_cost_cm must be >= 0"):
            upgrade_callback_data("confirm", -1)

    def test_non_numeric_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalid expected_cost_cm"):
            parse_upgrade_callback_data("upgrade:confirm:abc")

    def test_negative_cost_rejected_in_parser(self) -> None:
        with pytest.raises(ValueError, match="expected_cost_cm must be >= 0"):
            parse_upgrade_callback_data("upgrade:confirm:-1")
