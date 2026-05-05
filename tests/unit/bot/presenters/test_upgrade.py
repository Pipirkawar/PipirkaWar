"""Юнит-тесты презентеров `/upgrade` (Спринт 1.4.A → 1.5.D, ПД 1.4.2)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.upgrade import (
    UpgradeCallbackData,
    UpgradePresenter,
    parse_upgrade_callback_data,
    upgrade_callback_data,
)
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle


def _fluent_bundle() -> IMessageBundle:
    return FluentMessageBundle(locales_dir=Path(__file__).resolve().parents[4] / "locales")


class TestUpgradePresenterFakeBundle:
    """Маркерный bundle: проверяем, какие ключи и параметры зовёт презентер."""

    def _make(self) -> UpgradePresenter:
        return UpgradePresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))

    def test_chat_branches_use_distinct_keys(self) -> None:
        p = self._make()
        ru = Locale("ru")
        assert p.group(locale=ru) == "ru:upgrade-group"
        assert p.other(locale=ru) == "ru:upgrade-other"
        assert p.not_registered(locale=ru) == "ru:upgrade-not-registered"

    def test_proposal_passes_all_parameters(self) -> None:
        out = self._make().proposal(
            current_thickness=1,
            cost_cm=4_000,
            current_length_cm=5_000,
            min_after_spend_cm=20,
            locale=Locale("ru"),
        )
        assert "ru:upgrade-proposal[" in out
        assert "current_thickness=1" in out
        assert "next_thickness=2" in out
        assert "cost_cm=4000" in out
        assert "current_length_cm=5000" in out
        assert "remaining_cm=1000" in out
        assert "min_after_spend_cm=20" in out

    def test_success_passes_all_parameters(self) -> None:
        out = self._make().success(
            new_thickness=2,
            cost_cm=4_000,
            new_length_cm=1_000,
            locale=Locale("ru"),
        )
        assert "ru:upgrade-success[" in out
        assert "new_thickness=2" in out
        assert "cost_cm=4000" in out
        assert "new_length_cm=1000" in out

    def test_insufficient_passes_all_parameters(self) -> None:
        out = self._make().insufficient(
            current_thickness=1,
            cost_cm=4_000,
            current_length_cm=10,
            deficit_cm=4_010,
            min_after_spend_cm=20,
            locale=Locale("ru"),
        )
        assert "ru:upgrade-insufficient[" in out
        assert "next_thickness=2" in out
        assert "cost_cm=4000" in out
        assert "current_length_cm=10" in out
        assert "deficit_cm=4010" in out
        assert "min_after_spend_cm=20" in out

    def test_insufficient_short_for_callback_edit(self) -> None:
        out = self._make().insufficient_short(
            cost_cm=4_000,
            current_length_cm=10,
            min_after_spend_cm=20,
            deficit_cm=4_010,
            locale=Locale("ru"),
        )
        assert "ru:upgrade-insufficient-short[" in out
        assert "cost_cm=4000" in out
        assert "current_length_cm=10" in out
        assert "min_after_spend_cm=20" in out
        assert "deficit_cm=4010" in out

    def test_cancelled_and_race(self) -> None:
        p = self._make()
        ru = Locale("ru")
        assert p.cancelled(locale=ru) == "ru:upgrade-cancelled"
        assert p.race(locale=ru) == "ru:upgrade-race"

    def test_toasts(self) -> None:
        p = self._make()
        ru = Locale("ru")
        assert p.toast_upgraded(locale=ru) == "ru:upgrade-toast-upgraded"
        assert p.toast_cancelled(locale=ru) == "ru:upgrade-toast-cancelled"
        assert p.toast_player_not_found(locale=ru) == "ru:upgrade-toast-player-not-found"
        assert p.toast_insufficient(locale=ru) == "ru:upgrade-toast-insufficient"
        assert p.toast_race(locale=ru) == "ru:upgrade-toast-race"

    def test_proposal_keyboard_uses_localized_button_labels(self) -> None:
        kb = self._make().proposal_keyboard(
            expected_cost_cm=4_000,
            locale=Locale("ru"),
        )
        assert len(kb.inline_keyboard) == 1
        row = kb.inline_keyboard[0]
        assert len(row) == 2
        confirm, cancel = row
        # FakeMessageBundle сериализует параметры маркером.
        assert confirm.text == "ru:upgrade-button-confirm[cost_cm=4000]"
        assert cancel.text == "ru:upgrade-button-cancel"
        # callback_data — invariant и не зависит от локали.
        assert confirm.callback_data == "upgrade:confirm:4000"
        assert cancel.callback_data == "upgrade:cancel:0"


class TestUpgradePresenterFluent:
    """Интеграционный рендер через настоящий `FluentMessageBundle`."""

    def _make(self) -> UpgradePresenter:
        return UpgradePresenter(bundle=_fluent_bundle())

    def test_proposal_ru(self) -> None:
        text = self._make().proposal(
            current_thickness=1,
            cost_cm=4_000,
            current_length_cm=5_000,
            min_after_spend_cm=20,
            locale=Locale("ru"),
        )
        assert "Прокачка толщины" in text
        assert "Текущий уровень: 1" in text
        assert "Целевой уровень: 2" in text
        assert "4000 см" in text
        assert "У тебя: 5000 см" in text
        assert "Останется: 1000 см" in text
        assert "минимум по правилу 20 см" in text

    def test_proposal_en(self) -> None:
        text = self._make().proposal(
            current_thickness=1,
            cost_cm=4_000,
            current_length_cm=5_000,
            min_after_spend_cm=20,
            locale=Locale("en"),
        )
        assert "Thickness upgrade" in text
        assert "Current level: 1" in text
        assert "Target level: 2" in text
        assert "4000 cm" in text
        assert "Remaining: 1000 cm" in text
        assert "20 cm rule" in text

    def test_success_ru(self) -> None:
        text = self._make().success(
            new_thickness=2,
            cost_cm=4_000,
            new_length_cm=1_000,
            locale=Locale("ru"),
        )
        assert "Толщина прокачана до 2" in text
        assert "Списано: 4000 см" in text
        assert "Осталось: 1000 см" in text

    def test_success_en(self) -> None:
        text = self._make().success(
            new_thickness=2,
            cost_cm=4_000,
            new_length_cm=1_000,
            locale=Locale("en"),
        )
        assert "Thickness upgraded to 2" in text
        assert "Spent: 4000 cm" in text
        assert "Remaining: 1000 cm" in text

    def test_insufficient_ru(self) -> None:
        text = self._make().insufficient(
            current_thickness=1,
            cost_cm=4_000,
            current_length_cm=10,
            deficit_cm=4_010,
            min_after_spend_cm=20,
            locale=Locale("ru"),
        )
        assert "Недостаточно длины" in text
        assert "до 2" in text
        assert "4000 см" in text
        assert "4010 см" in text

    def test_insufficient_short_ru(self) -> None:
        text = self._make().insufficient_short(
            cost_cm=4_000,
            current_length_cm=10,
            min_after_spend_cm=20,
            deficit_cm=4_010,
            locale=Locale("ru"),
        )
        assert "Недостаточно длины" in text
        assert "Стоимость: 4000 см" in text
        assert "У тебя: 10 см" in text
        assert "Не хватает: 4010 см" in text

    def test_cancelled_and_race_localized(self) -> None:
        p = self._make()
        ru = Locale("ru")
        en = Locale("en")
        assert "отменена" in p.cancelled(locale=ru).lower()
        assert "cancelled" in p.cancelled(locale=en).lower()
        assert "Стоимость прокачки изменилась" in p.race(locale=ru)
        assert "cost has changed" in p.race(locale=en)

    def test_proposal_keyboard_ru_button_labels(self) -> None:
        kb = self._make().proposal_keyboard(
            expected_cost_cm=4_000,
            locale=Locale("ru"),
        )
        confirm, cancel = kb.inline_keyboard[0]
        assert confirm.text == "Подтвердить (4000 см)"
        assert cancel.text == "Отменить"
        assert confirm.callback_data == "upgrade:confirm:4000"
        assert cancel.callback_data == "upgrade:cancel:0"

    def test_proposal_keyboard_en_button_labels(self) -> None:
        kb = self._make().proposal_keyboard(
            expected_cost_cm=4_000,
            locale=Locale("en"),
        )
        confirm, cancel = kb.inline_keyboard[0]
        assert confirm.text == "Confirm (4000 cm)"
        assert cancel.text == "Cancel"


class TestUpgradeCallbackDataRoundTrip:
    @pytest.mark.parametrize(
        ("action", "expected_cost"),
        [("confirm", 1_000), ("confirm", 100_000), ("cancel", 0)],
    )
    def test_round_trip(self, action: str, expected_cost: int) -> None:
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
