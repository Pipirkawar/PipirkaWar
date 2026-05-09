"""Юнит-тесты `bot/presenters/bosses.py` (Спринт 3.3-D, D.5 / D.11c).

Покрываем:

1. Pure-функции `boss_callback_data` / `parse_boss_callback_data` /
   `is_boss_callback` — серилизация/парсинг `callback_data`,
   инварианты (≤ 64 байт, отказ на zero/negative `boss_fight_id`,
   отказ на unknown action, отказ на bad format).
2. `BossPresenter` через **`FakeMessageBundle`** — проверяем, что
   презентер просит правильные ключи и параметры (маркер
   `<locale>:<key>[k=v,...]` детерминистичен и не зависит от
   реальных переводов).
3. `BossPresenter` через **`FluentMessageBundle`** (RU + EN) —
   интеграционная проверка реальных переводов: вывод содержит
   ожидаемые подстроки в обеих локалях.
4. Locale parity для `bosses-*` ключей (RU↔EN). Глобальный parity
   уже покрыт `tests/unit/locales/test_admin_keys_lint.py::TestLocaleParity::test_full_parity`,
   но локальный фокусированный тест на boss-ключах помогает быстро
   ловить регрессии при росте набора `bosses-*` ключей.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fluent.syntax import parse as fluent_parse
from fluent.syntax.ast import Message, Term

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.bosses import (
    BossCallbackAction,
    BossCallbackData,
    BossPresenter,
    boss_callback_data,
    is_boss_callback,
    parse_boss_callback_data,
)
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightStatus,
    BossKind,
    BossParticipant,
)
from pipirik_wars.domain.player import (
    DisplayName,
    Length,
    Player,
    PlayerName,
    PlayerStatus,
    Thickness,
    Title,
    Username,
)
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_RU = Locale("ru")
_EN = Locale("en")


def _as_action(raw: str) -> BossCallbackAction:
    """Сужает `str` до `BossCallbackAction` для типобезопасных тестов."""
    if raw == "show_lobby":
        return "show_lobby"
    if raw == "join":
        return "join"
    if raw == "leave":
        return "leave"
    if raw == "cancel":
        return "cancel"
    raise AssertionError(f"unknown action: {raw!r}")


def _player(
    *,
    pid: int = 1,
    title: Title | None = None,
    name: PlayerName | None = None,
    length_cm: int = 47,
) -> Player:
    base = Player.new(tg_id=100 + pid, username=Username(value="alice"), now=_NOW)
    return Player(
        id=pid,
        tg_id=base.tg_id,
        username=base.username,
        length=Length(cm=length_cm),
        thickness=Thickness(level=base.thickness.level),
        title=title,
        name=name,
        status=PlayerStatus.ACTIVE,
        created_at=base.created_at,
        updated_at=base.updated_at,
    )


def _boss_fight(
    *,
    boss_fight_id: int = 99,
    status: BossFightStatus = BossFightStatus.LOBBY,
    summoner_player_id: int = 1,
    boss_player_id: int = 2,
    initial_boss_length_cm: int = 100,
    current_boss_length_cm: int | None = None,
    current_round: int = 0,
    lobby_ends_at: datetime | None = None,
) -> BossFight:
    return BossFight(
        id=boss_fight_id,
        kind=BossKind.RAID,
        summoner_player_id=summoner_player_id,
        boss_player_id=boss_player_id,
        status=status,
        started_at=_NOW,
        lobby_ends_at=lobby_ends_at
        if lobby_ends_at is not None
        else (_NOW + timedelta(minutes=20)),
        finished_at=None,
        random_seed=42,
        initial_boss_length_cm=initial_boss_length_cm,
        current_boss_length_cm=current_boss_length_cm
        if current_boss_length_cm is not None
        else initial_boss_length_cm,
        current_round=current_round,
    )


def _participant(*, player_id: int, is_summoner: bool = False) -> BossParticipant:
    return BossParticipant(
        boss_fight_id=99,
        player_id=player_id,
        is_summoner=is_summoner,
        length_at_join_cm=25,
        joined_at=_NOW,
    )


def _fluent_bundle() -> IMessageBundle:
    return FluentMessageBundle(locales_dir=Path(__file__).resolve().parents[4] / "locales")


# ============================================================
# Pure-функции: callback_data
# ============================================================


class TestCallbackData:
    def test_round_trip_each_action(self) -> None:
        for action in ("show_lobby", "join", "leave", "cancel"):
            raw = boss_callback_data(action=_as_action(action), boss_fight_id=42)
            parsed = parse_boss_callback_data(raw)
            assert parsed == BossCallbackData(action=_as_action(action), boss_fight_id=42)

    def test_serialize_format(self) -> None:
        assert boss_callback_data(action="join", boss_fight_id=7) == "boss:join:7"

    def test_serialize_callback_under_64_bytes(self) -> None:
        big = boss_callback_data(action="show_lobby", boss_fight_id=9_999_999_999_999_999_999)
        assert len(big.encode()) <= 64

    def test_serialize_rejects_zero_or_negative(self) -> None:
        with pytest.raises(ValueError):
            boss_callback_data(action="join", boss_fight_id=0)
        with pytest.raises(ValueError):
            boss_callback_data(action="join", boss_fight_id=-1)

    def test_serialize_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError):
            boss_callback_data(action="eat_boss", boss_fight_id=1)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "boss",
            "boss:join",
            "boss:join:1:2",
            "x:join:1",
        ],
    )
    def test_parse_rejects_malformed_format(self, raw: str) -> None:
        with pytest.raises(ValueError):
            parse_boss_callback_data(raw)

    def test_parse_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError):
            parse_boss_callback_data("boss:eat_boss:1")

    def test_parse_rejects_non_numeric_id(self) -> None:
        with pytest.raises(ValueError):
            parse_boss_callback_data("boss:join:abc")

    def test_parse_rejects_zero_or_negative_id(self) -> None:
        with pytest.raises(ValueError):
            parse_boss_callback_data("boss:join:0")
        with pytest.raises(ValueError):
            parse_boss_callback_data("boss:join:-3")


class TestIsBossCallback:
    def test_none_returns_false(self) -> None:
        assert is_boss_callback(None) is False

    def test_other_prefix_returns_false(self) -> None:
        assert is_boss_callback("forest:apply_name:1") is False
        assert is_boss_callback("caravan:join:1") is False
        assert is_boss_callback("bosses:join:1") is False  # plural ≠ "boss:"

    def test_boss_prefix_returns_true(self) -> None:
        assert is_boss_callback("boss:join:1") is True
        assert is_boss_callback("boss:show_lobby:42") is True
        assert is_boss_callback("boss:cancel:7") is True

    def test_bare_prefix_alone_is_not_callback(self) -> None:
        # `is_boss_callback("boss")` — без `:` суффикса — это не наш формат.
        assert is_boss_callback("boss") is False


# ============================================================
# BossPresenter — FakeMessageBundle (маркеры)
# ============================================================


class TestBossPresenterFakeBundle:
    """Маркерные тесты — какие ключи и параметры запрашивает презентер."""

    def test_not_registered_uses_correct_key(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        assert presenter.not_registered(locale=_RU) == "ru:bosses-not-registered"

    def test_usage_passes_top_n_pool(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        text = presenter.usage(top_n_pool=30, locale=_EN)
        assert text == "en:bosses-usage[top_n_pool=30]"

    def test_cooldown_rounds_up_minutes(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        # 121 секунд → 3 минуты (round up)
        text = presenter.cooldown(remaining_seconds=121, locale=_RU)
        assert text == "ru:bosses-cooldown[remaining_minutes=3]"

    def test_cooldown_minimum_one_minute(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        text = presenter.cooldown(remaining_seconds=5, locale=_RU)
        assert text == "ru:bosses-cooldown[remaining_minutes=1]"

    def test_already_in_uses_correct_key(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        assert presenter.already_in(locale=_RU) == "ru:bosses-already-in"

    def test_requirement_thickness_passes_required_and_actual(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        text = presenter.requirement_thickness(required=9, actual=4, locale=_EN)
        assert text == "en:bosses-requirement-thickness[actual=4,required=9]"

    def test_requirement_length_passes_required_and_actual_cm(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        text = presenter.requirement_length(required_cm=20, actual_cm=15, locale=_RU)
        assert text == "ru:bosses-requirement-length[actual_cm=15,required_cm=20]"

    def test_player_frozen_uses_correct_key(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        assert presenter.player_frozen(locale=_RU) == "ru:bosses-player-frozen"

    def test_pool_empty_uses_correct_key(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        assert presenter.pool_empty(locale=_EN) == "en:bosses-pool-empty"

    def test_summoned_private_renders_boss_nick_with_title(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        text = presenter.summoned_private(
            boss=_player(pid=2, title=Title.NEWBIE, name=PlayerName(value="Грог")),
            boss_display_name=DisplayName(value="Босс-Дракон"),
            boss_length_cm=80,
            lobby_minutes=20,
            locale=_RU,
        )
        # boss_nick = title + display_name + name
        assert "ru:bosses-summoned-private" in text
        assert "boss_nick=ru:profile-title-newbie Босс-Дракон Грог" in text
        assert "boss_length_cm=80" in text
        assert "lobby_minutes=20" in text

    def test_summoned_announcement_renders_both_nicks(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        text = presenter.summoned_announcement(
            summoner=_player(pid=1, title=Title.NEWBIE),
            summoner_display_name=DisplayName(value="Самми"),
            boss=_player(pid=2, title=Title.NEWBIE, name=PlayerName(value="Бо")),
            boss_display_name=DisplayName(value="Босс"),
            boss_length_cm=100,
            lobby_minutes=20,
            locale=_EN,
        )
        assert "en:bosses-summoned-announcement" in text
        assert "summoner_nick=en:profile-title-newbie Самми" in text
        assert "boss_nick=en:profile-title-newbie Босс Бо" in text
        assert "boss_length_cm=100" in text
        assert "lobby_minutes=20" in text

    def test_announcement_keyboard_has_single_button_with_show_lobby_callback(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        markup = presenter.announcement_keyboard(boss_fight_id=42, locale=_RU)
        assert len(markup.inline_keyboard) == 1
        assert len(markup.inline_keyboard[0]) == 1
        button = markup.inline_keyboard[0][0]
        assert button.text == "ru:bosses-button-show-lobby"
        assert button.callback_data == "boss:show_lobby:42"

    def test_lobby_state_text_renders_open_status(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        boss_fight = _boss_fight(
            lobby_ends_at=_NOW + timedelta(minutes=15, seconds=30),
        )
        text = presenter.lobby_state_text(
            boss_fight=boss_fight,
            raiders_count=3,
            summoner=_player(pid=1),
            summoner_display_name=DisplayName(value="Самми"),
            boss=_player(pid=2),
            boss_display_name=DisplayName(value="Босс"),
            now=_NOW,
            locale=_RU,
        )
        assert "ru:bosses-lobby-state" in text
        # ceil(15.5 min) = 16
        assert "lobby_status=ru:bosses-lobby-status-open[remaining_minutes=16]" in text
        assert "raiders_count=3" in text

    def test_lobby_state_text_renders_closing_status_when_lobby_expired(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        # `lobby_ends_at` строго после `started_at` (инвариант entity);
        # симулируем «закрывается» через `now > lobby_ends_at`.
        boss_fight = _boss_fight(lobby_ends_at=_NOW + timedelta(minutes=1))
        text = presenter.lobby_state_text(
            boss_fight=boss_fight,
            raiders_count=0,
            summoner=_player(pid=1),
            summoner_display_name=DisplayName(value="Самми"),
            boss=_player(pid=2),
            boss_display_name=DisplayName(value="Босс"),
            now=_NOW + timedelta(minutes=2),
            locale=_RU,
        )
        assert "lobby_status=ru:bosses-lobby-status-closing" in text

    def test_lobby_keyboard_has_three_buttons_in_one_row(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        markup = presenter.lobby_keyboard(boss_fight_id=99, locale=_RU)
        assert len(markup.inline_keyboard) == 1
        row = markup.inline_keyboard[0]
        assert len(row) == 3
        assert row[0].text == "ru:bosses-button-join"
        assert row[0].callback_data == "boss:join:99"
        assert row[1].text == "ru:bosses-button-leave"
        assert row[1].callback_data == "boss:leave:99"
        assert row[2].text == "ru:bosses-button-cancel"
        assert row[2].callback_data == "boss:cancel:99"

    def test_battle_started_text_passes_round_seconds_from_cfg(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        cfg = build_valid_balance().bosses
        text = presenter.battle_started_text(
            summoner=_player(pid=1),
            summoner_display_name=DisplayName(value="Самми"),
            boss=_player(pid=2),
            boss_display_name=DisplayName(value="Босс"),
            boss_length_cm=100,
            raiders_count=4,
            cfg=cfg,
            locale=_RU,
        )
        assert "ru:bosses-battle-started" in text
        assert "boss_length_cm=100" in text
        assert "raiders_count=4" in text
        assert f"round_seconds={cfg.round_max_seconds}" in text

    def test_round_tick_text_passes_round_metrics(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        text = presenter.round_tick_text(
            boss=_player(pid=2),
            boss_display_name=DisplayName(value="Босс"),
            round_number=3,
            boss_damage_cm=15,
            boss_length_cm=70,
            eliminated_count=1,
            raiders_alive=4,
            locale=_RU,
        )
        assert "ru:bosses-round-tick" in text
        assert "round_number=3" in text
        assert "boss_damage_cm=15" in text
        assert "boss_length_cm=70" in text
        assert "eliminated_count=1" in text
        assert "raiders_alive=4" in text

    def test_battle_finished_victory_text_uses_victory_key(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        text = presenter.battle_finished_victory_text(
            summoner=_player(pid=1),
            summoner_display_name=DisplayName(value="Самми"),
            boss=_player(pid=2),
            boss_display_name=DisplayName(value="Босс"),
            raiders_alive=3,
            per_raider_grant_cm=33,
            locale=_RU,
        )
        assert "ru:bosses-battle-finished-victory" in text
        assert "raiders_alive=3" in text
        assert "per_raider_grant_cm=33" in text

    def test_battle_finished_defeat_text_uses_defeat_key(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        text = presenter.battle_finished_defeat_text(
            summoner=_player(pid=1),
            summoner_display_name=DisplayName(value="Самми"),
            boss=_player(pid=2),
            boss_display_name=DisplayName(value="Босс"),
            raiders_alive=0,
            total_granted_cm=120,
            locale=_RU,
        )
        assert "ru:bosses-battle-finished-defeat" in text
        assert "raiders_alive=0" in text
        assert "total_granted_cm=120" in text

    def test_count_alive_raiders_returns_len(self) -> None:
        # `count_alive_raiders` — staticmethod без локализации.
        participants = (
            _participant(player_id=10),
            _participant(player_id=11),
            _participant(player_id=12),
        )
        assert BossPresenter.count_alive_raiders(participants) == 3

    def test_count_alive_raiders_zero_for_empty(self) -> None:
        assert BossPresenter.count_alive_raiders(()) == 0

    @pytest.mark.parametrize(
        ("method", "expected_key"),
        [
            ("join_toast_success", "bosses-join-toast-success"),
            ("callback_toast_lobby_closed", "bosses-callback-toast-lobby-closed"),
            ("callback_toast_already_in_fight", "bosses-callback-toast-already-in-fight"),
            ("callback_toast_cannot_join_as_boss", "bosses-callback-toast-cannot-join-as-boss"),
            ("leave_toast_success", "bosses-leave-toast-success"),
            ("leave_toast_summoner_leaves", "bosses-leave-toast-summoner-leaves"),
            ("leave_toast_not_a_participant", "bosses-leave-toast-not-a-participant"),
            ("cancel_message_text", "bosses-cancel-message"),
            ("cancel_toast_success", "bosses-cancel-toast-success"),
            ("cancel_toast_already_cancelled", "bosses-cancel-toast-already-cancelled"),
            ("callback_toast_fight_not_found", "bosses-callback-toast-fight-not-found"),
            ("callback_toast_invalid_state", "bosses-callback-toast-invalid-state"),
            ("callback_toast_not_summoner", "bosses-callback-toast-not-summoner"),
            ("callback_toast_player_not_found", "bosses-callback-toast-player-not-found"),
            ("callback_toast_player_frozen", "bosses-callback-toast-player-frozen"),
            ("callback_toast_generic_error", "bosses-callback-toast-generic-error"),
        ],
    )
    def test_simple_toast_methods_route_to_correct_keys(
        self,
        method: str,
        expected_key: str,
    ) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        result = getattr(presenter, method)(locale=_RU)
        assert result == f"ru:{expected_key}"

    def test_callback_toast_requirement_thickness_passes_required_and_actual(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        text = presenter.callback_toast_requirement_thickness(required=4, actual=2, locale=_EN)
        assert text == "en:bosses-callback-toast-requirement-thickness[actual=2,required=4]"

    def test_callback_toast_requirement_length_passes_required_and_actual_cm(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        text = presenter.callback_toast_requirement_length(required_cm=20, actual_cm=15, locale=_RU)
        assert text == "ru:bosses-callback-toast-requirement-length[actual_cm=15,required_cm=20]"

    def test_render_full_nick_without_title_just_uses_display_name(self) -> None:
        presenter = BossPresenter(bundle=FakeMessageBundle())
        # Используем тот факт, что `summoned_private` дёргает `_render_full_nick`
        # — у player без title и без name nick = display_name.value.
        text = presenter.summoned_private(
            boss=_player(pid=2, title=None, name=None),
            boss_display_name=DisplayName(value="ТолькоИмя"),
            boss_length_cm=50,
            lobby_minutes=20,
            locale=_RU,
        )
        assert "boss_nick=ТолькоИмя" in text


# ============================================================
# BossPresenter — FluentMessageBundle (реальные переводы)
# ============================================================


class TestBossPresenterFluent:
    """Дым-тесты с реальными RU/EN переводами — проверяем, что ключи
    действительно есть в `locales/{ru,en}.ftl` и подстановки работают.
    """

    def test_not_registered_ru_smoke(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        text = presenter.not_registered(locale=_RU)
        # RU-перевод содержит инструкцию `/start`
        assert "/start" in text

    def test_not_registered_en_smoke(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        text = presenter.not_registered(locale=_EN)
        assert "/start" in text

    def test_usage_renders_top_n_pool_in_ru(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        text = presenter.usage(top_n_pool=30, locale=_RU)
        assert "30" in text
        assert "/boss" in text

    def test_usage_renders_top_n_pool_in_en(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        text = presenter.usage(top_n_pool=30, locale=_EN)
        assert "30" in text
        assert "/boss" in text

    def test_cooldown_renders_remaining_minutes_in_ru(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        text = presenter.cooldown(remaining_seconds=600, locale=_RU)
        assert "10" in text  # 600s = 10 min

    def test_requirement_thickness_renders_numbers_in_ru(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        text = presenter.requirement_thickness(required=9, actual=4, locale=_RU)
        assert "9" in text
        assert "4" in text

    def test_requirement_length_renders_cm_in_en(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        text = presenter.requirement_length(required_cm=20, actual_cm=15, locale=_EN)
        assert "20" in text
        assert "15" in text

    def test_announcement_keyboard_uses_localized_label(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        markup_ru = presenter.announcement_keyboard(boss_fight_id=1, locale=_RU)
        markup_en = presenter.announcement_keyboard(boss_fight_id=1, locale=_EN)
        # Локализация различается, callback_data — нет.
        assert markup_ru.inline_keyboard[0][0].text != markup_en.inline_keyboard[0][0].text
        assert markup_ru.inline_keyboard[0][0].callback_data == "boss:show_lobby:1"
        assert markup_en.inline_keyboard[0][0].callback_data == "boss:show_lobby:1"

    def test_lobby_keyboard_uses_localized_labels(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        markup_ru = presenter.lobby_keyboard(boss_fight_id=99, locale=_RU)
        markup_en = presenter.lobby_keyboard(boss_fight_id=99, locale=_EN)
        ru_row = markup_ru.inline_keyboard[0]
        en_row = markup_en.inline_keyboard[0]
        # Тексты разные, callback_data — инвариантна.
        for ru_btn, en_btn in zip(ru_row, en_row, strict=True):
            assert ru_btn.text != en_btn.text
            assert ru_btn.callback_data == en_btn.callback_data

    def test_join_toast_success_renders_in_both_locales(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        ru = presenter.join_toast_success(locale=_RU)
        en = presenter.join_toast_success(locale=_EN)
        assert ru and en
        assert ru != en  # переводы отличаются

    def test_callback_toast_requirement_thickness_renders_numbers(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        text = presenter.callback_toast_requirement_thickness(required=4, actual=2, locale=_RU)
        assert "4" in text
        assert "2" in text

    def test_cancel_toast_success_renders_in_both_locales(self) -> None:
        presenter = BossPresenter(bundle=_fluent_bundle())
        ru = presenter.cancel_toast_success(locale=_RU)
        en = presenter.cancel_toast_success(locale=_EN)
        assert ru and en
        assert ru != en


# ============================================================
# Locale parity (focused on `bosses-*`)
# ============================================================


_LOCALES_DIR: Path = Path(__file__).resolve().parents[4] / "locales"


def _bosses_keys(ftl_path: Path) -> set[str]:
    resource = fluent_parse(ftl_path.read_text(encoding="utf-8"))
    return {
        entry.id.name
        for entry in resource.body
        if isinstance(entry, Message)
        and not isinstance(entry, Term)
        and entry.id.name.startswith("bosses-")
    }


class TestBossesLocaleParity:
    """RU↔EN ключи `bosses-*` должны совпадать множествами."""

    def test_full_parity(self) -> None:
        ru = _bosses_keys(_LOCALES_DIR / "ru.ftl")
        en = _bosses_keys(_LOCALES_DIR / "en.ftl")
        only_ru = sorted(ru - en)
        only_en = sorted(en - ru)
        assert only_ru == [], f"bosses-* только в ru.ftl: {only_ru}"
        assert only_en == [], f"bosses-* только в en.ftl: {only_en}"

    def test_minimum_count_sanity(self) -> None:
        # Snapshot на момент D.6 — 39 ключей. Регрессия ниже 30 = что-то
        # удалили без обновления handler-а / презентера.
        ru = _bosses_keys(_LOCALES_DIR / "ru.ftl")
        assert len(ru) >= 30, f"bosses-* в ru.ftl всего {len(ru)} — подозрительно мало"
