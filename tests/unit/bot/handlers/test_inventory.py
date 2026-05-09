"""Юнит-тесты `/inventory` handler-а (Спринт 3.4-D, ГДД §2.6 + §2.8).

Покрываем:

1. Регистрированный игрок в ЛС с непустым инвентарём → handler зовёт
   `GetProfile.execute(...)` → `GetInventory(...)` → шлёт карточку через
   `InventoryPresenter.card(...)` + клавиатуру.
2. Регистрированный игрок в ЛС с пустым инвентарём → ключ
   `inventory-empty`, без `reply_markup`.
3. Незарегистрированный пользователь в ЛС → ключ
   `inventory-not-registered`, `GetInventory` НЕ зовётся.
4. Группа/супергруппа → ключ `inventory-group`, оба use-case-а НЕ зовутся.
5. Прочие чаты (channel) → ключ `inventory-other`, оба use-case-а
   НЕ зовутся.
6. ЛС без `tg_identity` → ключ `inventory-other` (fallback).
7. Локаль из middleware пробрасывается в bundle (RU vs EN дают разные
   маркерные строки от `FakeMessageBundle`).
8. Без локали → fallback на `DEFAULT_LOCALE`.

Плюс — `inv:`-callback handler (D.1d):

9. `inv:enchant:<id>` с 0 свитками → toast `inventory-toast-no-scroll`,
   `message.answer` НЕ зовётся.
10. `inv:enchant:<id>` с 1 свитком → handler шлёт **новое** сообщение
    с `enchant-warning-*` + confirm-keyboard (`enc:confirm:...`).
11. `inv:enchant:<id>` с 2 свитками (regular + blessed) → handler шлёт
    picker-сообщение `inventory-picker-card` + три кнопки
    (`inv:pick:..:weapon_scroll:regular`, `inv:pick:..:..blessed`,
    `inv:pickcancel:..`).
12. `inv:pick:<id>:<scroll_id>` (валидный) → handler **редактирует**
    picker-сообщение в warning-карточку + confirm-keyboard.
13. `inv:pickcancel:<id>` → handler редактирует picker-сообщение в
    `inventory-picker-cancelled` + toast `inventory-picker-toast-cancelled`.
14. Невалидный `callback_data` → toast `enchant-toast-error`.
15. Незарегистрированный игрок (для не-`pickcancel`) → toast
    `inventory-not-registered`.
16. `item_id`, которого нет в инвентаре → toast `enchant-error-item-not-found`.
17. `inv:pick:<id>:<scroll_id>`, где scroll-stack `qty=0` → toast
    `enchant-error-scroll-not-found` (защита от race с `enchant.py`).
18. `inv:pick:<id>:<scroll_id>` с категорией скролла, не совпадающей
    с предметом → toast `enchant-error-wrong-category`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.inventory import (
    GetInventory,
    InventoryView,
    ItemView,
    ScrollView,
)
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.inventory import (
    handle_inventory,
    handle_inventory_callback,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.balance.config import Rarity, Slot
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.inventory import ItemCategory
from pipirik_wars.domain.player import (
    DisplayName,
    Player,
    PlayerName,
    PlayerStatus,
    Thickness,
    Title,
)
from pipirik_wars.domain.player.value_objects import Length, Username
from tests.fakes import FakeBalanceConfig, FakeMessageBundle
from tests.unit.domain.balance.factories import build_valid_balance


def _build_message_mock(chat_type: str = "private") -> MagicMock:
    msg = MagicMock()
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    return msg


def _identity(chat_kind: str = "private", tg_user_id: int = 100) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=None,
    )


def _profile_view(player_id: int = 1) -> ProfileView:
    return ProfileView(
        player=Player(
            id=player_id,
            tg_id=100,
            username=Username(value="alice"),
            length=Length(cm=47),
            thickness=Thickness(level=5),
            title=Title.NEWBIE,
            name=PlayerName(value="Коляндр"),
            status=PlayerStatus.ACTIVE,
            created_at=datetime(2026, 5, 4, tzinfo=UTC),
            updated_at=datetime(2026, 5, 4, tzinfo=UTC),
        ),
        display_name=DisplayName(value="Бананчик"),
    )


def _stub_get_profile(*, found: bool = True, player_id: int = 1) -> MagicMock:
    use_case = MagicMock(spec=GetProfile)
    use_case.execute = AsyncMock(
        return_value=_profile_view(player_id=player_id) if found else None,
    )
    return use_case


def _stub_get_inventory(*, view: InventoryView | None = None) -> AsyncMock:
    """Stub для `GetInventory` — `AsyncMock(spec=GetInventory)`.

    Handler зовёт через `await get_inventory(player_id=...)`, что соответствует
    `GetInventory.__call__(...)`. `AsyncMock` сам по себе awaitable-callable,
    поэтому проверка вызова идёт через `assert_awaited_once_with(...)`.
    """
    if view is None:
        view = InventoryView(items=(), scrolls=())
    return AsyncMock(spec=GetInventory, return_value=view)


def _make_item(
    *,
    item_id: str = "item.right_hand.test_1",
    display_name: str = "Меч",
    enchant_level: int = 0,
) -> ItemView:
    return ItemView(
        item_id=item_id,
        display_name=display_name,
        category=ItemCategory.WEAPON,
        slot=Slot.RIGHT_HAND,
        rarity=Rarity.RARE,
        enchant_level=enchant_level,
    )


def _non_empty_view() -> InventoryView:
    return InventoryView(
        items=(_make_item(),),
        scrolls=(
            ScrollView(
                scroll_id="weapon_scroll:regular",
                category="weapon_scroll",
                blessed=False,
                qty=2,
            ),
        ),
    )


@pytest.mark.asyncio
class TestHandleInventory:
    async def test_private_registered_with_items_renders_card_and_keyboard(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile(player_id=7)
        get_inventory = _stub_get_inventory(view=_non_empty_view())
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_inventory(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_awaited_once_with(tg_id=100)
        get_inventory.assert_awaited_once()
        await_args = get_inventory.await_args
        assert await_args is not None
        assert await_args.kwargs == {"player_id": 7}
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        # Маркерный bundle сериализует ключ карточки.
        assert "ru:inventory-card[" in sent
        assert "items_count=1" in sent
        assert "scrolls_count=1" in sent
        # Клавиатура передаётся через `reply_markup=...`.
        kwargs = msg.answer.await_args.kwargs
        kb = kwargs.get("reply_markup")
        assert kb is not None
        assert kb.inline_keyboard[0][0].callback_data == "inv:enchant:item.right_hand.test_1"

    async def test_private_registered_empty_inventory_replies_empty_text(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory(view=InventoryView(items=(), scrolls=()))
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_inventory(
            cast(Message, msg),
            _identity("private"),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_awaited_once()
        get_inventory.assert_awaited_once()
        msg.answer.assert_awaited_once_with("ru:inventory-empty")

    async def test_private_unregistered_replies_not_registered(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile(found=False)
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_inventory(
            cast(Message, msg),
            _identity("private"),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_awaited_once()
        get_inventory.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:inventory-not-registered")

    async def test_group_skips_both_use_cases_and_replies_instructions(self) -> None:
        msg = _build_message_mock("group")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_inventory(
            cast(Message, msg),
            _identity("group"),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        get_inventory.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:inventory-group")

    async def test_supergroup_skips_use_cases(self) -> None:
        msg = _build_message_mock("supergroup")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_inventory(
            cast(Message, msg),
            _identity("supergroup"),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        get_inventory.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:inventory-group")

    async def test_channel_replies_other(self) -> None:
        msg = _build_message_mock("channel")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_inventory(
            cast(Message, msg),
            _identity("channel"),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        get_inventory.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:inventory-other")

    async def test_private_without_tg_identity_falls_back_to_other(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_inventory(
            cast(Message, msg),
            None,
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        get_inventory.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:inventory-other")

    async def test_locale_propagates_to_bundle(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory(view=_non_empty_view())
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_inventory(
            cast(Message, msg),
            _identity("private"),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            bundle,
            Locale("en"),
        )

        sent = msg.answer.await_args.args[0]
        assert "en:inventory-card[" in sent

    async def test_no_locale_falls_back_to_default_locale(self) -> None:
        msg = _build_message_mock("group")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_inventory(
            cast(Message, msg),
            _identity("group"),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            bundle,
            None,
        )

        msg.answer.assert_awaited_once_with("en:inventory-group")


# ───────────────────── inv:-callback handler (D.1d) ─────────────────────


_ITEM_ID = "item.right_hand.test_1"
_REGULAR_SCROLL_ID = "weapon_scroll:regular"
_BLESSED_SCROLL_ID = "weapon_scroll:blessed"


def _build_callback_mock(
    *,
    data: str,
    has_message: bool = True,
) -> MagicMock:
    """Стандартный mock `CallbackQuery` для inv:-callback handler-а.

    `callback.message` имеет два AsyncMock-а: `answer` (отправка нового
    сообщения, ветка `_handle_enchant_button`) и `edit_text` (редактирование
    picker-а на месте, ветки `_handle_pick` и `_handle_pickcancel`).
    """
    callback = MagicMock(spec=CallbackQuery)
    callback.data = data
    callback.answer = AsyncMock()
    if has_message:
        msg = MagicMock(spec=Message)
        msg.message_id = 12345
        msg.chat = Chat(id=42, type="private")
        msg.answer = AsyncMock()
        msg.edit_text = AsyncMock()
        callback.message = msg
    else:
        callback.message = None
    return callback


def _balance() -> IBalanceConfig:
    """Реальный (валидный) `BalanceConfig` снимок, через factory."""
    return cast(IBalanceConfig, FakeBalanceConfig(build_valid_balance()))


def _inventory_with_scrolls(
    *,
    item: ItemView | None = None,
    scrolls: tuple[ScrollView, ...] = (),
) -> InventoryView:
    if item is None:
        item = _make_item(item_id=_ITEM_ID)
    return InventoryView(items=(item,), scrolls=scrolls)


def _scroll(scroll_id: str, *, qty: int = 1) -> ScrollView:
    blessed = scroll_id.endswith(":blessed")
    category = scroll_id.split(":", 1)[0]
    return ScrollView(
        scroll_id=scroll_id,
        category=category,
        blessed=blessed,
        qty=qty,
    )


@pytest.mark.asyncio
class TestHandleInventoryCallbackEnchant:
    """`inv:enchant:<item_id>` — нажата «Заточить» в карточке `/inventory`."""

    async def test_no_matching_scrolls_emits_toast_and_does_not_edit_message(
        self,
    ) -> None:
        callback = _build_callback_mock(data=f"inv:enchant:{_ITEM_ID}")
        get_profile = _stub_get_profile(player_id=7)
        # У игрока нет нужных свитков (broker_scroll вместо weapon_scroll).
        view = _inventory_with_scrolls(scrolls=(_scroll("broker_scroll:regular", qty=1),))
        get_inventory = _stub_get_inventory(view=view)

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_awaited_once_with(
            "ru:inventory-toast-no-scroll",
            show_alert=False,
        )
        callback.message.answer.assert_not_awaited()
        callback.message.edit_text.assert_not_awaited()

    async def test_one_scroll_sends_warning_card_with_confirm_keyboard(self) -> None:
        callback = _build_callback_mock(data=f"inv:enchant:{_ITEM_ID}")
        get_profile = _stub_get_profile(player_id=7)
        view = _inventory_with_scrolls(scrolls=(_scroll(_REGULAR_SCROLL_ID, qty=2),))
        get_inventory = _stub_get_inventory(view=view)

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        # callback.answer() без аргументов — empty toast (ack).
        callback.answer.assert_awaited_once_with()
        # Новое сообщение — warning-карточка + клавиатура confirm/cancel.
        callback.message.answer.assert_awaited_once()
        sent_text = callback.message.answer.await_args.args[0]
        assert "ru:enchant-warning-regular[" in sent_text
        kb = callback.message.answer.await_args.kwargs.get("reply_markup")
        assert kb is not None
        # Первый ряд — две кнопки: confirm + cancel.
        confirm_btn, cancel_btn = kb.inline_keyboard[0]
        assert confirm_btn.callback_data == f"enc:confirm:{_ITEM_ID}:{_REGULAR_SCROLL_ID}"
        assert cancel_btn.callback_data == f"enc:cancel:{_ITEM_ID}:{_REGULAR_SCROLL_ID}"
        # `edit_text` НЕ зовётся — карточка инвентаря живёт отдельно.
        callback.message.edit_text.assert_not_awaited()

    async def test_two_scrolls_send_picker_card_with_three_buttons(self) -> None:
        callback = _build_callback_mock(data=f"inv:enchant:{_ITEM_ID}")
        get_profile = _stub_get_profile(player_id=7)
        view = _inventory_with_scrolls(
            scrolls=(
                _scroll(_REGULAR_SCROLL_ID, qty=1),
                _scroll(_BLESSED_SCROLL_ID, qty=1),
            ),
        )
        get_inventory = _stub_get_inventory(view=view)

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_awaited_once_with()
        callback.message.answer.assert_awaited_once()
        sent_text = callback.message.answer.await_args.args[0]
        assert "ru:inventory-picker-card[" in sent_text
        kb = callback.message.answer.await_args.kwargs.get("reply_markup")
        assert kb is not None
        # Picker рендерит три кнопки (regular | blessed | cancel) — ряды
        # упорядочены: первый — два варианта свитков, второй — «Отмена».
        rows = kb.inline_keyboard
        assert len(rows) == 2
        assert len(rows[0]) == 2
        assert len(rows[1]) == 1
        regular_btn, blessed_btn = rows[0]
        cancel_btn = rows[1][0]
        assert regular_btn.callback_data == f"inv:pick:{_ITEM_ID}:{_REGULAR_SCROLL_ID}"
        assert blessed_btn.callback_data == f"inv:pick:{_ITEM_ID}:{_BLESSED_SCROLL_ID}"
        assert cancel_btn.callback_data == f"inv:pickcancel:{_ITEM_ID}"
        callback.message.edit_text.assert_not_awaited()

    async def test_unregistered_player_emits_not_registered_toast(self) -> None:
        callback = _build_callback_mock(data=f"inv:enchant:{_ITEM_ID}")
        get_profile = _stub_get_profile(found=False)
        get_inventory = _stub_get_inventory()

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_awaited_once_with(
            "ru:inventory-not-registered",
            show_alert=False,
        )
        get_inventory.assert_not_awaited()
        callback.message.answer.assert_not_awaited()

    async def test_item_not_in_inventory_emits_item_not_found_toast(self) -> None:
        callback = _build_callback_mock(data="inv:enchant:item.right_hand.absent")
        get_profile = _stub_get_profile(player_id=7)
        view = _inventory_with_scrolls(scrolls=(_scroll(_REGULAR_SCROLL_ID, qty=1),))
        get_inventory = _stub_get_inventory(view=view)

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_awaited_once_with(
            "ru:enchant-error-item-not-found",
            show_alert=False,
        )
        callback.message.answer.assert_not_awaited()


@pytest.mark.asyncio
class TestHandleInventoryCallbackPick:
    """`inv:pick:<item_id>:<scroll_id>` — выбран свиток в picker-е."""

    async def test_valid_pick_edits_picker_into_warning_card(self) -> None:
        callback = _build_callback_mock(
            data=f"inv:pick:{_ITEM_ID}:{_BLESSED_SCROLL_ID}",
        )
        get_profile = _stub_get_profile(player_id=7)
        view = _inventory_with_scrolls(
            scrolls=(
                _scroll(_REGULAR_SCROLL_ID, qty=1),
                _scroll(_BLESSED_SCROLL_ID, qty=1),
            ),
        )
        get_inventory = _stub_get_inventory(view=view)

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_awaited_once_with()
        # Pick *редактирует* существующее picker-сообщение, а не шлёт новое.
        callback.message.edit_text.assert_awaited_once()
        edit_kwargs = callback.message.edit_text.await_args.kwargs
        assert "ru:enchant-warning-blessed[" in edit_kwargs["text"]
        kb = edit_kwargs["reply_markup"]
        confirm_btn, cancel_btn = kb.inline_keyboard[0]
        assert confirm_btn.callback_data == f"enc:confirm:{_ITEM_ID}:{_BLESSED_SCROLL_ID}"
        assert cancel_btn.callback_data == f"enc:cancel:{_ITEM_ID}:{_BLESSED_SCROLL_ID}"
        callback.message.answer.assert_not_awaited()

    async def test_pick_with_zero_qty_emits_scroll_not_found_toast(self) -> None:
        callback = _build_callback_mock(
            data=f"inv:pick:{_ITEM_ID}:{_REGULAR_SCROLL_ID}",
        )
        get_profile = _stub_get_profile(player_id=7)
        # qty=0 — стэк есть, но запас опустошён (race: игрок успел истратить
        # свиток между показом picker-а и нажатием кнопки).
        view = _inventory_with_scrolls(scrolls=(_scroll(_REGULAR_SCROLL_ID, qty=0),))
        get_inventory = _stub_get_inventory(view=view)

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_awaited_once_with(
            "ru:enchant-error-scroll-not-found",
            show_alert=False,
        )
        callback.message.edit_text.assert_not_awaited()

    async def test_pick_with_wrong_category_emits_wrong_category_toast(self) -> None:
        callback = _build_callback_mock(
            data=f"inv:pick:{_ITEM_ID}:armor_scroll:regular",
        )
        get_profile = _stub_get_profile(player_id=7)
        # У игрока ИСТЬ armor_scroll:regular в стэке (qty>0), но предмет —
        # weapon-категории, поэтому handler ожидает weapon_scroll. Категории
        # не совпадают → toast `enchant-error-wrong-category`.
        view = _inventory_with_scrolls(
            scrolls=(_scroll("armor_scroll:regular", qty=1),),
        )
        get_inventory = _stub_get_inventory(view=view)

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_awaited_once_with(
            "ru:enchant-error-wrong-category",
            show_alert=False,
        )
        callback.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
class TestHandleInventoryCallbackPickCancel:
    """`inv:pickcancel:<item_id>` — нажата «Отмена» в picker-е."""

    async def test_pickcancel_sends_toast_and_edits_message(self) -> None:
        callback = _build_callback_mock(data=f"inv:pickcancel:{_ITEM_ID}")
        # `_handle_pickcancel` НЕ зовёт ни get_profile, ни get_inventory —
        # ему хватает callback.message; стабы должны остаться неиспользованными.
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_awaited_once_with(
            "ru:inventory-picker-toast-cancelled",
            show_alert=False,
        )
        callback.message.edit_text.assert_awaited_once()
        edit_kwargs = callback.message.edit_text.await_args.kwargs
        assert edit_kwargs == {"text": "ru:inventory-picker-cancelled"}
        get_profile.execute.assert_not_awaited()
        get_inventory.assert_not_awaited()

    async def test_pickcancel_without_message_just_acks_with_toast(self) -> None:
        callback = _build_callback_mock(
            data=f"inv:pickcancel:{_ITEM_ID}",
            has_message=False,
        )
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_awaited_once_with(
            "ru:inventory-picker-toast-cancelled",
            show_alert=False,
        )

    async def test_pickcancel_swallows_telegram_error_on_edit_text(self) -> None:
        callback = _build_callback_mock(data=f"inv:pickcancel:{_ITEM_ID}")
        callback.message.edit_text.side_effect = RuntimeError("telegram down")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()

        # Не должно поднять исключение наружу — handler best-effort редактит.
        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_awaited_once()


@pytest.mark.asyncio
class TestHandleInventoryCallbackGuards:
    """Граничные случаи (невалидный data / отсутствие identity)."""

    async def test_invalid_callback_data_emits_toast_error(self) -> None:
        callback = _build_callback_mock(data="inv:bogus:foo:bar:baz:qux")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_awaited_once_with(
            "ru:enchant-toast-error",
            show_alert=False,
        )
        get_profile.execute.assert_not_awaited()
        get_inventory.assert_not_awaited()

    async def test_no_identity_returns_silently(self) -> None:
        callback = _build_callback_mock(data=f"inv:enchant:{_ITEM_ID}")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            None,
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_not_awaited()
        get_profile.execute.assert_not_awaited()
        get_inventory.assert_not_awaited()

    async def test_no_data_returns_silently(self) -> None:
        callback = _build_callback_mock(data=f"inv:enchant:{_ITEM_ID}")
        callback.data = None
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            Locale("ru"),
        )

        callback.answer.assert_not_awaited()

    async def test_no_locale_falls_back_to_default(self) -> None:
        callback = _build_callback_mock(data=f"inv:pickcancel:{_ITEM_ID}")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()

        await handle_inventory_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=100),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            cast(IMessageBundle, FakeMessageBundle()),
            None,
        )

        callback.answer.assert_awaited_once_with(
            "en:inventory-picker-toast-cancelled",
            show_alert=False,
        )
