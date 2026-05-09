"""Юнит-тесты `bot/presenters/enchant.py` (Спринт 3.4-D, ГДД §2.8).

Покрываем:

1. `EnchantPresenter.{group,other,not_registered,usage,cancelled,idempotent,
   error_*,toast_*}` ходят через корректные `IMessageBundle`-ключи.
2. `warning(...)` для regular/blessed: подставлены `item_display`,
   `scroll_display`, `tier_label`, `tier_emoji`; разный шаблон для
   regular vs blessed; RU/EN parity (один и тот же набор плейсхолдеров,
   разные локализованные строки).
3. `result(...)`:
   * `idempotent=True` → `enchant-idempotent`;
   * `RegularEnchantOutcome.{SUCCESS,NO_EFFECT,DROP,DESTROY}` →
     `enchant-{success,no-effect,drop,destroy}`;
   * `BlessedEnchantOutcome.{SUCCESS_1,SUCCESS_2,NO_EFFECT,DROP_1,DROP_2}` →
     `enchant-{success,success,no-effect,drop,drop}`;
   * `+N`-суффикс: `new_level=0` → нет `+`; `new_level=5` → ` +5`;
     для `DESTROY` показывается голое имя (предмет потерян).
4. `keyboard_confirm(...)` — две кнопки (Подтвердить / Отмена), стабильный
   `callback_data` `enc:<action>:<item_id>:<scroll_id>`, локализованные
   подписи.
5. `tier_for_level(...)` — диапазон `[from, to)` корректно ретёрнит тир;
   `level >= max_level` → последний тир.
6. `enchant_callback_data` / `parse_enchant_callback_data` — round-trip;
   `is_enchant_callback` — отделяет от других префиксов.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.inventory import EnchantAttemptResult, ItemView
from pipirik_wars.bot.presenters.enchant import (
    EnchantPresenter,
    enchant_callback_data,
    is_enchant_callback,
    parse_enchant_callback_data,
    tier_for_level,
)
from pipirik_wars.domain.balance.config import (
    EnchantmentConfig,
    EnchantmentTier,
    Rarity,
    Slot,
)
from pipirik_wars.domain.enchantment import Scroll, ScrollCategory
from pipirik_wars.domain.inventory import (
    BlessedEnchantOutcome,
    ItemCategory,
    RegularEnchantOutcome,
)
from pipirik_wars.infrastructure.balance import YamlBalanceLoader
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle

_RU = Locale("ru")
_EN = Locale("en")


def _fluent_bundle() -> IMessageBundle:
    """Реальный `FluentMessageBundle` поверх `locales/{ru,en}.ftl`."""
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


def _enchantment_config_from_balance() -> EnchantmentConfig:
    """Реальный `EnchantmentConfig` из `config/balance.yaml`.

    Снимок тиров: safe[0..3) easy[3..7) hard[7..12) very_hard[12..18)
    extreme[18..25) almost_impossible[25..30).
    """
    loader = YamlBalanceLoader(
        path=Path(__file__).resolve().parents[4] / "config" / "balance.yaml",
    )
    return loader.get().enchantment


def _make_tier(
    *,
    name: str = "easy",
    from_level: int = 3,
    to_level: int = 7,
    description_key: str = "tier-easy",
    emoji: str = "🟢",
) -> EnchantmentTier:
    return EnchantmentTier(
        name=name,
        from_level=from_level,  # type: ignore[call-arg]
        to_level=to_level,  # type: ignore[call-arg]
        description_key=description_key,
        emoji=emoji,
    )


# ───────────────── chat-branch + usage ключи через FakeMessageBundle ─────────


class TestEnchantPresenterChatBranches:
    """Фиксируем какие ключи реально дёргаются у `IMessageBundle`."""

    def _make(self) -> EnchantPresenter:
        return EnchantPresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))

    def test_group_uses_enchant_group_key(self) -> None:
        assert self._make().group(locale=_RU) == "ru:enchant-group"

    def test_other_uses_enchant_other_key(self) -> None:
        assert self._make().other(locale=_EN) == "en:enchant-other"

    def test_not_registered_uses_enchant_not_registered_key(self) -> None:
        assert self._make().not_registered(locale=_RU) == "ru:enchant-not-registered"

    def test_usage_uses_enchant_usage_key(self) -> None:
        assert self._make().usage(locale=_EN) == "en:enchant-usage"

    def test_cancelled_uses_enchant_cancelled_key(self) -> None:
        assert self._make().cancelled(locale=_RU) == "ru:enchant-cancelled"

    def test_idempotent_uses_enchant_idempotent_key(self) -> None:
        assert self._make().idempotent(locale=_RU) == "ru:enchant-idempotent"

    def test_error_wrong_category_uses_correct_key(self) -> None:
        p = self._make()
        assert p.error_wrong_category(locale=_RU) == "ru:enchant-error-wrong-category"

    def test_error_item_not_found_uses_correct_key(self) -> None:
        p = self._make()
        assert p.error_item_not_found(locale=_EN) == "en:enchant-error-item-not-found"

    def test_error_scroll_not_found_uses_correct_key(self) -> None:
        p = self._make()
        assert p.error_scroll_not_found(locale=_RU) == "ru:enchant-error-scroll-not-found"

    def test_error_out_of_stock_uses_correct_key(self) -> None:
        p = self._make()
        assert p.error_out_of_stock(locale=_RU) == "ru:enchant-error-out-of-stock"

    def test_error_bad_args_uses_correct_key(self) -> None:
        p = self._make()
        assert p.error_bad_args(locale=_RU) == "ru:enchant-error-bad-args"

    def test_toast_confirmed_uses_correct_key(self) -> None:
        assert self._make().toast_confirmed(locale=_RU) == "ru:enchant-toast-confirmed"

    def test_toast_cancelled_uses_correct_key(self) -> None:
        assert self._make().toast_cancelled(locale=_RU) == "ru:enchant-toast-cancelled"

    def test_toast_already_processed_uses_correct_key(self) -> None:
        p = self._make()
        assert p.toast_already_processed(locale=_RU) == "ru:enchant-toast-already-processed"

    def test_toast_error_uses_correct_key(self) -> None:
        assert self._make().toast_error(locale=_EN) == "en:enchant-toast-error"


# ───────────────── warning через реальный FluentMessageBundle ─────────


class TestEnchantPresenterWarningRu:
    """RU-рендер warning-карточки."""

    def test_warning_regular_includes_item_scroll_tier_emoji_ru(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        config = _enchantment_config_from_balance()
        item = _item(display_name="Меч", enchant_level=4)  # tier `easy` (3..7)
        scroll = Scroll(category=ScrollCategory.WEAPON, blessed=False)
        text = presenter.warning(item=item, scroll=scroll, config=config, locale=_RU)
        assert "Попытка заточки" in text
        assert "Меч +4" in text  # +N включён в имя в warning-карточке
        assert "свиток на оружие" in text
        assert "лёгкий" in text
        assert "🟢" in text  # эмодзи safe/easy
        # regular-исходы: уничтожение упомянуто.
        assert "Уничтожение" in text

    def test_warning_blessed_uses_blessed_template_ru(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        config = _enchantment_config_from_balance()
        item = _item(display_name="Шлем", category=ItemCategory.ARMOR, slot=Slot.HAT)
        scroll = Scroll(category=ScrollCategory.ARMOR, blessed=True)
        text = presenter.warning(item=item, scroll=scroll, config=config, locale=_RU)
        assert "Благословлённая заточка" in text
        assert "благословлённый свиток на броню" in text
        # blessed → последняя строка про «не уничтожает».
        assert "никогда не уничтожает" in text
        # blessed → в исходах нет "Уничтожение".
        assert "Уничтожение" not in text

    def test_warning_tier_safe_emoji_for_low_level_ru(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        config = _enchantment_config_from_balance()
        item = _item(enchant_level=0)
        scroll = Scroll(category=ScrollCategory.WEAPON, blessed=False)
        text = presenter.warning(item=item, scroll=scroll, config=config, locale=_RU)
        assert "безопасный" in text
        assert "🟢" in text

    def test_warning_tier_extreme_emoji_for_level_20_ru(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        config = _enchantment_config_from_balance()
        item = _item(display_name="Меч", enchant_level=20)
        scroll = Scroll(category=ScrollCategory.WEAPON, blessed=False)
        text = presenter.warning(item=item, scroll=scroll, config=config, locale=_RU)
        assert "экстремальный" in text
        assert "🔴" in text


class TestEnchantPresenterWarningEn:
    """EN-рендер warning-карточки — RU/EN parity."""

    def test_warning_regular_in_english_no_cyrillic(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        config = _enchantment_config_from_balance()
        item = _item(display_name="Sword", enchant_level=2)
        scroll = Scroll(category=ScrollCategory.WEAPON, blessed=False)
        text = presenter.warning(item=item, scroll=scroll, config=config, locale=_EN)
        assert "Sword +2" in text
        assert "weapon scroll" in text
        assert "Destroy" in text  # regular blessed=False — destroy в шаблоне
        assert not any(0x0400 <= ord(c) <= 0x04FF for c in text)

    def test_warning_blessed_in_english_no_cyrillic(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        config = _enchantment_config_from_balance()
        item = _item(
            display_name="Helmet",
            category=ItemCategory.ARMOR,
            slot=Slot.HAT,
            enchant_level=10,
        )
        scroll = Scroll(category=ScrollCategory.ARMOR, blessed=True)
        text = presenter.warning(item=item, scroll=scroll, config=config, locale=_EN)
        assert "Blessed" in text
        assert "blessed armor scroll" in text
        assert "never destroys" in text
        assert "Destroy" not in text  # blessed → нет уничтожения
        assert not any(0x0400 <= ord(c) <= 0x04FF for c in text)


# ───────────────── result-карточки через реальный FluentMessageBundle ─────────


class TestEnchantPresenterResultRu:
    """RU-рендер карточки результата."""

    def test_result_idempotent_returns_idempotent_key_ru(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        result = EnchantAttemptResult(
            outcome=RegularEnchantOutcome.NO_EFFECT,
            old_level=2,
            new_level=2,
            item_destroyed=False,
            item_dropped=False,
            idempotent=True,
        )
        text = presenter.result(result=result, item_display_name="Меч", locale=_RU)
        assert "уже обработана" in text
        # `+N` в idempotent-фразе не нужен — это явно не результат, а fallback.
        assert "Меч" not in text  # idempotent-шаблон не содержит item_display

    def test_result_regular_success_includes_new_level_ru(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        result = EnchantAttemptResult(
            outcome=RegularEnchantOutcome.SUCCESS,
            old_level=2,
            new_level=3,
            item_destroyed=False,
            item_dropped=False,
        )
        text = presenter.result(result=result, item_display_name="Меч", locale=_RU)
        assert "Успех" in text
        assert "Меч +3" in text
        assert "+2 → +3" in text

    def test_result_regular_no_effect_ru(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        result = EnchantAttemptResult(
            outcome=RegularEnchantOutcome.NO_EFFECT,
            old_level=5,
            new_level=5,
            item_destroyed=False,
            item_dropped=False,
        )
        text = presenter.result(result=result, item_display_name="Меч", locale=_RU)
        assert "Без эффекта" in text
        assert "Меч +5" in text
        assert "+5" in text

    def test_result_regular_drop_ru(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        result = EnchantAttemptResult(
            outcome=RegularEnchantOutcome.DROP,
            old_level=4,
            new_level=3,
            item_destroyed=False,
            item_dropped=True,
        )
        text = presenter.result(result=result, item_display_name="Меч", locale=_RU)
        assert "Падение" in text
        assert "Меч +3" in text
        assert "+4 → +3" in text

    def test_result_regular_destroy_shows_bare_name_ru(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        result = EnchantAttemptResult(
            outcome=RegularEnchantOutcome.DESTROY,
            old_level=10,
            new_level=0,
            item_destroyed=True,
            item_dropped=False,
        )
        text = presenter.result(result=result, item_display_name="Меч", locale=_RU)
        assert "уничтожен" in text
        assert "Меч" in text
        # Уничтожение — `+N` не показывается, предмета больше нет.
        assert "Меч +" not in text

    def test_result_blessed_success_2_uses_success_template_ru(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        result = EnchantAttemptResult(
            outcome=BlessedEnchantOutcome.SUCCESS_2,
            old_level=4,
            new_level=6,
            item_destroyed=False,
            item_dropped=False,
        )
        text = presenter.result(result=result, item_display_name="Шлем", locale=_RU)
        assert "Успех" in text
        assert "Шлем +6" in text
        assert "+4 → +6" in text

    def test_result_blessed_drop_2_uses_drop_template_ru(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        result = EnchantAttemptResult(
            outcome=BlessedEnchantOutcome.DROP_2,
            old_level=8,
            new_level=6,
            item_destroyed=False,
            item_dropped=True,
        )
        text = presenter.result(result=result, item_display_name="Шлем", locale=_RU)
        assert "Падение" in text
        assert "Шлем +6" in text
        assert "+8 → +6" in text


class TestEnchantPresenterResultEn:
    """EN-рендер карточки результата — RU/EN parity."""

    def test_result_success_in_english_no_cyrillic(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        result = EnchantAttemptResult(
            outcome=RegularEnchantOutcome.SUCCESS,
            old_level=2,
            new_level=3,
            item_destroyed=False,
            item_dropped=False,
        )
        text = presenter.result(result=result, item_display_name="Sword", locale=_EN)
        assert "Success" in text
        assert "Sword +3" in text
        assert "+2 → +3" in text
        assert not any(0x0400 <= ord(c) <= 0x04FF for c in text)

    def test_result_destroy_in_english_no_cyrillic(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        result = EnchantAttemptResult(
            outcome=RegularEnchantOutcome.DESTROY,
            old_level=10,
            new_level=0,
            item_destroyed=True,
            item_dropped=False,
        )
        text = presenter.result(result=result, item_display_name="Sword", locale=_EN)
        assert "destroyed" in text.lower()
        assert "Sword" in text
        assert not any(0x0400 <= ord(c) <= 0x04FF for c in text)

    def test_result_idempotent_in_english_no_cyrillic(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        result = EnchantAttemptResult(
            outcome=BlessedEnchantOutcome.NO_EFFECT,
            old_level=2,
            new_level=2,
            item_destroyed=False,
            item_dropped=False,
            idempotent=True,
        )
        text = presenter.result(result=result, item_display_name="Sword", locale=_EN)
        assert "already been processed" in text
        assert not any(0x0400 <= ord(c) <= 0x04FF for c in text)


# ───────────────── confirm-keyboard ─────────────────


class TestEnchantPresenterKeyboardConfirm:
    def test_keyboard_has_two_buttons_with_correct_callback_data(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        kb = presenter.keyboard_confirm(
            item_id="item.right_hand.test_1",
            scroll_id="weapon_scroll:regular",
            locale=_RU,
        )
        assert len(kb.inline_keyboard) == 1
        row = kb.inline_keyboard[0]
        assert len(row) == 2
        # Подтвердить.
        assert row[0].callback_data == "enc:confirm:item.right_hand.test_1:weapon_scroll:regular"
        # Отмена.
        assert row[1].callback_data == "enc:cancel:item.right_hand.test_1:weapon_scroll:regular"
        # Локализованные подписи в RU.
        assert row[0].text == "Подтвердить"
        assert row[1].text == "Отмена"

    def test_keyboard_labels_localized_en(self) -> None:
        presenter = EnchantPresenter(bundle=_fluent_bundle())
        kb = presenter.keyboard_confirm(
            item_id="item.hat.cap_dachnik",
            scroll_id="armor_scroll:blessed",
            locale=_EN,
        )
        labels = [btn.text for btn in kb.inline_keyboard[0]]
        for label in labels:
            assert not any(0x0400 <= ord(c) <= 0x04FF for c in label)
        assert labels == ["Confirm", "Cancel"]


# ───────────────────────── tier_for_level ─────────────────────────


class TestTierForLevel:
    def test_safe_tier_at_level_0(self) -> None:
        config = _enchantment_config_from_balance()
        tier = tier_for_level(config, 0)
        assert tier.name == "safe"
        assert tier.emoji == "🟢"

    def test_easy_tier_at_level_3(self) -> None:
        config = _enchantment_config_from_balance()
        tier = tier_for_level(config, 3)
        assert tier.name == "easy"

    def test_hard_tier_at_level_11(self) -> None:
        config = _enchantment_config_from_balance()
        tier = tier_for_level(config, 11)
        assert tier.name == "hard"

    def test_extreme_tier_at_level_24(self) -> None:
        config = _enchantment_config_from_balance()
        tier = tier_for_level(config, 24)
        assert tier.name == "extreme"

    def test_almost_impossible_tier_at_level_29(self) -> None:
        config = _enchantment_config_from_balance()
        tier = tier_for_level(config, 29)
        assert tier.name == "almost_impossible"

    def test_level_30_returns_last_tier(self) -> None:
        # Граничный случай — `level >= max_level`. Use-case такого не передаст
        # (предмет на `+30` уже-максимален и точить нельзя), но защита
        # от неправомочного вызова существует.
        config = _enchantment_config_from_balance()
        tier = tier_for_level(config, 30)
        assert tier.name == "almost_impossible"


# ───────────────────────── callback_data helpers ─────────────────────────


class TestEnchantCallbackData:
    def test_round_trip_regular_scroll(self) -> None:
        data = enchant_callback_data(
            action="confirm",
            item_id="item.right_hand.test_1",
            scroll_id="weapon_scroll:regular",
        )
        assert data == "enc:confirm:item.right_hand.test_1:weapon_scroll:regular"
        action, item_id, scroll_id = parse_enchant_callback_data(data)
        assert action == "confirm"
        assert item_id == "item.right_hand.test_1"
        assert scroll_id == "weapon_scroll:regular"

    def test_round_trip_blessed_scroll(self) -> None:
        data = enchant_callback_data(
            action="cancel",
            item_id="item.hat.crown_baton",
            scroll_id="armor_scroll:blessed",
        )
        action, item_id, scroll_id = parse_enchant_callback_data(data)
        assert action == "cancel"
        assert item_id == "item.hat.crown_baton"
        assert scroll_id == "armor_scroll:blessed"

    def test_serialize_rejects_empty_item_id(self) -> None:
        with pytest.raises(ValueError, match="item_id must be non-empty"):
            enchant_callback_data(action="confirm", item_id="", scroll_id="weapon_scroll:regular")

    def test_serialize_rejects_colon_in_item_id(self) -> None:
        with pytest.raises(ValueError, match="must not contain"):
            enchant_callback_data(
                action="confirm", item_id="item:bad", scroll_id="weapon_scroll:regular"
            )

    def test_serialize_rejects_empty_scroll_id(self) -> None:
        with pytest.raises(ValueError, match="scroll_id must be non-empty"):
            enchant_callback_data(action="confirm", item_id="item.x", scroll_id="")

    def test_serialize_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError, match="unknown enchant callback action"):
            enchant_callback_data(
                action="zoo",  # type: ignore[arg-type]
                item_id="item.x",
                scroll_id="weapon_scroll:regular",
            )

    def test_serialize_rejects_too_long_payload(self) -> None:
        # 64-байтовый лимит Telegram callback_data: длинный item_id даёт
        # `enc:confirm:<64-байт>:weapon_scroll:regular` > 64 байт.
        long_id = "x" * 50
        with pytest.raises(ValueError, match="exceeds 64-byte"):
            enchant_callback_data(
                action="confirm", item_id=long_id, scroll_id="weapon_scroll:regular"
            )

    def test_parse_rejects_wrong_prefix(self) -> None:
        with pytest.raises(ValueError, match="must be 'enc"):
            parse_enchant_callback_data("inv:confirm:item.x:weapon_scroll:regular")

    def test_parse_rejects_unknown_action(self) -> None:
        with pytest.raises(ValueError, match="unknown enchant action"):
            parse_enchant_callback_data("enc:zap:item.x:weapon_scroll:regular")

    def test_parse_rejects_empty_item_id(self) -> None:
        with pytest.raises(ValueError, match="item_id must be non-empty"):
            parse_enchant_callback_data("enc:confirm::weapon_scroll:regular")

    def test_parse_rejects_empty_scroll_id(self) -> None:
        with pytest.raises(ValueError, match="scroll_id must be non-empty"):
            parse_enchant_callback_data("enc:confirm:item.x:")

    def test_parse_rejects_too_few_parts(self) -> None:
        with pytest.raises(ValueError, match="must be 'enc"):
            parse_enchant_callback_data("enc:confirm:item.x")


class TestIsEnchantCallback:
    def test_none_returns_false(self) -> None:
        assert is_enchant_callback(None) is False

    def test_enc_prefix_returns_true(self) -> None:
        assert is_enchant_callback("enc:confirm:item.x:weapon_scroll:regular") is True

    def test_other_prefix_returns_false(self) -> None:
        assert is_enchant_callback("inv:enchant:item.x") is False
        assert is_enchant_callback("caravan:show_lobby:1") is False
        assert is_enchant_callback("boss:join:1") is False
        assert is_enchant_callback("") is False

    def test_make_tier_helper_unused_directly(self) -> None:
        # Smoke-тест на вспомогательный конструктор тира (используется
        # как fixture в потенциальных будущих тестах). Без него `_make_tier`
        # был бы dead code.
        tier = _make_tier()
        assert tier.from_level == 3
        assert tier.to_level == 7
