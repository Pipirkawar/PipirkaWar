"""Юнит-тесты `bot/presenters/forest.py` (Спринт 1.3.D → 1.5.E).

Покрываем:

1. Pure-функции `forest_callback_data` / `parse_forest_callback_data` —
   серилизация/парсинг `callback_data`, инварианты (≤ 64 байт, отказ
   на zero/negative run_id, отказ на unknown action, отказ на bad format).
2. `has_finish_keyboard(...)` — должна ли быть клавиатура для каждого
   варианта `Drop`.
3. `ForestPresenter` через **`FakeMessageBundle`** — проверяем, что
   презентер просит правильные ключи и параметры (маркер
   `<locale>:<key>[k=v,...]` детерминистичен и не зависит от реальных
   переводов).
4. `ForestPresenter` через **`FluentMessageBundle`** (RU + EN) —
   интеграционная проверка реальных переводов: вывод содержит ожидаемые
   подстроки в обеих локалях.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pipirik_wars.application.forest import ForestRunFinished
from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.forest import (
    ForestCallbackAction,
    ForestCallbackData,
    ForestPresenter,
    forest_callback_data,
    has_finish_keyboard,
    parse_forest_callback_data,
)
from pipirik_wars.domain.forest import (
    ForestRun,
    ForestRunStatus,
    Item,
    ItemDrop,
    Name,
    NameDrop,
    NoDrop,
    Rarity,
    Slot,
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

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_RU = Locale("ru")
_EN = Locale("en")


def _as_action(raw: str) -> ForestCallbackAction:
    """Сужает `str` до `ForestCallbackAction` для типобезопасных тестов."""
    if raw == "equip_item":
        return "equip_item"
    if raw == "drop_item":
        return "drop_item"
    if raw == "apply_name":
        return "apply_name"
    if raw == "drop_name":
        return "drop_name"
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


def _run(
    *,
    rid: int = 11,
    player_id: int = 1,
    drop: NoDrop | ItemDrop | NameDrop | None = None,
    length_delta_cm: int = 5,
) -> ForestRun:
    return ForestRun(
        id=rid,
        player_id=player_id,
        status=ForestRunStatus.FINISHED,
        started_at=_NOW - timedelta(minutes=15),
        ends_at=_NOW,
        finished_at=_NOW,
        branch_name="normal",
        length_delta_cm=length_delta_cm,
        drop=drop or NoDrop(),
    )


def _finished(
    *,
    before: Player,
    after: Player,
    drop: NoDrop | ItemDrop | NameDrop,
    granted_title: bool = False,
    granted_name: bool = False,
    rid: int = 11,
    length_delta_cm: int = 5,
) -> ForestRunFinished:
    assert before.id is not None
    return ForestRunFinished(
        run=_run(
            rid=rid,
            player_id=before.id,
            drop=drop,
            length_delta_cm=length_delta_cm,
        ),
        player_before=before,
        player_after=after,
        granted_title=granted_title,
        granted_name=granted_name,
        was_already_finished=False,
    )


def _fluent_bundle() -> IMessageBundle:
    return FluentMessageBundle(locales_dir=Path(__file__).resolve().parents[4] / "locales")


# ============================================================
# Pure-функции: callback_data
# ============================================================


class TestCallbackData:
    def test_round_trip_each_action(self) -> None:
        for action in ("equip_item", "drop_item", "apply_name", "drop_name"):
            raw = forest_callback_data(_as_action(action), run_id=42)
            parsed = parse_forest_callback_data(raw)
            assert parsed == ForestCallbackData(action=_as_action(action), run_id=42)

    def test_serialize_format(self) -> None:
        assert forest_callback_data("apply_name", 7) == "forest:apply_name:7"

    def test_serialize_callback_under_64_bytes(self) -> None:
        big = forest_callback_data("apply_name", 9_999_999_999_999_999_999)
        assert len(big.encode()) <= 64

    def test_serialize_rejects_zero_or_negative(self) -> None:
        with pytest.raises(ValueError):
            forest_callback_data("apply_name", 0)
        with pytest.raises(ValueError):
            forest_callback_data("apply_name", -1)

    def test_serialize_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError):
            forest_callback_data("eat_item", 1)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "forest",
            "forest:apply_name",
            "forest:apply_name:1:2",
            "x:apply_name:1",
        ],
    )
    def test_parse_rejects_malformed_format(self, raw: str) -> None:
        with pytest.raises(ValueError):
            parse_forest_callback_data(raw)

    def test_parse_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError):
            parse_forest_callback_data("forest:eat_item:1")

    def test_parse_rejects_non_numeric_run_id(self) -> None:
        with pytest.raises(ValueError):
            parse_forest_callback_data("forest:apply_name:abc")

    def test_parse_rejects_zero_or_negative_run_id(self) -> None:
        with pytest.raises(ValueError):
            parse_forest_callback_data("forest:apply_name:0")
        with pytest.raises(ValueError):
            parse_forest_callback_data("forest:apply_name:-3")


class TestHasFinishKeyboard:
    def test_no_drop(self) -> None:
        assert has_finish_keyboard(NoDrop(), granted_name=False) is False

    def test_item_drop(self) -> None:
        item = Item(
            id="item.head.x",
            display_name="X",
            slot=Slot.HAT,
            rarity=Rarity.COMMON,
        )
        assert has_finish_keyboard(ItemDrop(item=item), granted_name=False) is True

    def test_name_drop_auto_applied(self) -> None:
        assert has_finish_keyboard(NameDrop(name=Name(value="X")), granted_name=True) is False

    def test_name_drop_not_applied(self) -> None:
        assert has_finish_keyboard(NameDrop(name=Name(value="X")), granted_name=False) is True


# ============================================================
# ForestPresenter — FakeMessageBundle (маркеры)
# ============================================================


class TestForestPresenterFakeBundle:
    def test_group_uses_forest_group_key(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        assert presenter.group(locale=_RU) == "ru:forest-group"
        assert presenter.other(locale=_RU) == "ru:forest-other"
        assert presenter.not_registered(locale=_RU) == "ru:forest-not-registered"
        assert presenter.already_in(locale=_RU) == "ru:forest-already-in"

    def test_started_passes_nick_and_cooldown(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        text = presenter.started(
            player=_player(),
            display_name=DisplayName(value="Пипирик"),
            cooldown_minutes=15,
            locale=_RU,
        )
        # Без титула → nick = display_name.value
        assert "ru:forest-started" in text
        assert "nick=Пипирик" in text
        assert "cooldown_minutes=15" in text

    def test_started_with_title_uses_title_message_key(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        text = presenter.started(
            player=_player(title=Title.NEWBIE, name=PlayerName(value="Иван")),
            display_name=DisplayName(value="Бананчик"),
            cooldown_minutes=20,
            locale=_RU,
        )
        # Локализованный титул берётся из bundle: «ru:profile-title-newbie»
        assert "nick=ru:profile-title-newbie Бананчик Иван" in text

    def test_started_fallback_uses_fallback_key(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        text = presenter.started_fallback(cooldown_minutes=15, locale=_EN)
        assert text == "en:forest-started-fallback[cooldown_minutes=15]"

    def test_finished_no_drop_with_title_grant(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        before = _player(length_cm=2)
        after = _player(length_cm=7, title=Title.NEWBIE)
        result = _finished(
            before=before,
            after=after,
            drop=NoDrop(),
            granted_title=True,
            length_delta_cm=5,
        )
        text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
            locale=_RU,
        )
        # Нашёлся header + length + title-granted
        assert "ru:forest-finished-header" in text
        assert "ru:forest-finished-length" in text
        assert "length_delta_cm=5" in text
        assert "length_before_cm=2" in text
        assert "length_after_cm=7" in text
        assert "ru:forest-finished-title-granted" in text
        # Нет item-found / name-found / name-granted
        assert "forest-finished-item-found" not in text
        assert "forest-finished-name" not in text

    def test_finished_item_drop_renders_localized_rarity(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        before = _player(length_cm=10)
        after = _player(length_cm=15, title=Title.NEWBIE)
        item = Item(
            id="item.head.berserker",
            display_name="Шлем Берсерка",
            slot=Slot.HAT,
            rarity=Rarity.EPIC,
        )
        result = _finished(before=before, after=after, drop=ItemDrop(item=item))
        text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Бананчик"),
            locale=_RU,
        )
        assert "ru:forest-finished-item-found" in text
        assert "item_name=Шлем Берсерка" in text
        # Локализованная редкость = маркер «ru:forest-rarity-epic»
        assert "rarity=ru:forest-rarity-epic" in text

    def test_finished_name_drop_auto_applied_uses_name_granted(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        before = _player(name=None)
        after = _player(name=PlayerName(value="Коляндр"), title=Title.NEWBIE)
        drop = NameDrop(name=Name(value="Коляндр"))
        result = _finished(
            before=before,
            after=after,
            drop=drop,
            granted_title=True,
            granted_name=True,
        )
        text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
            locale=_RU,
        )
        assert "ru:forest-finished-name-granted" in text
        assert "name=Коляндр" in text
        # Не должно быть «name-found» (это для замены)
        assert "forest-finished-name-found" not in text

    def test_finished_name_drop_replacement_uses_name_found(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        before = _player(name=PlayerName(value="Старое"), title=Title.NEWBIE)
        after = before  # имя не применили
        drop = NameDrop(name=Name(value="Новое"))
        result = _finished(
            before=before,
            after=after,
            drop=drop,
            granted_title=False,
            granted_name=False,
        )
        text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
            locale=_RU,
        )
        assert "ru:forest-finished-name-found" in text
        assert "name=Новое" in text
        # Не должно быть «name-granted» (это для авто-применения)
        assert "forest-finished-name-granted" not in text

    def test_finish_keyboard_no_drop_returns_none(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        before = _player()
        after = _player()
        result = _finished(before=before, after=after, drop=NoDrop())
        assert presenter.finish_keyboard(result, locale=_RU) is None

    def test_finish_keyboard_name_drop_auto_applied_returns_none(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        before = _player(name=None)
        after = _player(name=PlayerName(value="X"))
        result = _finished(
            before=before,
            after=after,
            drop=NameDrop(name=Name(value="X")),
            granted_name=True,
        )
        assert presenter.finish_keyboard(result, locale=_RU) is None

    def test_finish_keyboard_item_uses_localized_labels_invariant_callback(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        before = _player()
        after = _player()
        item = Item(
            id="item.head.pickaxe",
            display_name="Кирка",
            slot=Slot.HAT,
            rarity=Rarity.COMMON,
        )
        result = _finished(before=before, after=after, drop=ItemDrop(item=item))
        kb = presenter.finish_keyboard(result, locale=_RU)
        assert kb is not None
        assert len(kb.inline_keyboard) == 1
        row = kb.inline_keyboard[0]
        # Маркеры FakeMessageBundle для подписей кнопок
        assert [b.text for b in row] == ["ru:forest-button-equip", "ru:forest-button-drop-item"]
        # callback_data — invariant, не зависит от локали
        assert [b.callback_data for b in row] == [
            "forest:equip_item:11",
            "forest:drop_item:11",
        ]

    def test_finish_keyboard_name_replacement_uses_localized_labels(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        before = _player(name=PlayerName(value="Старое"))
        after = before
        result = _finished(
            before=before,
            after=after,
            drop=NameDrop(name=Name(value="Новое")),
            granted_name=False,
        )
        kb = presenter.finish_keyboard(result, locale=_EN)
        assert kb is not None
        row = kb.inline_keyboard[0]
        assert [b.text for b in row] == [
            "en:forest-button-replace-name",
            "en:forest-button-drop-name",
        ]
        assert [b.callback_data for b in row] == [
            "forest:apply_name:11",
            "forest:drop_name:11",
        ]

    def test_finish_keyboard_item_callback_data_invariant_across_locales(self) -> None:
        """Подписи кнопок переключаются по локали, а `callback_data` — нет."""
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        item = Item(
            id="item.head.x",
            display_name="X",
            slot=Slot.HAT,
            rarity=Rarity.COMMON,
        )
        result = _finished(
            before=_player(),
            after=_player(),
            drop=ItemDrop(item=item),
            rid=42,
        )
        kb_ru = presenter.finish_keyboard(result, locale=_RU)
        kb_en = presenter.finish_keyboard(result, locale=_EN)
        assert kb_ru is not None
        assert kb_en is not None
        ru_row = kb_ru.inline_keyboard[0]
        en_row = kb_en.inline_keyboard[0]
        # Подписи разные...
        assert [b.text for b in ru_row] != [b.text for b in en_row]
        # ...а callback_data одинаковые.
        assert [b.callback_data for b in ru_row] == [b.callback_data for b in en_row]

    @pytest.mark.parametrize(
        ("method", "expected_key"),
        [
            ("toast_name_applied", "forest-toast-name-applied"),
            ("toast_name_already_applied", "forest-toast-name-already-applied"),
            ("toast_name_dropped", "forest-toast-name-dropped"),
            ("toast_item_dropped", "forest-toast-item-dropped"),
            ("toast_item_equipped_placeholder", "forest-toast-item-equipped-placeholder"),
            ("toast_foreign_button", "forest-toast-foreign-button"),
            ("toast_run_not_found", "forest-toast-run-not-found"),
            ("toast_drop_mismatch", "forest-toast-drop-mismatch"),
            ("toast_player_not_found", "forest-toast-player-not-found"),
        ],
    )
    def test_toast_methods_route_to_correct_keys(self, method: str, expected_key: str) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        toast = getattr(presenter, method)(locale=_RU)
        assert toast == f"ru:{expected_key}"

    def test_localized_rarity_method_routes_per_locale(self) -> None:
        presenter = ForestPresenter(bundle=FakeMessageBundle())
        assert presenter.localized_rarity(Rarity.COMMON, locale=_RU) == "ru:forest-rarity-common"
        assert presenter.localized_rarity(Rarity.RARE, locale=_EN) == "en:forest-rarity-rare"
        assert presenter.localized_rarity(Rarity.EPIC, locale=_RU) == "ru:forest-rarity-epic"


# ============================================================
# ForestPresenter — FluentMessageBundle (RU + EN, реальные переводы)
# ============================================================


class TestForestPresenterFluent:
    def test_chat_branches_ru(self) -> None:
        presenter = ForestPresenter(bundle=_fluent_bundle())
        assert "/forest" in presenter.group(locale=_RU)
        assert "личке" in presenter.group(locale=_RU)
        assert "/start" in presenter.not_registered(locale=_RU)
        assert "лесу" in presenter.already_in(locale=_RU)

    def test_chat_branches_en(self) -> None:
        presenter = ForestPresenter(bundle=_fluent_bundle())
        assert "/forest" in presenter.group(locale=_EN)
        assert "private chat" in presenter.group(locale=_EN)
        assert "/start" in presenter.not_registered(locale=_EN)
        assert "forest" in presenter.already_in(locale=_EN)

    def test_started_renders_ru(self) -> None:
        presenter = ForestPresenter(bundle=_fluent_bundle())
        text = presenter.started(
            player=_player(),
            display_name=DisplayName(value="Пипирик"),
            cooldown_minutes=15,
            locale=_RU,
        )
        assert "Пипирик ушёл в лес на 15 минут" in text

    def test_started_renders_en(self) -> None:
        presenter = ForestPresenter(bundle=_fluent_bundle())
        text = presenter.started(
            player=_player(title=Title.NEWBIE, name=PlayerName(value="Ivan")),
            display_name=DisplayName(value="Banana"),
            cooldown_minutes=15,
            locale=_EN,
        )
        # Локализованный титул EN = "Newbie".
        assert "Newbie Banana Ivan went to the forest for 15 minutes" in text

    def test_finished_no_drop_ru_smoke(self) -> None:
        presenter = ForestPresenter(bundle=_fluent_bundle())
        before = _player(length_cm=2)
        after = _player(length_cm=7, title=Title.NEWBIE)
        result = _finished(
            before=before, after=after, drop=NoDrop(), granted_title=True, length_delta_cm=5
        )
        text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
            locale=_RU,
        )
        assert "Новичок Пипирик вернулся из леса" in text
        assert "+5 см (было 2, стало 7)" in text
        assert "Получен титул: Новичок" in text

    def test_finished_item_drop_en(self) -> None:
        presenter = ForestPresenter(bundle=_fluent_bundle())
        before = _player(length_cm=10)
        after = _player(length_cm=15, title=Title.NEWBIE)
        item = Item(
            id="item.head.berserker",
            display_name="Berserker Helm",
            slot=Slot.HAT,
            rarity=Rarity.EPIC,
        )
        result = _finished(before=before, after=after, drop=ItemDrop(item=item))
        text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Banana"),
            locale=_EN,
        )
        assert "Found: Berserker Helm [epic]" in text
        # Не должно быть кириллицы в EN-выводе.
        for char in text:
            assert not ("\u0400" <= char <= "\u04ff"), f"unexpected cyrillic char {char!r} in EN"

    def test_finished_name_drop_replacement_ru(self) -> None:
        presenter = ForestPresenter(bundle=_fluent_bundle())
        before = _player(name=PlayerName(value="Старое"), title=Title.NEWBIE)
        after = before
        result = _finished(
            before=before,
            after=after,
            drop=NameDrop(name=Name(value="Новое")),
            granted_name=False,
        )
        text = presenter.finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
            locale=_RU,
        )
        assert "Нашёл имя: Новое" in text
        assert "Получено имя" not in text

    def test_finish_keyboard_uses_localized_labels_ru(self) -> None:
        presenter = ForestPresenter(bundle=_fluent_bundle())
        item = Item(
            id="item.head.x",
            display_name="X",
            slot=Slot.HAT,
            rarity=Rarity.COMMON,
        )
        result = _finished(before=_player(), after=_player(), drop=ItemDrop(item=item), rid=11)
        kb = presenter.finish_keyboard(result, locale=_RU)
        assert kb is not None
        labels = [b.text for b in kb.inline_keyboard[0]]
        assert labels == ["Надеть", "Выбросить"]
        callbacks = [b.callback_data for b in kb.inline_keyboard[0]]
        assert callbacks == ["forest:equip_item:11", "forest:drop_item:11"]

    def test_finish_keyboard_uses_localized_labels_en(self) -> None:
        presenter = ForestPresenter(bundle=_fluent_bundle())
        item = Item(
            id="item.head.x",
            display_name="X",
            slot=Slot.HAT,
            rarity=Rarity.COMMON,
        )
        result = _finished(before=_player(), after=_player(), drop=ItemDrop(item=item), rid=11)
        kb = presenter.finish_keyboard(result, locale=_EN)
        assert kb is not None
        labels = [b.text for b in kb.inline_keyboard[0]]
        assert labels == ["Equip", "Drop"]
        # callback_data — тот же.
        callbacks = [b.callback_data for b in kb.inline_keyboard[0]]
        assert callbacks == ["forest:equip_item:11", "forest:drop_item:11"]

    def test_localized_rarity_ru_en(self) -> None:
        presenter = ForestPresenter(bundle=_fluent_bundle())
        assert presenter.localized_rarity(Rarity.COMMON, locale=_RU) == "обычный"
        assert presenter.localized_rarity(Rarity.RARE, locale=_RU) == "редкий"
        assert presenter.localized_rarity(Rarity.EPIC, locale=_RU) == "эпический"
        assert presenter.localized_rarity(Rarity.COMMON, locale=_EN) == "common"
        assert presenter.localized_rarity(Rarity.RARE, locale=_EN) == "rare"
        assert presenter.localized_rarity(Rarity.EPIC, locale=_EN) == "epic"
