"""Юнит-тесты `/enchant`-handler-а + confirm/cancel-callback-ов (Спринт 3.4-D, ГДД §2.8).

Покрываем:

1. Команда `/enchant <item_id> <scroll_id>`:
   - Чат-гейт: group/supergroup → `enchant-group`; channel → `enchant-other`;
     ЛС без identity → `enchant-other`.
   - Аргументы: 0/1/3+ → `enchant-usage`; пустой `text` → `enchant-usage`.
   - Регистрация: `GetProfile.execute(...) → None` → `enchant-not-registered`.
   - Невалидный `scroll_id` → `enchant-error-bad-args`.
   - Предмета нет в инвентаре → `enchant-error-item-not-found`.
   - Скролла нет в стэке → `enchant-error-scroll-not-found`.
   - Категория скролла ≠ категории предмета → `enchant-error-wrong-category`.
   - Happy path → `enchant-warning-{regular,blessed}` + клавиатура с
     `enc:confirm:...` и `enc:cancel:...`.

2. Callback `enc:<action>:<item_id>:<scroll_id>`:
   - `tg_identity is None` → silent return (handler не вызывает ack).
   - `callback.data is None` → silent return.
   - Невалидный `callback_data` → toast `enchant-toast-error`.
   - `cancel` happy path → toast `enchant-toast-cancelled` + edit_text
     `enchant-cancelled`.
   - `cancel` без `callback.message` → toast, без edit_text.
   - `cancel` `edit_text` падает → исключение глотается (best-effort).
   - `confirm` без `callback.message` → toast `enchant-toast-error`.
   - `confirm` незарегистрирован → toast `enchant-not-registered`.
   - `confirm` предмета нет в inventory (pre-uow) → toast
     `enchant-error-item-not-found`.
   - `confirm` use-case бросает `ItemNotFoundError` → toast.
   - `confirm` use-case бросает `WrongScrollCategoryError` → toast.
   - `confirm` use-case бросает `ScrollNotFoundError` → toast.
   - `confirm` use-case бросает `ScrollOutOfStockError` → toast.
   - `confirm` use-case бросает `ValueError` → toast `enchant-error-bad-args`.
   - `confirm` happy path SUCCESS → toast `enchant-toast-confirmed` +
     edit_text `enchant-success`.
   - `confirm` idempotent=True → toast `enchant-toast-already-processed` +
     edit_text `enchant-idempotent`.
   - `confirm` `edit_text` падает → исключение глотается.
   - `confirm` открывает ambient `IUnitOfWork` (uow.commits == 1).

3. Локаль:
   - Команда без `locale` → fallback на `DEFAULT_LOCALE` (en).
   - Callback с `locale="ru"` → русские маркеры в bundle.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.inventory import (
    EnchantAttemptResult,
    EnchantItem,
    GetInventory,
    InventoryView,
    ItemView,
    ScrollView,
)
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.enchant import (
    handle_enchant,
    handle_enchant_callback,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.balance.config import Rarity, Slot
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.inventory import (
    BlessedEnchantOutcome,
    ItemCategory,
    ItemNotFoundError,
    RegularEnchantOutcome,
    ScrollNotFoundError,
    ScrollOutOfStockError,
    WrongScrollCategoryError,
)
from pipirik_wars.domain.player import (
    DisplayName,
    Player,
    PlayerName,
    PlayerStatus,
    Thickness,
    Title,
)
from pipirik_wars.domain.player.value_objects import Length, Username
from pipirik_wars.infrastructure.balance import YamlBalanceLoader
from tests.fakes import FakeMessageBundle, FakeUnitOfWork

_RU = Locale("ru")
_EN = Locale("en")
_TG_USER_ID = 100
_PLAYER_ID = 7
_MESSAGE_ID = 555
_ITEM_ID = "item.right_hand.test_1"
_SCROLL_ID = "weapon_scroll:regular"
_SCROLL_ID_BLESSED = "weapon_scroll:blessed"


# ───────────────────────── helpers ─────────────────────────


def _build_message_mock(
    *,
    chat_type: str = "private",
    text: str = f"/enchant {_ITEM_ID} {_SCROLL_ID}",
) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=42, type=chat_type)
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _identity(
    *,
    chat_kind: str = "private",
    tg_user_id: int = _TG_USER_ID,
) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=None,
    )


def _profile_view(player_id: int = _PLAYER_ID) -> ProfileView:
    return ProfileView(
        player=Player(
            id=player_id,
            tg_id=_TG_USER_ID,
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


def _stub_get_profile(*, found: bool = True, player_id: int = _PLAYER_ID) -> MagicMock:
    use_case = MagicMock(spec=GetProfile)
    use_case.execute = AsyncMock(
        return_value=_profile_view(player_id=player_id) if found else None,
    )
    return use_case


def _make_item(
    *,
    item_id: str = _ITEM_ID,
    display_name: str = "Меч",
    category: ItemCategory = ItemCategory.WEAPON,
    enchant_level: int = 0,
) -> ItemView:
    return ItemView(
        item_id=item_id,
        display_name=display_name,
        category=category,
        slot=Slot.RIGHT_HAND,
        rarity=Rarity.RARE,
        enchant_level=enchant_level,
    )


def _make_scroll(
    *,
    scroll_id: str = _SCROLL_ID,
    category: str = "weapon_scroll",
    blessed: bool = False,
    qty: int = 2,
) -> ScrollView:
    return ScrollView(
        scroll_id=scroll_id,
        category=category,
        blessed=blessed,
        qty=qty,
    )


def _stub_get_inventory(*, view: InventoryView | None = None) -> AsyncMock:
    if view is None:
        view = InventoryView(items=(_make_item(),), scrolls=(_make_scroll(),))
    return AsyncMock(spec=GetInventory, return_value=view)


def _stub_enchant_item(
    *,
    result: EnchantAttemptResult | None = None,
    error: Exception | None = None,
) -> AsyncMock:
    """`AsyncMock(spec=EnchantItem)` — handler зовёт `await enchant_item(...)`."""
    if error is not None:
        return AsyncMock(spec=EnchantItem, side_effect=error)
    if result is None:
        result = EnchantAttemptResult(
            outcome=RegularEnchantOutcome.SUCCESS,
            old_level=0,
            new_level=1,
            item_destroyed=False,
            item_dropped=False,
            idempotent=False,
        )
    return AsyncMock(spec=EnchantItem, return_value=result)


_BALANCE_YAML_PATH = Path("config/balance.yaml")


def _balance() -> IBalanceConfig:
    """Реальный `IBalanceConfig` из `config/balance.yaml` (источник правды).

    Конструировать `EnchantmentConfig` вручную сложно (cross-row invariants
    + `_validate_tiers_cover_range` + safe-zone правила), поэтому проще
    использовать загрузчик — он же используется в production.
    """
    return YamlBalanceLoader(_BALANCE_YAML_PATH)


def _build_callback_mock(
    *,
    data: str = f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}",
    has_message: bool = True,
    message_id: int = _MESSAGE_ID,
) -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.data = data
    callback.answer = AsyncMock()
    if has_message:
        msg = MagicMock(spec=Message)
        msg.message_id = message_id
        msg.chat = Chat(id=42, type="private")
        msg.edit_text = AsyncMock()
        callback.message = msg
    else:
        callback.message = None
    return callback


# ───────────────────────── /enchant command ─────────────────────────


@pytest.mark.asyncio
class TestHandleEnchantChatGate:
    async def test_group_uses_enchant_group_key(self) -> None:
        msg = _build_message_mock(chat_type="group")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(chat_kind="group"),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        get_profile.execute.assert_not_awaited()
        get_inventory.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:enchant-group")

    async def test_supergroup_uses_enchant_group_key(self) -> None:
        msg = _build_message_mock(chat_type="supergroup")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(chat_kind="supergroup"),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:enchant-group")

    async def test_channel_uses_enchant_other_key(self) -> None:
        msg = _build_message_mock(chat_type="channel")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(chat_kind="channel"),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        get_profile.execute.assert_not_awaited()
        get_inventory.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:enchant-other")

    async def test_private_without_identity_uses_other_key(self) -> None:
        msg = _build_message_mock(chat_type="private")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            None,
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        get_profile.execute.assert_not_awaited()
        get_inventory.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:enchant-other")

    async def test_no_locale_falls_back_to_default(self) -> None:
        msg = _build_message_mock(chat_type="group")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(chat_kind="group"),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            None,
        )

        msg.answer.assert_awaited_once_with("en:enchant-group")


@pytest.mark.asyncio
class TestHandleEnchantArgumentParsing:
    async def test_no_args_returns_usage(self) -> None:
        msg = _build_message_mock(text="/enchant")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:enchant-usage")

    async def test_one_arg_returns_usage(self) -> None:
        msg = _build_message_mock(text=f"/enchant {_ITEM_ID}")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:enchant-usage")

    async def test_three_args_returns_usage(self) -> None:
        msg = _build_message_mock(
            text=f"/enchant {_ITEM_ID} {_SCROLL_ID} extra",
        )
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:enchant-usage")

    async def test_message_text_none_returns_usage(self) -> None:
        msg = _build_message_mock(text="")
        msg.text = None
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:enchant-usage")


@pytest.mark.asyncio
class TestHandleEnchantPreCheck:
    async def test_unregistered_returns_not_registered(self) -> None:
        msg = _build_message_mock()
        get_profile = _stub_get_profile(found=False)
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        get_profile.execute.assert_awaited_once_with(tg_id=_TG_USER_ID)
        get_inventory.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:enchant-not-registered")

    async def test_invalid_scroll_id_returns_bad_args(self) -> None:
        msg = _build_message_mock(text=f"/enchant {_ITEM_ID} not_a_scroll_id")
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        get_inventory.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:enchant-error-bad-args")

    async def test_item_not_in_inventory_returns_item_not_found(self) -> None:
        msg = _build_message_mock()
        get_profile = _stub_get_profile()
        # инвентарь без нужного предмета — есть только скролл.
        get_inventory = _stub_get_inventory(
            view=InventoryView(items=(), scrolls=(_make_scroll(),)),
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        get_inventory.assert_awaited_once()
        assert get_inventory.await_args is not None
        assert get_inventory.await_args.kwargs == {"player_id": _PLAYER_ID}
        msg.answer.assert_awaited_once_with("ru:enchant-error-item-not-found")

    async def test_scroll_not_in_stock_returns_scroll_not_found(self) -> None:
        msg = _build_message_mock()
        get_profile = _stub_get_profile()
        # есть предмет, но нет скролла.
        get_inventory = _stub_get_inventory(
            view=InventoryView(items=(_make_item(),), scrolls=()),
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:enchant-error-scroll-not-found")

    async def test_scroll_in_stack_with_zero_qty_returns_scroll_not_found(self) -> None:
        msg = _build_message_mock()
        get_profile = _stub_get_profile()
        # стэк скролла есть, но `qty == 0` — handler такой стэк отфильтрует.
        get_inventory = _stub_get_inventory(
            view=InventoryView(
                items=(_make_item(),),
                scrolls=(_make_scroll(qty=0),),
            ),
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:enchant-error-scroll-not-found")

    async def test_wrong_category_returns_wrong_category(self) -> None:
        msg = _build_message_mock()
        get_profile = _stub_get_profile()
        # предмет — броня, скролл — на оружие.
        get_inventory = _stub_get_inventory(
            view=InventoryView(
                items=(_make_item(category=ItemCategory.ARMOR),),
                scrolls=(_make_scroll(),),
            ),
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:enchant-error-wrong-category")


@pytest.mark.asyncio
class TestHandleEnchantHappyPath:
    async def test_warning_card_with_keyboard_for_regular_scroll(self) -> None:
        msg = _build_message_mock()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert "ru:enchant-warning-regular[" in sent
        assert "tier_emoji=🟢" in sent
        kb = msg.answer.await_args.kwargs.get("reply_markup")
        assert kb is not None
        # Две кнопки: confirm + cancel.
        assert len(kb.inline_keyboard) == 1
        assert len(kb.inline_keyboard[0]) == 2
        assert kb.inline_keyboard[0][0].callback_data == f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}"
        assert kb.inline_keyboard[0][1].callback_data == f"enc:cancel:{_ITEM_ID}:{_SCROLL_ID}"

    async def test_warning_card_for_blessed_scroll(self) -> None:
        msg = _build_message_mock(
            text=f"/enchant {_ITEM_ID} {_SCROLL_ID_BLESSED}",
        )
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory(
            view=InventoryView(
                items=(_make_item(),),
                scrolls=(
                    _make_scroll(
                        scroll_id=_SCROLL_ID_BLESSED,
                        blessed=True,
                    ),
                ),
            ),
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _RU,
        )

        sent = msg.answer.await_args.args[0]
        assert "ru:enchant-warning-blessed[" in sent

    async def test_locale_propagates_to_bundle(self) -> None:
        msg = _build_message_mock()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant(
            cast(Message, msg),
            _identity(),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            _balance(),
            bundle,
            _EN,
        )

        sent = msg.answer.await_args.args[0]
        assert "en:enchant-warning-regular[" in sent


# ───────────────────────── enchant callbacks ─────────────────────────


@pytest.mark.asyncio
class TestHandleEnchantCallbackGuards:
    async def test_no_identity_returns_silently(self) -> None:
        callback = _build_callback_mock()
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            None,
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.answer.assert_not_called()
        enchant_uc.assert_not_awaited()
        assert uow.commits == 0

    async def test_no_data_returns_silently(self) -> None:
        callback = _build_callback_mock()
        callback.data = None
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.answer.assert_not_called()
        enchant_uc.assert_not_awaited()

    async def test_invalid_callback_data_emits_toast_error(self) -> None:
        callback = _build_callback_mock(data="enc:bogus:foo:bar")
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        enchant_uc.assert_not_awaited()
        callback.answer.assert_awaited_once()
        toast = callback.answer.await_args.args[0]
        assert toast == "ru:enchant-toast-error"

    async def test_garbage_callback_data_no_colons(self) -> None:
        callback = _build_callback_mock(data="enc:")
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.answer.assert_awaited_once_with(
            "ru:enchant-toast-error",
            show_alert=False,
        )


@pytest.mark.asyncio
class TestHandleEnchantCallbackCancel:
    async def test_happy_path_emits_toast_and_edits_message(self) -> None:
        callback = _build_callback_mock(
            data=f"enc:cancel:{_ITEM_ID}:{_SCROLL_ID}",
        )
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        # use-case НЕ зовётся.
        enchant_uc.assert_not_awaited()
        # Toast + edit_text.
        callback.answer.assert_awaited_once_with(
            "ru:enchant-toast-cancelled",
            show_alert=False,
        )
        callback.message.edit_text.assert_awaited_once()
        edit_kwargs = callback.message.edit_text.await_args.kwargs
        assert edit_kwargs["text"] == "ru:enchant-cancelled"
        # `IUnitOfWork` не открывается на cancel.
        assert uow.commits == 0

    async def test_cancel_without_message_emits_toast_no_edit(self) -> None:
        callback = _build_callback_mock(
            data=f"enc:cancel:{_ITEM_ID}:{_SCROLL_ID}",
            has_message=False,
        )
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.answer.assert_awaited_once()
        toast = callback.answer.await_args.args[0]
        assert toast == "ru:enchant-toast-cancelled"

    async def test_cancel_edit_text_failure_does_not_propagate(self) -> None:
        callback = _build_callback_mock(
            data=f"enc:cancel:{_ITEM_ID}:{_SCROLL_ID}",
        )
        callback.message.edit_text.side_effect = RuntimeError("telegram API down")
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.answer.assert_awaited_once()


@pytest.mark.asyncio
class TestHandleEnchantCallbackConfirm:
    async def test_no_message_emits_toast_error(self) -> None:
        callback = _build_callback_mock(
            data=f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}",
            has_message=False,
        )
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.answer.assert_awaited_once_with(
            "ru:enchant-toast-error",
            show_alert=False,
        )
        enchant_uc.assert_not_awaited()
        assert uow.commits == 0

    async def test_unregistered_emits_not_registered_toast(self) -> None:
        callback = _build_callback_mock(
            data=f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}",
        )
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile(found=False)
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.answer.assert_awaited_once_with(
            "ru:enchant-not-registered",
            show_alert=False,
        )
        enchant_uc.assert_not_awaited()
        assert uow.commits == 0

    async def test_item_not_in_inventory_emits_item_not_found_toast(self) -> None:
        callback = _build_callback_mock(
            data=f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}",
        )
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile()
        # инвентарь без нужного предмета.
        get_inventory = _stub_get_inventory(
            view=InventoryView(items=(), scrolls=(_make_scroll(),)),
        )
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.answer.assert_awaited_once_with(
            "ru:enchant-error-item-not-found",
            show_alert=False,
        )
        enchant_uc.assert_not_awaited()
        assert uow.commits == 0

    @pytest.mark.parametrize(
        ("error", "expected_toast"),
        [
            (
                ItemNotFoundError(player_id=_PLAYER_ID, item_id=_ITEM_ID),
                "ru:enchant-error-item-not-found",
            ),
            (
                WrongScrollCategoryError(
                    scroll_category="weapon_scroll",
                    item_category="armor",
                ),
                "ru:enchant-error-wrong-category",
            ),
            (
                ScrollNotFoundError(player_id=_PLAYER_ID, scroll_id=_SCROLL_ID),
                "ru:enchant-error-scroll-not-found",
            ),
            (
                ScrollOutOfStockError(
                    player_id=_PLAYER_ID,
                    scroll_id=_SCROLL_ID,
                    requested_qty=1,
                    available_qty=0,
                ),
                "ru:enchant-error-out-of-stock",
            ),
            (ValueError("bad scroll_id"), "ru:enchant-error-bad-args"),
        ],
    )
    async def test_use_case_domain_error_maps_to_toast(
        self,
        error: Exception,
        expected_toast: str,
    ) -> None:
        callback = _build_callback_mock(
            data=f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}",
        )
        enchant_uc = _stub_enchant_item(error=error)
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.answer.assert_awaited_once_with(expected_toast, show_alert=False)
        enchant_uc.assert_awaited_once()
        # use-case был вызван внутри открытого uow — rollback на исключении.
        assert uow.commits == 0
        assert uow.rollbacks == 1

    async def test_happy_path_success_emits_toast_and_edits_message(self) -> None:
        callback = _build_callback_mock(
            data=f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}",
        )
        result = EnchantAttemptResult(
            outcome=RegularEnchantOutcome.SUCCESS,
            old_level=4,
            new_level=5,
            item_destroyed=False,
            item_dropped=False,
            idempotent=False,
        )
        enchant_uc = _stub_enchant_item(result=result)
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        # Use-case вызван с правильным idempotency_key.
        enchant_uc.assert_awaited_once()
        assert enchant_uc.await_args is not None
        kwargs = enchant_uc.await_args.kwargs
        assert kwargs["player_id"] == _PLAYER_ID
        assert kwargs["item_id"] == _ITEM_ID
        assert kwargs["scroll_id"] == _SCROLL_ID
        assert kwargs["idempotency_key"] == f"{_TG_USER_ID}:{_MESSAGE_ID}"
        # Ambient uow открылся и закоммитился.
        assert uow.commits == 1
        assert uow.rollbacks == 0
        # Toast + edit_text.
        callback.answer.assert_awaited_once_with(
            "ru:enchant-toast-confirmed",
            show_alert=False,
        )
        callback.message.edit_text.assert_awaited_once()
        edit_kwargs = callback.message.edit_text.await_args.kwargs
        assert "ru:enchant-success[" in edit_kwargs["text"]
        assert "old_level=4" in edit_kwargs["text"]
        assert "new_level=5" in edit_kwargs["text"]

    async def test_idempotent_result_emits_already_processed_toast(self) -> None:
        callback = _build_callback_mock(
            data=f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}",
        )
        result = EnchantAttemptResult(
            outcome=RegularEnchantOutcome.NO_EFFECT,
            old_level=2,
            new_level=2,
            item_destroyed=False,
            item_dropped=False,
            idempotent=True,
        )
        enchant_uc = _stub_enchant_item(result=result)
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.answer.assert_awaited_once_with(
            "ru:enchant-toast-already-processed",
            show_alert=False,
        )
        callback.message.edit_text.assert_awaited_once()
        edit_kwargs = callback.message.edit_text.await_args.kwargs
        assert edit_kwargs["text"] == "ru:enchant-idempotent"

    async def test_blessed_success_2_emits_success_template(self) -> None:
        callback = _build_callback_mock(
            data=f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID_BLESSED}",
        )
        result = EnchantAttemptResult(
            outcome=BlessedEnchantOutcome.SUCCESS_2,
            old_level=4,
            new_level=6,
            item_destroyed=False,
            item_dropped=False,
            idempotent=False,
        )
        enchant_uc = _stub_enchant_item(result=result)
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory(
            view=InventoryView(
                items=(_make_item(enchant_level=4),),
                scrolls=(
                    _make_scroll(
                        scroll_id=_SCROLL_ID_BLESSED,
                        blessed=True,
                    ),
                ),
            ),
        )
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.message.edit_text.assert_awaited_once()
        edit_kwargs = callback.message.edit_text.await_args.kwargs
        assert "ru:enchant-success[" in edit_kwargs["text"]

    async def test_destroy_outcome_renders_destroy_template(self) -> None:
        callback = _build_callback_mock(
            data=f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}",
        )
        result = EnchantAttemptResult(
            outcome=RegularEnchantOutcome.DESTROY,
            old_level=10,
            new_level=0,
            item_destroyed=True,
            item_dropped=False,
            idempotent=False,
        )
        enchant_uc = _stub_enchant_item(result=result)
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        callback.message.edit_text.assert_awaited_once()
        edit_kwargs = callback.message.edit_text.await_args.kwargs
        assert "ru:enchant-destroy[" in edit_kwargs["text"]

    async def test_confirm_edit_text_failure_does_not_propagate(self) -> None:
        callback = _build_callback_mock(
            data=f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}",
        )
        callback.message.edit_text.side_effect = RuntimeError("telegram API down")
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )

        # Toast всё равно отправлен.
        callback.answer.assert_awaited_once()
        # uow откоммичен.
        assert uow.commits == 1

    async def test_idempotency_key_stable_for_same_message(self) -> None:
        """Дважды нажав confirm на одной и той же warning-карточке — ключ
        одинаковый. Use-case на повторе вернёт `idempotent=True`, но это
        уже проверка use-case-уровня; здесь — что handler не «соляет»
        ключ ничем динамическим."""
        callback = _build_callback_mock(
            data=f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}",
            message_id=999,
        )
        enchant_uc = _stub_enchant_item()
        get_profile = _stub_get_profile()
        get_inventory = _stub_get_inventory()
        uow = FakeUnitOfWork()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        # Первый клик.
        await handle_enchant_callback(
            cast(CallbackQuery, callback),
            _identity(tg_user_id=42),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow,
            bundle,
            _RU,
        )
        # Второй клик той же кнопки — handler собирает ровно тот же ключ.
        callback2 = _build_callback_mock(
            data=f"enc:confirm:{_ITEM_ID}:{_SCROLL_ID}",
            message_id=999,
        )
        uow2 = FakeUnitOfWork()
        await handle_enchant_callback(
            cast(CallbackQuery, callback2),
            _identity(tg_user_id=42),
            cast(EnchantItem, enchant_uc),
            cast(GetInventory, get_inventory),
            cast(GetProfile, get_profile),
            uow2,
            bundle,
            _RU,
        )

        assert enchant_uc.await_args_list[0].kwargs["idempotency_key"] == "42:999"
        assert enchant_uc.await_args_list[1].kwargs["idempotency_key"] == "42:999"
