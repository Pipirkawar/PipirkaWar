"""Unit-тесты презентеров `bot/presenters/forest.py` (Спринт 1.3.D)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.forest import ForestRunFinished
from pipirik_wars.bot.presenters.forest import (
    ForestCallbackAction,
    ForestCallbackData,
    build_finish_keyboard,
    forest_callback_data,
    has_finish_keyboard,
    localized_rarity,
    parse_forest_callback_data,
    render_forest_finished,
    render_forest_started,
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

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


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


class TestRenderForestStarted:
    def test_newbie_without_title_or_name(self) -> None:
        player = _player()
        text = render_forest_started(
            player=player,
            display_name=DisplayName(value="Пипирик"),
            cooldown_minutes=15,
        )
        assert text == "🌲 Пипирик ушёл в лес на 15 минут..."

    def test_with_title_and_name(self) -> None:
        player = _player(title=Title.NEWBIE, name=PlayerName(value="Иванушка"))
        text = render_forest_started(
            player=player,
            display_name=DisplayName(value="Бананчик"),
            cooldown_minutes=20,
        )
        assert text == "🌲 Новичок Бананчик Иванушка ушёл в лес на 20 минут..."

    def test_minimum_cooldown_minutes(self) -> None:
        player = _player()
        text = render_forest_started(
            player=player,
            display_name=DisplayName(value="Пипирик"),
            cooldown_minutes=10,
        )
        assert text.endswith("на 10 минут...")


class TestRenderForestFinished:
    def test_no_drop_first_return_with_title_grant(self) -> None:
        before = _player(length_cm=2)
        after = _player(length_cm=7, title=Title.NEWBIE)
        result = _finished(
            before=before,
            after=after,
            drop=NoDrop(),
            granted_title=True,
            length_delta_cm=5,
        )
        text = render_forest_finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
        )
        # Длина начислена, титул появился, дропа нет.
        assert "Новичок Пипирик вернулся из леса" in text
        assert "Длина: +5 см (было 2, стало 7)" in text
        assert "Получен титул: Новичок" in text
        assert "Нашёл" not in text

    def test_item_drop_shows_localized_rarity(self) -> None:
        before = _player(length_cm=10)
        after = _player(length_cm=15, title=Title.NEWBIE)
        item = Item(
            id="item.head.berserker",
            display_name="Шлем Берсерка",
            slot=Slot.HAT,
            rarity=Rarity.EPIC,
        )
        result = _finished(
            before=before,
            after=after,
            drop=ItemDrop(item=item),
        )
        text = render_forest_finished(
            result=result,
            display_name_after=DisplayName(value="Бананчик"),
        )
        assert "Нашёл: Шлем Берсерка [эпический]" in text

    def test_name_drop_auto_applied_for_newbie(self) -> None:
        # У новичка имени не было, FinishForestRun применил его автоматически.
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
        text = render_forest_finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
        )
        # После применения имя в нике, отдельной строкой — «получено».
        assert "Новичок Пипирик Коляндр вернулся из леса" in text
        assert "Получено имя: Коляндр" in text
        assert "Нашёл имя" not in text

    def test_name_drop_not_applied_when_player_has_name(self) -> None:
        before = _player(name=PlayerName(value="Старое"), title=Title.NEWBIE)
        after = before  # имя не применили — `granted_name=False`
        drop = NameDrop(name=Name(value="Новое"))
        result = _finished(
            before=before,
            after=after,
            drop=drop,
            granted_title=False,
            granted_name=False,
        )
        text = render_forest_finished(
            result=result,
            display_name_after=DisplayName(value="Пипирик"),
        )
        assert "Нашёл имя: Новое" in text
        assert "Получено имя" not in text


class TestBuildFinishKeyboard:
    def test_no_drop_returns_none(self) -> None:
        before = _player()
        after = _player()
        result = _finished(before=before, after=after, drop=NoDrop())
        assert build_finish_keyboard(result) is None

    def test_name_drop_auto_applied_returns_none(self) -> None:
        before = _player(name=None)
        after = _player(name=PlayerName(value="X"))
        result = _finished(
            before=before,
            after=after,
            drop=NameDrop(name=Name(value="X")),
            granted_name=True,
        )
        assert build_finish_keyboard(result) is None

    def test_item_drop_two_buttons(self) -> None:
        before = _player()
        after = _player()
        item = Item(
            id="item.head.pickaxe",
            display_name="Кирка",
            slot=Slot.HAT,
            rarity=Rarity.COMMON,
        )
        result = _finished(before=before, after=after, drop=ItemDrop(item=item))
        kb = build_finish_keyboard(result)
        assert kb is not None
        assert len(kb.inline_keyboard) == 1
        row = kb.inline_keyboard[0]
        assert [b.text for b in row] == ["Надеть", "Выбросить"]
        callbacks = [b.callback_data for b in row]
        assert callbacks == ["forest:equip_item:11", "forest:drop_item:11"]

    def test_name_drop_replacement_two_buttons(self) -> None:
        before = _player(name=PlayerName(value="Старое"))
        after = before
        result = _finished(
            before=before,
            after=after,
            drop=NameDrop(name=Name(value="Новое")),
            granted_name=False,
        )
        kb = build_finish_keyboard(result)
        assert kb is not None
        row = kb.inline_keyboard[0]
        assert [b.text for b in row] == ["Заменить", "Выбросить"]
        callbacks = [b.callback_data for b in row]
        assert callbacks == ["forest:apply_name:11", "forest:drop_name:11"]


class TestCallbackData:
    def test_round_trip_each_action(self) -> None:
        for action in ("equip_item", "drop_item", "apply_name", "drop_name"):
            raw = forest_callback_data(_as_action(action), run_id=42)
            parsed = parse_forest_callback_data(raw)
            assert parsed == ForestCallbackData(action=_as_action(action), run_id=42)

    def test_serialize_format(self) -> None:
        assert forest_callback_data("apply_name", 7) == "forest:apply_name:7"

    def test_serialize_callback_under_64_bytes(self) -> None:
        # Самое длинное реальное значение: forest:apply_name:<19digits>
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


class TestHelpers:
    def test_localized_rarity_all_known(self) -> None:
        assert localized_rarity(Rarity.COMMON) == "обычный"
        assert localized_rarity(Rarity.RARE) == "редкий"
        assert localized_rarity(Rarity.EPIC) == "эпический"

    def test_has_finish_keyboard_no_drop(self) -> None:
        assert has_finish_keyboard(NoDrop(), granted_name=False) is False

    def test_has_finish_keyboard_item(self) -> None:
        item = Item(
            id="item.head.x",
            display_name="X",
            slot=Slot.HAT,
            rarity=Rarity.COMMON,
        )
        assert has_finish_keyboard(ItemDrop(item=item), granted_name=False) is True

    def test_has_finish_keyboard_name_auto_applied(self) -> None:
        assert has_finish_keyboard(NameDrop(name=Name(value="X")), granted_name=True) is False

    def test_has_finish_keyboard_name_not_applied(self) -> None:
        assert has_finish_keyboard(NameDrop(name=Name(value="X")), granted_name=False) is True
