"""Юнит-тесты `DuelPresenter` (Спринт 2.1.E + 2.1.F.3).

Проверяем:

1. Маркеры `FakeMessageBundle` — какие ключи зовёт презентер.
2. Парсеры callback-data — happy-path и ошибки.
3. Реальный `FluentMessageBundle` — RU/EN рендер для глобал-лобби (F.3).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.duel import (
    DuelPresenter,
    accept_callback_data,
    attack_callback_data,
    block_callback_data,
    parse_accept_callback_data,
    parse_attack_callback_data,
    parse_block_callback_data,
    parse_reject_callback_data,
    parse_share_callback_data,
    reject_callback_data,
    share_callback_data,
)
from pipirik_wars.domain.pvp import (
    DuelLogTemplate,
    DuelOutcome,
    DuelWinner,
    Position,
    RoundChoice,
    RoundOutcome,
    RoundOutcomeKind,
)
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle


def _fluent() -> IMessageBundle:
    return FluentMessageBundle(
        locales_dir=Path(__file__).resolve().parents[4] / "locales",
    )


def _fake() -> DuelPresenter:
    return DuelPresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))


# ─────────────────────── FakeBundle (unit) ───────────────────────


class TestDuelPresenterFake:
    def test_private_needs_global_uses_key(self) -> None:
        assert _fake().private_needs_global(locale=Locale("ru")) == "ru:duel-private-needs-global"

    def test_usage_uses_key(self) -> None:
        assert _fake().usage(locale=Locale("en")) == "en:duel-usage"

    def test_not_registered_uses_key(self) -> None:
        assert _fake().not_registered(locale=Locale("ru")) == "ru:duel-not-registered"

    def test_target_not_registered_uses_key(self) -> None:
        assert _fake().target_not_registered(locale=Locale("ru")) == "ru:duel-target-not-registered"

    def test_target_is_bot_uses_key(self) -> None:
        assert _fake().target_is_bot(locale=Locale("ru")) == "ru:duel-target-is-bot"

    def test_self_challenge_uses_key(self) -> None:
        assert _fake().self_challenge(locale=Locale("ru")) == "ru:duel-self-challenge"

    def test_challenge_chat_only_passes_usernames(self) -> None:
        out = _fake().challenge_chat_only(
            challenger_username="@a",
            challenged_username="@b",
            locale=Locale("ru"),
        )
        assert "ru:duel-challenge-chat" in out
        assert "challenger=@a" in out and "challenged=@b" in out

    def test_challenge_chat_then_global_passes_usernames(self) -> None:
        out = _fake().challenge_chat_then_global(
            challenger_username="@a",
            challenged_username="@b",
            locale=Locale("ru"),
        )
        assert "ru:duel-challenge-chat-then-global" in out

    def test_challenge_global_passes_ttl(self) -> None:
        out = _fake().challenge_global(
            challenger_username="@a",
            ttl_minutes=10,
            locale=Locale("ru"),
        )
        assert "ru:duel-challenge-global" in out
        assert "challenger=@a" in out
        assert "ttl_minutes=10" in out

    def test_global_enqueued_passes_duel_id_and_ttl(self) -> None:
        out = _fake().global_enqueued(
            duel_id=42,
            ttl_minutes=7,
            locale=Locale("ru"),
        )
        assert "ru:duel-global-enqueued" in out
        assert "duel_id=42" in out
        assert "ttl_minutes=7" in out

    def test_global_matched_passes_challenger(self) -> None:
        out = _fake().global_matched(
            challenger_username="@alice",
            locale=Locale("en"),
        )
        assert "en:duel-global-matched" in out
        assert "challenger=@alice" in out

    def test_global_empty_uses_key(self) -> None:
        assert _fake().global_empty(locale=Locale("ru")) == "ru:duel-global-empty"

    def test_global_only_in_private_uses_key(self) -> None:
        assert (
            _fake().global_only_in_private(locale=Locale("en")) == "en:duel-global-only-in-private"
        )

    def test_chat_accepted(self) -> None:
        out = _fake().chat_accepted(
            challenger_username="@a",
            challenged_username="@b",
            locale=Locale("ru"),
        )
        assert "ru:duel-chat-accepted" in out

    def test_cancelled(self) -> None:
        out = _fake().cancelled(challenger_username="@a", locale=Locale("ru"))
        assert "ru:duel-cancelled" in out

    def test_round_prompts(self) -> None:
        atk = _fake().round_attack_prompt(round_num=2, locale=Locale("ru"))
        blk = _fake().round_block_prompt(round_num=2, attack=Position.HIGH, locale=Locale("ru"))
        wait = _fake().round_waiting(round_num=2, locale=Locale("ru"))
        assert "ru:duel-round-attack-prompt" in atk
        assert "ru:duel-round-block-prompt" in blk
        assert "ru:duel-round-waiting" in wait

    def test_results(self) -> None:
        v = _fake().result_victory(delta_cm=5, new_length_cm=30, locale=Locale("ru"))
        d = _fake().result_defeat(delta_cm=-5, new_length_cm=20, locale=Locale("ru"))
        dr = _fake().result_draw(length_cm=25, locale=Locale("ru"))
        assert "ru:duel-result-victory" in v
        assert "ru:duel-result-defeat" in d
        assert "ru:duel-result-draw" in dr

    def test_requirements(self) -> None:
        out = _fake().requirements_not_met(
            min_length_cm=20,
            min_thickness_level=2,
            locale=Locale("ru"),
        )
        assert "ru:duel-requirements-not-met" in out

    def test_anticheat(self) -> None:
        out = _fake().anticheat_blocked(banned_until="2030-01-01", locale=Locale("ru"))
        assert "ru:duel-anticheat-blocked" in out

    def test_lock_already_held(self) -> None:
        assert _fake().lock_already_held(locale=Locale("ru")) == "ru:duel-lock-already-held"

    def test_cancel_usage(self) -> None:
        assert _fake().cancel_usage(locale=Locale("ru")) == "ru:duel-cancel-usage"

    def test_toasts(self) -> None:
        p = _fake()
        loc = Locale("ru")
        assert p.toast_accepted(locale=loc) == "ru:duel-toast-accepted"
        assert p.toast_rejected(locale=loc) == "ru:duel-toast-rejected"
        assert p.toast_cancelled(locale=loc) == "ru:duel-toast-cancelled"
        assert p.toast_duel_not_found(locale=loc) == "ru:duel-toast-not-found"
        assert p.toast_not_participant(locale=loc) == "ru:duel-toast-not-participant"
        assert p.toast_foreign_button(locale=loc) == "ru:duel-toast-foreign-button"
        assert p.toast_invalid_state(locale=loc) == "ru:duel-toast-invalid-state"
        assert p.toast_already_submitted(locale=loc) == "ru:duel-toast-already-submitted"
        assert p.toast_outdated(locale=loc) == "ru:duel-toast-outdated"


# ─────────────────────── Callback-data parsers ───────────────────────


class TestCallbackDataRoundtrip:
    def test_accept_roundtrip(self) -> None:
        data = accept_callback_data(11)
        assert parse_accept_callback_data(data).duel_id == 11

    def test_reject_roundtrip(self) -> None:
        data = reject_callback_data(11)
        assert parse_reject_callback_data(data).duel_id == 11

    def test_attack_roundtrip(self) -> None:
        data = attack_callback_data(11, 2, Position.HIGH)
        parsed = parse_attack_callback_data(data)
        assert parsed.duel_id == 11
        assert parsed.round_num == 2
        assert parsed.position == "high"

    def test_block_roundtrip(self) -> None:
        data = block_callback_data(11, 2, Position.HIGH, Position.LOW)
        parsed = parse_block_callback_data(data)
        assert parsed.duel_id == 11
        assert parsed.round_num == 2
        assert parsed.attack == "high"
        assert parsed.position == "low"

    def test_share_roundtrip(self) -> None:
        data = share_callback_data(42)
        assert data == "pvp-share:42"
        assert parse_share_callback_data(data).duel_id == 42

    def test_share_rejects_non_positive(self) -> None:
        with pytest.raises(ValueError, match="duel_id must be positive"):
            share_callback_data(0)
        with pytest.raises(ValueError):
            share_callback_data(-3)


class TestCallbackDataParsersErrors:
    @pytest.mark.parametrize(
        "data",
        ["", "wrong-prefix:11", "pvp-accept:", "pvp-accept:abc", "pvp-accept:0", "pvp-accept:-1"],
    )
    def test_parse_accept_invalid_raises(self, data: str) -> None:
        with pytest.raises(ValueError):
            parse_accept_callback_data(data)

    @pytest.mark.parametrize(
        "data",
        ["", "wrong:11", "pvp-reject:", "pvp-reject:abc", "pvp-reject:0"],
    )
    def test_parse_reject_invalid_raises(self, data: str) -> None:
        with pytest.raises(ValueError):
            parse_reject_callback_data(data)

    @pytest.mark.parametrize(
        "data",
        [
            "",
            "pvp-attack:",
            "pvp-attack:11",
            "pvp-attack:11:abc:high",
            "pvp-attack:11:0:high",
            "pvp-attack:11:1:north",
        ],
    )
    def test_parse_attack_invalid_raises(self, data: str) -> None:
        with pytest.raises(ValueError):
            parse_attack_callback_data(data)

    @pytest.mark.parametrize(
        "data",
        [
            "",
            "pvp-block:",
            "pvp-block:11",
            "pvp-block:11:1:high",
            "pvp-block:11:0:high:low",
            "pvp-block:11:1:high:north",
            "pvp-block:11:abc:high:low",
        ],
    )
    def test_parse_block_invalid_raises(self, data: str) -> None:
        with pytest.raises(ValueError):
            parse_block_callback_data(data)

    @pytest.mark.parametrize(
        "data",
        ["", "wrong:11", "pvp-share:", "pvp-share:abc", "pvp-share:0", "pvp-share:-1"],
    )
    def test_parse_share_invalid_raises(self, data: str) -> None:
        with pytest.raises(ValueError):
            parse_share_callback_data(data)


# ─────────────────────── round_flavor / result_card (Спринт 2.1.H) ─────────


def _outcome(
    *,
    winner: DuelWinner,
    p1_delta: int = 0,
    p2_delta: int = 0,
) -> DuelOutcome:
    """Минимальный `DuelOutcome` для тестов карточки результата."""
    rc = RoundChoice(attack=Position.HIGH, block=Position.LOW)
    round_zero = RoundOutcome(
        p1_choice=rc,
        p2_choice=rc,
        p1_attack_blocked=False,
        p2_attack_blocked=False,
        p1_damage_to_p2=0,
        p2_damage_to_p1=0,
    )
    return DuelOutcome(
        rounds=(round_zero, round_zero, round_zero),
        p1_total_dealt=abs(p1_delta) if winner is DuelWinner.P1 else 0,
        p2_total_dealt=abs(p2_delta) if winner is DuelWinner.P2 else 0,
        p1_delta_cm=p1_delta,
        p2_delta_cm=p2_delta,
        winner=winner,
    )


class TestDuelPresenterRoundFlavor:
    def test_renders_p1_p2_for_both_hit(self) -> None:
        tpl = DuelLogTemplate(
            id="pvp.ru.both_hit.0001",
            text="🥊 {p1} и {p2} оба пробили блок!",
            kind=RoundOutcomeKind.BOTH_HIT,
        )
        out = _fake().round_flavor(template=tpl, p1_name="@alice", p2_name="@bob")
        assert out == "🥊 @alice и @bob оба пробили блок!"

    def test_renders_p1_p2_for_both_blocked(self) -> None:
        tpl = DuelLogTemplate(
            id="pvp.ru.both_blocked.0001",
            text="🛡 Двойной блок: {p1} vs {p2}",
            kind=RoundOutcomeKind.BOTH_BLOCKED,
        )
        out = _fake().round_flavor(template=tpl, p1_name="@a", p2_name="@b")
        assert out == "🛡 Двойной блок: @a vs @b"

    def test_renders_attacker_defender_for_single_hit(self) -> None:
        tpl = DuelLogTemplate(
            id="pvp.ru.single_hit.0001",
            text="💥 {attacker} пробил {defender}",
            kind=RoundOutcomeKind.SINGLE_HIT,
        )
        out = _fake().round_flavor(
            template=tpl,
            p1_name="@a",
            p2_name="@b",
            attacker_name="@a",
            defender_name="@b",
        )
        assert out == "💥 @a пробил @b"

    def test_returns_raw_text_on_unknown_placeholder(self) -> None:
        tpl = DuelLogTemplate(
            id="pvp.ru.both_hit.0002",
            text="bad: {unknown}",
            kind=RoundOutcomeKind.BOTH_HIT,
        )
        # `str.format` ругается KeyError → возвращаем сырой текст.
        assert _fake().round_flavor(template=tpl, p1_name="@a", p2_name="@b") == "bad: {unknown}"


class TestDuelPresenterResultCard:
    def test_victory_renders_winner_and_delta_p1(self) -> None:
        outcome = _outcome(winner=DuelWinner.P1, p1_delta=4, p2_delta=-4)
        out = _fake().result_card_text(
            outcome=outcome,
            p1_name="@alice",
            p2_name="@bob",
            locale=Locale("ru"),
        )
        assert "ru:duel-result-card-victory" in out
        assert "winner=@alice" in out and "loser=@bob" in out
        assert "delta_cm=4" in out

    def test_victory_renders_winner_and_delta_p2(self) -> None:
        outcome = _outcome(winner=DuelWinner.P2, p1_delta=-3, p2_delta=3)
        out = _fake().result_card_text(
            outcome=outcome,
            p1_name="@alice",
            p2_name="@bob",
            locale=Locale("en"),
        )
        assert "en:duel-result-card-victory" in out
        assert "winner=@bob" in out and "loser=@alice" in out
        assert "delta_cm=3" in out

    def test_draw_uses_draw_key(self) -> None:
        outcome = _outcome(winner=DuelWinner.DRAW)
        out = _fake().result_card_text(
            outcome=outcome,
            p1_name="@alice",
            p2_name="@bob",
            locale=Locale("ru"),
        )
        assert "ru:duel-result-card-draw" in out
        assert "p1=@alice" in out and "p2=@bob" in out

    def test_share_keyboard_one_button_with_correct_callback(self) -> None:
        keyboard = _fake().share_keyboard(duel_id=7, locale=Locale("ru"))
        assert len(keyboard.inline_keyboard) == 1
        row = keyboard.inline_keyboard[0]
        assert len(row) == 1
        button = row[0]
        assert "ru:duel-share-button" in button.text
        assert button.callback_data == "pvp-share:7"


class TestDuelPresenterFluentResultCard:
    def _make(self) -> DuelPresenter:
        return DuelPresenter(bundle=_fluent())

    def test_victory_card_ru_contains_winner_and_delta(self) -> None:
        outcome = _outcome(winner=DuelWinner.P1, p1_delta=5, p2_delta=-5)
        text = self._make().result_card_text(
            outcome=outcome,
            p1_name="@alice",
            p2_name="@bob",
            locale=Locale("ru"),
        )
        assert "@alice" in text
        assert "@bob" in text
        assert "5" in text

    def test_victory_card_en_contains_winner_and_delta(self) -> None:
        outcome = _outcome(winner=DuelWinner.P2, p1_delta=-2, p2_delta=2)
        text = self._make().result_card_text(
            outcome=outcome,
            p1_name="@alice",
            p2_name="@bob",
            locale=Locale("en"),
        )
        assert "@bob" in text
        assert "@alice" in text
        assert "2" in text

    def test_draw_card_ru_mentions_both(self) -> None:
        outcome = _outcome(winner=DuelWinner.DRAW)
        text = self._make().result_card_text(
            outcome=outcome,
            p1_name="@a",
            p2_name="@b",
            locale=Locale("ru"),
        )
        assert "@a" in text
        assert "@b" in text

    def test_share_button_label_localized_ru(self) -> None:
        keyboard = self._make().share_keyboard(duel_id=1, locale=Locale("ru"))
        button = keyboard.inline_keyboard[0][0]
        assert "Поделиться" in button.text

    def test_share_button_label_localized_en(self) -> None:
        keyboard = self._make().share_keyboard(duel_id=1, locale=Locale("en"))
        button = keyboard.inline_keyboard[0][0]
        assert "Share" in button.text


# ─────────────────────── FluentBundle (integration) ───────────────────────


class TestDuelPresenterFluent:
    def _make(self) -> DuelPresenter:
        return DuelPresenter(bundle=_fluent())

    def test_global_enqueued_ru(self) -> None:
        text = self._make().global_enqueued(
            duel_id=42,
            ttl_minutes=7,
            locale=Locale("ru"),
        )
        assert "глобальное лобби" in text
        assert "/cancel_duel" in text
        assert "42" in text

    def test_global_enqueued_en(self) -> None:
        text = self._make().global_enqueued(
            duel_id=42,
            ttl_minutes=7,
            locale=Locale("en"),
        )
        assert "global pool" in text
        assert "/cancel_duel" in text
        assert "42" in text

    def test_global_matched_ru(self) -> None:
        text = self._make().global_matched(
            challenger_username="@alice",
            locale=Locale("ru"),
        )
        assert "@alice" in text

    def test_global_empty_ru(self) -> None:
        text = self._make().global_empty(locale=Locale("ru"))
        assert "лобби" in text.lower() or "пусто" in text.lower()

    def test_global_only_in_private_en(self) -> None:
        text = self._make().global_only_in_private(locale=Locale("en"))
        assert "private chat" in text.lower()

    def test_challenge_global_ru_renders_ttl(self) -> None:
        text = self._make().challenge_global(
            challenger_username="@alice",
            ttl_minutes=15,
            locale=Locale("ru"),
        )
        assert "@alice" in text
        assert "15" in text
