"""Юнит-тесты `MassDuelPresenter` (Спринт 2.2.F часть 2).

Проверяем:

1. Парсеры callback_data — happy-path и ошибки.
2. Маркеры `FakeMessageBundle` — какие ключи и параметры зовёт презентер.
3. Реальный `FluentMessageBundle` — RU/EN рендер на ключевых сценариях
   (карточка старта + DM-промпты + результат).
4. Кейборды отдают валидные `pvpm-*` callback_data в правильных ячейках.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.mass_duel import (
    MassDuelPresenter,
    mass_attack_callback_data,
    mass_block_callback_data,
    parse_mass_attack_callback_data,
    parse_mass_block_callback_data,
)
from pipirik_wars.domain.pvp import MassDuelWinner, Position
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle


def _fluent() -> IMessageBundle:
    return FluentMessageBundle(
        locales_dir=Path(__file__).resolve().parents[4] / "locales",
    )


def _fake() -> MassDuelPresenter:
    return MassDuelPresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))


# ──────────────────────── Callback-data ────────────────────────────


class TestAttackCallbackData:
    @pytest.mark.parametrize(
        ("position", "expected"),
        [
            (Position.HIGH, "pvpm-attack:42:high"),
            (Position.MID, "pvpm-attack:42:mid"),
            (Position.LOW, "pvpm-attack:42:low"),
        ],
    )
    def test_serialize_round_trip(self, position: Position, expected: str) -> None:
        raw = mass_attack_callback_data(42, position)
        assert raw == expected
        parsed = parse_mass_attack_callback_data(raw)
        assert parsed.duel_id == 42
        assert parsed.position == position.value

    def test_serialize_rejects_non_positive_id(self) -> None:
        with pytest.raises(ValueError, match="duel_id must be positive"):
            mass_attack_callback_data(0, Position.HIGH)
        with pytest.raises(ValueError, match="duel_id must be positive"):
            mass_attack_callback_data(-1, Position.MID)

    @pytest.mark.parametrize(
        "data",
        [
            "pvpm-attack:42",
            "pvpm-attack:42:high:extra",
            "pvp-attack:42:high",
            "pvpm-block:42:high:high",
            "pvpm-attack:abc:high",
            "pvpm-attack:0:high",
            "pvpm-attack:-1:high",
            "pvpm-attack:42:diagonal",
            "",
        ],
    )
    def test_parse_invalid_raises(self, data: str) -> None:
        with pytest.raises(ValueError):
            parse_mass_attack_callback_data(data)


class TestBlockCallbackData:
    @pytest.mark.parametrize(
        ("attack", "block", "expected"),
        [
            (Position.HIGH, Position.HIGH, "pvpm-block:42:high:high"),
            (Position.HIGH, Position.LOW, "pvpm-block:42:high:low"),
            (Position.MID, Position.HIGH, "pvpm-block:42:mid:high"),
            (Position.LOW, Position.MID, "pvpm-block:42:low:mid"),
        ],
    )
    def test_serialize_round_trip(
        self,
        attack: Position,
        block: Position,
        expected: str,
    ) -> None:
        raw = mass_block_callback_data(42, attack, block)
        assert raw == expected
        parsed = parse_mass_block_callback_data(raw)
        assert parsed.duel_id == 42
        assert parsed.attack == attack.value
        assert parsed.position == block.value

    def test_serialize_rejects_non_positive_id(self) -> None:
        with pytest.raises(ValueError, match="duel_id must be positive"):
            mass_block_callback_data(0, Position.HIGH, Position.LOW)

    @pytest.mark.parametrize(
        "data",
        [
            "pvpm-block:42",
            "pvpm-block:42:high",
            "pvpm-block:42:high:low:extra",
            "pvp-block:42:high:low",
            "pvpm-attack:42:high:low",
            "pvpm-block:abc:high:low",
            "pvpm-block:42:diagonal:low",
            "pvpm-block:42:high:diagonal",
            "",
        ],
    )
    def test_parse_invalid_raises(self, data: str) -> None:
        with pytest.raises(ValueError):
            parse_mass_block_callback_data(data)

    def test_callback_data_under_64_bytes(self) -> None:
        raw = mass_block_callback_data(2_147_483_647, Position.HIGH, Position.LOW)
        assert len(raw.encode("utf-8")) <= 64


# ─────────────────────── Fake-bundle markers ─────────────────────


class TestPresenterFakeBundle:
    def test_needs_group_chat_uses_key(self) -> None:
        assert _fake().needs_group_chat(locale=Locale("ru")) == "ru:pvp-mass-needs-group-chat"

    def test_attacker_not_member_uses_key(self) -> None:
        assert _fake().attacker_not_member(locale=Locale("en")) == "en:pvp-mass-attacker-not-member"

    def test_target_not_found_uses_key(self) -> None:
        assert _fake().target_not_found(locale=Locale("ru")) == "ru:pvp-mass-target-not-found"

    def test_self_attack_uses_key(self) -> None:
        assert _fake().self_attack(locale=Locale("ru")) == "ru:pvp-mass-self-attack"

    def test_clan_frozen_uses_key(self) -> None:
        assert _fake().clan_frozen(locale=Locale("ru")) == "ru:pvp-mass-clan-frozen"

    def test_cooldown_passes_hours(self) -> None:
        out = _fake().cooldown(cooldown_hours=6, locale=Locale("ru"))
        assert "ru:pvp-mass-cooldown" in out
        assert "cooldown_hours=6" in out

    def test_no_participants_passes_thresholds(self) -> None:
        out = _fake().no_participants(
            min_length_cm=20,
            min_thickness_level=2,
            locale=Locale("ru"),
        )
        assert "ru:pvp-mass-no-participants" in out
        assert "min_length_cm=20" in out
        assert "min_thickness_level=2" in out

    def test_lock_already_held_uses_key(self) -> None:
        assert _fake().lock_already_held(locale=Locale("ru")) == "ru:pvp-mass-lock-already-held"

    def test_started_card_passes_titles_and_sizes(self) -> None:
        out = _fake().started_card(
            attacker_title="Alpha",
            defender_title="Beta",
            attacker_size=3,
            defender_size=5,
            timer_seconds=180,
            locale=Locale("ru"),
        )
        assert "ru:pvp-mass-started" in out
        assert "attacker=Alpha" in out
        assert "defender=Beta" in out
        assert "attacker_size=3" in out
        assert "defender_size=5" in out
        assert "timer_seconds=180" in out

    def test_prompt_attack_uses_key(self) -> None:
        assert _fake().prompt_attack(locale=Locale("ru")) == "ru:pvp-mass-prompt-attack"

    def test_prompt_block_passes_attack(self) -> None:
        out = _fake().prompt_block(attack=Position.MID, locale=Locale("en"))
        assert "en:pvp-mass-prompt-block" in out
        assert "attack=mid" in out

    def test_waiting_uses_key(self) -> None:
        assert _fake().waiting(locale=Locale("ru")) == "ru:pvp-mass-waiting"

    def test_result_victory_dm_passes_clan_and_delta(self) -> None:
        out = _fake().result_victory_dm(
            winner_clan_title="Alpha",
            total_dealt=42,
            delta_cm=15,
            locale=Locale("ru"),
        )
        assert "ru:pvp-mass-result-victory" in out
        assert "clan=Alpha" in out
        assert "total_dealt=42" in out
        assert "delta_sign=+" in out
        assert "delta_cm=15" in out

    def test_result_defeat_dm_uses_minus_sign(self) -> None:
        out = _fake().result_defeat_dm(
            loser_clan_title="Beta",
            total_lost=20,
            delta_cm=-7,
            locale=Locale("en"),
        )
        assert "en:pvp-mass-result-defeat" in out
        assert "delta_sign=−" in out
        assert "delta_cm=7" in out  # abs

    def test_result_draw_dm_no_sign_for_zero(self) -> None:
        out = _fake().result_draw_dm(delta_cm=0, locale=Locale("ru"))
        assert "ru:pvp-mass-result-draw" in out
        assert "delta_sign=" in out
        assert "delta_cm=0" in out

    def test_result_chat_victory_uses_winner_key(self) -> None:
        out = _fake().result_chat(
            winner=MassDuelWinner.CLAN1,
            winner_clan_title="Alpha",
            total_dealt=42,
            locale=Locale("ru"),
        )
        assert "ru:pvp-mass-result-chat-victory" in out
        assert "clan=Alpha" in out
        assert "total_dealt=42" in out

    def test_result_chat_draw_uses_draw_key(self) -> None:
        out = _fake().result_chat(
            winner=MassDuelWinner.DRAW,
            winner_clan_title="ignored",
            total_dealt=10,
            locale=Locale("ru"),
        )
        assert "ru:pvp-mass-result-chat-draw" in out
        assert "total_dealt=10" in out
        assert "clan=" not in out

    @pytest.mark.parametrize(
        "method_name",
        [
            "toast_not_found",
            "toast_not_participant",
            "toast_foreign_button",
            "toast_invalid_state",
            "toast_already_submitted",
            "toast_outdated",
            "toast_attack_selected",
            "toast_move_accepted",
        ],
    )
    def test_toast_methods_use_keys(self, method_name: str) -> None:
        method = getattr(_fake(), method_name)
        out = method(locale=Locale("ru"))
        # Все toast-ы должны иметь префикс `ru:pvp-mass-toast-`.
        assert out.startswith("ru:pvp-mass-toast-")


# ─────────────────────── Keyboards ─────────────────────────────


class TestKeyboards:
    def test_attack_keyboard_has_three_buttons_in_one_row(self) -> None:
        kb = _fake().attack_keyboard(duel_id=42, locale=Locale("ru"))
        assert len(kb.inline_keyboard) == 1
        row = kb.inline_keyboard[0]
        assert len(row) == 3
        callbacks = [b.callback_data for b in row]
        assert callbacks == [
            "pvpm-attack:42:high",
            "pvpm-attack:42:mid",
            "pvpm-attack:42:low",
        ]

    def test_block_keyboard_carries_attack_in_callback(self) -> None:
        kb = _fake().block_keyboard(
            duel_id=42,
            attack=Position.HIGH,
            locale=Locale("ru"),
        )
        assert len(kb.inline_keyboard) == 1
        row = kb.inline_keyboard[0]
        callbacks = [b.callback_data for b in row]
        assert callbacks == [
            "pvpm-block:42:high:high",
            "pvpm-block:42:high:mid",
            "pvpm-block:42:high:low",
        ]

    def test_block_keyboard_with_mid_attack(self) -> None:
        kb = _fake().block_keyboard(
            duel_id=7,
            attack=Position.MID,
            locale=Locale("ru"),
        )
        callbacks = [b.callback_data for b in kb.inline_keyboard[0]]
        assert callbacks == [
            "pvpm-block:7:mid:high",
            "pvpm-block:7:mid:mid",
            "pvpm-block:7:mid:low",
        ]

    def test_attack_keyboard_labels_localized(self) -> None:
        kb_ru = _fake().attack_keyboard(duel_id=42, locale=Locale("ru"))
        labels_ru = [b.text for b in kb_ru.inline_keyboard[0]]
        assert labels_ru == [
            "ru:pvp-mass-button-attack-high",
            "ru:pvp-mass-button-attack-mid",
            "ru:pvp-mass-button-attack-low",
        ]
        kb_en = _fake().attack_keyboard(duel_id=42, locale=Locale("en"))
        labels_en = [b.text for b in kb_en.inline_keyboard[0]]
        assert labels_en[0].startswith("en:")


# ─────────────────────── Fluent integration (RU/EN) ────────────


class TestFluentIntegration:
    def test_started_card_renders_clans_and_timer_ru(self) -> None:
        bundle = _fluent()
        presenter = MassDuelPresenter(bundle=bundle)
        out = presenter.started_card(
            attacker_title="Alpha",
            defender_title="Beta",
            attacker_size=3,
            defender_size=5,
            timer_seconds=180,
            locale=Locale("ru"),
        )
        assert "Alpha" in out
        assert "Beta" in out
        assert "180" in out

    def test_started_card_renders_en(self) -> None:
        bundle = _fluent()
        presenter = MassDuelPresenter(bundle=bundle)
        out = presenter.started_card(
            attacker_title="Alpha",
            defender_title="Beta",
            attacker_size=2,
            defender_size=3,
            timer_seconds=180,
            locale=Locale("en"),
        )
        assert "Alpha" in out
        assert "Beta" in out

    def test_prompt_block_renders_attack_token(self) -> None:
        bundle = _fluent()
        presenter = MassDuelPresenter(bundle=bundle)
        out = presenter.prompt_block(attack=Position.HIGH, locale=Locale("ru"))
        assert "high" in out

    def test_result_victory_dm_renders_clan_and_total_ru(self) -> None:
        bundle = _fluent()
        presenter = MassDuelPresenter(bundle=bundle)
        out = presenter.result_victory_dm(
            winner_clan_title="Alpha",
            total_dealt=42,
            delta_cm=10,
            locale=Locale("ru"),
        )
        assert "Alpha" in out
        assert "42" in out
        assert "10" in out

    def test_result_chat_draw_renders_total(self) -> None:
        bundle = _fluent()
        presenter = MassDuelPresenter(bundle=bundle)
        out = presenter.result_chat(
            winner=MassDuelWinner.DRAW,
            winner_clan_title="unused",
            total_dealt=15,
            locale=Locale("ru"),
        )
        assert "15" in out

    def test_attack_keyboard_renders_localized_labels(self) -> None:
        bundle = _fluent()
        presenter = MassDuelPresenter(bundle=bundle)
        kb = presenter.attack_keyboard(duel_id=1, locale=Locale("ru"))
        labels = [b.text for b in kb.inline_keyboard[0]]
        # RU-labels не пустые и не равны fallback-маркерам.
        assert all(label and not label.startswith("ru:") for label in labels)
