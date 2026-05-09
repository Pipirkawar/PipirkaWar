"""Юнит-тесты `bot/presenters/inventory.py` (Спринт 3.4-D, ГДД §2.6 + §2.8).

Покрываем:

1. `InventoryPresenter.{group,other,not_registered,empty}` дают строки
   из `.ftl`, отличные между RU и EN.
2. `card()` — целостный рендер: header + секции «Предметы» / «Свитки»
   + строки; пустые секции скрываются; локализованный титул слотов
   и редкостей реально подставлен; `+N`-суффикс присутствует только
   для `enchant_level > 0`.
3. RU/EN parity: те же поля, но локализованные строки разные (для
   проверки, что `IMessageBundle` действительно ходит в нужный `.ftl`).
4. `keyboard()` — `None` при пустом инвентаре; ровно одна кнопка
   на предмет, callback `inv:enchant:<item_id>`.
5. `inventory_callback_data` / `parse_inventory_callback_data` —
   round-trip; rejection на мусор / `:` в `item_id` / превышение лимита 64 байт.
6. `is_inventory_callback` — корректно отделяет от других префиксов.
7. `enchant_suffix` — `+0` → пустая строка; `+5` → ` +5` (с лидирующим пробелом).
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.inventory import InventoryView, ItemView, ScrollView
from pipirik_wars.bot.presenters.inventory import (
    InventoryPresenter,
    enchant_suffix,
    inventory_callback_data,
    is_inventory_callback,
    parse_inventory_callback_data,
)
from pipirik_wars.domain.balance.config import Rarity, Slot
from pipirik_wars.domain.inventory import ItemCategory
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle

_RU = Locale("ru")
_EN = Locale("en")


def _fluent_bundle() -> IMessageBundle:
    """Реальный FluentMessageBundle поверх locales/{ru,en}.ftl."""
    return FluentMessageBundle(locales_dir=Path(__file__).resolve().parents[4] / "locales")


def _item(
    *,
    item_id: str = "item.right_hand.test_1",
    display_name: str = "Меч",
    category: ItemCategory = ItemCategory.WEAPON,
    slot: Slot = Slot.RIGHT_HAND,
    rarity: Rarity = Rarity.RARE,
    enchant_level: int = 0,
) -> ItemView:
    return ItemView(
        item_id=item_id,
        display_name=display_name,
        category=category,
        slot=slot,
        rarity=rarity,
        enchant_level=enchant_level,
    )


def _scroll(
    *,
    scroll_id: str = "weapon_scroll:regular",
    category: str = "weapon_scroll",
    blessed: bool = False,
    qty: int = 3,
) -> ScrollView:
    return ScrollView(scroll_id=scroll_id, category=category, blessed=blessed, qty=qty)


# ───────────────── chat-branch ключи через FakeMessageBundle ─────────────────


class TestInventoryPresenterChatBranches:
    """Проверяем, какие именно ключи ходят через `IMessageBundle`."""

    def _make(self) -> InventoryPresenter:
        return InventoryPresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))

    def test_group_uses_inventory_group_key(self) -> None:
        assert self._make().group(locale=_RU) == "ru:inventory-group"

    def test_other_uses_inventory_other_key(self) -> None:
        assert self._make().other(locale=_EN) == "en:inventory-other"

    def test_not_registered_uses_inventory_not_registered_key(self) -> None:
        assert self._make().not_registered(locale=_RU) == "ru:inventory-not-registered"

    def test_empty_uses_inventory_empty_key(self) -> None:
        assert self._make().empty(locale=_RU) == "ru:inventory-empty"


# ───────────────── card-rendering через реальный FluentMessageBundle ─────────


class TestInventoryPresenterCardRu:
    """RU-рендер карточки `/inventory`."""

    def test_card_includes_counts_and_section_headers_ru(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(
            items=(_item(),),
            scrolls=(_scroll(),),
        )
        text = presenter.card(view, locale=_RU)
        assert "🎒" in text
        assert "Предметов: 1" in text
        assert "Стэков свитков: 1" in text
        assert "📦 Предметы:" in text
        assert "📜 Свитки:" in text

    def test_card_item_line_shows_display_name_slot_and_rarity_ru(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(
            items=(
                _item(
                    display_name="Шапка воеводы",
                    slot=Slot.HAT,
                    rarity=Rarity.EPIC,
                    enchant_level=0,
                ),
            ),
            scrolls=(),
        )
        text = presenter.card(view, locale=_RU)
        assert "Шапка воеводы" in text
        assert "голова" in text
        assert "эпическое" in text

    def test_card_item_line_includes_plus_n_suffix_when_enchanted_ru(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(
            items=(_item(display_name="Меч", enchant_level=5),),
            scrolls=(),
        )
        text = presenter.card(view, locale=_RU)
        assert "Меч +5" in text

    def test_card_item_line_omits_suffix_for_level_zero_ru(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(
            items=(_item(display_name="Меч", enchant_level=0),),
            scrolls=(),
        )
        text = presenter.card(view, locale=_RU)
        assert "Меч</b>" in text
        assert "Меч +" not in text

    def test_card_scroll_line_regular_ru(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(
            items=(),
            scrolls=(_scroll(category="weapon_scroll", blessed=False, qty=3),),
        )
        text = presenter.card(view, locale=_RU)
        assert "свиток на оружие" in text
        assert "× 3" in text

    def test_card_scroll_line_blessed_ru(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(
            items=(),
            scrolls=(_scroll(category="armor_scroll", blessed=True, qty=1),),
        )
        text = presenter.card(view, locale=_RU)
        assert "благословлённый свиток на броню" in text
        assert "× 1" in text

    def test_card_hides_items_section_if_no_items_ru(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(
            items=(),
            scrolls=(_scroll(),),
        )
        text = presenter.card(view, locale=_RU)
        assert "📦 Предметы:" not in text
        assert "📜 Свитки:" in text

    def test_card_hides_scrolls_section_if_no_scrolls_ru(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(
            items=(_item(),),
            scrolls=(),
        )
        text = presenter.card(view, locale=_RU)
        assert "📦 Предметы:" in text
        assert "📜 Свитки:" not in text

    def test_card_renders_all_slots_and_rarities_ru(self) -> None:
        # Гарантия, что для каждого Slot/Rarity есть `inventory-slot-*` /
        # `inventory-rarity-*` ключ — иначе FluentMessageBundle бросит.
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        items = tuple(
            _item(
                item_id=f"item.{slot.value}.test",
                slot=slot,
                rarity=rarity,
                enchant_level=0,
            )
            for slot in Slot
            for rarity in Rarity
        )
        view = InventoryView(items=items, scrolls=())
        text = presenter.card(view, locale=_RU)
        assert text  # рендер прошёл без MessageKeyError


class TestInventoryPresenterCardEn:
    """EN-рендер карточки `/inventory` — RU/EN parity."""

    def test_card_in_english_has_no_cyrillic(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(
            items=(_item(display_name="Sword", enchant_level=3),),
            scrolls=(_scroll(category="weapon_scroll", blessed=False, qty=2),),
        )
        text = presenter.card(view, locale=_EN)
        assert "Sword +3" in text
        # Ни одной кириллической буквы в карточке.
        assert not any(0x0400 <= ord(c) <= 0x04FF for c in text)

    def test_card_blessed_scroll_in_english(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(
            items=(),
            scrolls=(_scroll(category="jewelry_scroll", blessed=True, qty=1),),
        )
        text = presenter.card(view, locale=_EN)
        # «blessed» / «jewelry» в EN-локали должны присутствовать.
        assert "blessed" in text.lower() or "Blessed" in text
        assert "jewelry" in text.lower()


class TestInventoryPresenterEmpty:
    """Пустой инвентарь — отдельный метод `empty(...)`, не `card(...)`."""

    def test_empty_message_ru_mentions_forest_or_mountains(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        msg = presenter.empty(locale=_RU)
        assert "пуст" in msg.lower()

    def test_empty_message_en_no_cyrillic(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        msg = presenter.empty(locale=_EN)
        assert msg
        assert not any(0x0400 <= ord(c) <= 0x04FF for c in msg)


# ───────────────────────── Inline keyboard ─────────────────────────


class TestInventoryPresenterKeyboard:
    def test_keyboard_is_none_when_no_items(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(items=(), scrolls=(_scroll(),))
        assert presenter.keyboard(view, locale=_RU) is None

    def test_keyboard_has_one_button_per_item(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        items = (
            _item(item_id="item.right_hand.a", display_name="Меч", enchant_level=2),
            _item(
                item_id="item.hat.b",
                display_name="Шапка",
                slot=Slot.HAT,
                category=ItemCategory.ARMOR,
                enchant_level=0,
            ),
        )
        view = InventoryView(items=items, scrolls=())
        kb = presenter.keyboard(view, locale=_RU)
        assert kb is not None
        rows = kb.inline_keyboard
        assert len(rows) == 2
        # Кнопка предмета: callback_data = `inv:enchant:<item_id>`.
        assert rows[0][0].callback_data == "inv:enchant:item.right_hand.a"
        assert rows[1][0].callback_data == "inv:enchant:item.hat.b"
        # Текст кнопки содержит display_name + (опц.) +N.
        assert "Меч +2" in rows[0][0].text
        assert "Шапка" in rows[1][0].text
        assert "+" not in rows[1][0].text  # уровень 0 → без +N

    def test_keyboard_button_label_localized_en(self) -> None:
        presenter = InventoryPresenter(bundle=_fluent_bundle())
        view = InventoryView(items=(_item(display_name="Sword"),), scrolls=())
        kb = presenter.keyboard(view, locale=_EN)
        assert kb is not None
        text = kb.inline_keyboard[0][0].text
        # Кнопка должна быть на английском (без кириллицы).
        assert not any(0x0400 <= ord(c) <= 0x04FF for c in text)


# ───────────────────────── callback_data helpers ─────────────────────────


class TestInventoryCallbackData:
    def test_round_trip_serialize_parse(self) -> None:
        data = inventory_callback_data(action="enchant", item_id="item.right_hand.test_1")
        assert data == "inv:enchant:item.right_hand.test_1"
        action, item_id, scroll_id = parse_inventory_callback_data(data)
        assert action == "enchant"
        assert item_id == "item.right_hand.test_1"
        # Для `enchant`-action `scroll_id` — `None` (скролл выбирается позже).
        assert scroll_id is None

    def test_round_trip_pick_includes_scroll_id(self) -> None:
        data = inventory_callback_data(
            action="pick",
            item_id="item.right_hand.test_1",
            scroll_id="weapon_scroll:blessed",
        )
        assert data == "inv:pick:item.right_hand.test_1:weapon_scroll:blessed"
        action, item_id, scroll_id = parse_inventory_callback_data(data)
        assert action == "pick"
        assert item_id == "item.right_hand.test_1"
        assert scroll_id == "weapon_scroll:blessed"

    def test_round_trip_pickcancel_returns_no_scroll_id(self) -> None:
        data = inventory_callback_data(
            action="pickcancel",
            item_id="item.right_hand.test_1",
        )
        assert data == "inv:pickcancel:item.right_hand.test_1"
        action, item_id, scroll_id = parse_inventory_callback_data(data)
        assert action == "pickcancel"
        assert item_id == "item.right_hand.test_1"
        assert scroll_id is None

    def test_serialize_rejects_empty_item_id(self) -> None:
        with pytest.raises(ValueError, match="item_id must be non-empty"):
            inventory_callback_data(action="enchant", item_id="")

    def test_serialize_rejects_colon_in_item_id(self) -> None:
        # `:` ломает парсер — composite-id без `:` гарантирован каталогом.
        with pytest.raises(ValueError, match="must not contain"):
            inventory_callback_data(action="enchant", item_id="item:bad")

    def test_serialize_rejects_too_long_item_id(self) -> None:
        long_id = "x" * 70
        with pytest.raises(ValueError, match="exceeds 64-byte"):
            inventory_callback_data(action="enchant", item_id=long_id)

    def test_serialize_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError, match="unknown inventory callback action"):
            inventory_callback_data(action="zoo", item_id="x")  # type: ignore[arg-type]

    def test_parse_rejects_wrong_prefix(self) -> None:
        with pytest.raises(ValueError, match="must start with 'inv:'"):
            parse_inventory_callback_data("caravan:enchant:item.x")

    def test_parse_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError, match="unknown inventory action"):
            parse_inventory_callback_data("inv:zap:item.x")

    def test_parse_rejects_empty_item_id(self) -> None:
        with pytest.raises(ValueError, match="must be 'inv:enchant:<item_id>'"):
            parse_inventory_callback_data("inv:enchant:")

    def test_parse_rejects_pick_without_scroll_id(self) -> None:
        with pytest.raises(
            ValueError,
            match="must be 'inv:pick:<item_id>:<scroll_id>'",
        ):
            parse_inventory_callback_data("inv:pick:item.x")

    def test_parse_preserves_dots_in_item_id(self) -> None:
        # `item.right_hand.test_1` содержит `.` — split(maxsplit=3) не должен ломаться.
        action, item_id, scroll_id = parse_inventory_callback_data(
            "inv:enchant:item.right_hand.test_1",
        )
        assert action == "enchant"
        assert item_id == "item.right_hand.test_1"
        assert scroll_id is None


class TestIsInventoryCallback:
    def test_none_returns_false(self) -> None:
        assert is_inventory_callback(None) is False

    def test_inv_prefix_returns_true(self) -> None:
        assert is_inventory_callback("inv:enchant:item.x") is True

    def test_other_prefix_returns_false(self) -> None:
        assert is_inventory_callback("caravan:show_lobby:1") is False
        assert is_inventory_callback("boss:join:1") is False
        assert is_inventory_callback("") is False


# ───────────────────────── enchant_suffix helper ─────────────────────────


class TestEnchantSuffix:
    def test_zero_returns_empty(self) -> None:
        assert enchant_suffix(0) == ""

    def test_negative_returns_empty(self) -> None:
        # Защита от мусорного состояния — UI никогда не должен показывать «-2».
        assert enchant_suffix(-2) == ""

    def test_positive_includes_leading_space(self) -> None:
        assert enchant_suffix(5) == " +5"

    def test_double_digit(self) -> None:
        assert enchant_suffix(15) == " +15"
