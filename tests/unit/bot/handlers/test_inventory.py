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
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.inventory import (
    GetInventory,
    InventoryView,
    ItemView,
    ScrollView,
)
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.inventory import handle_inventory
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.balance.config import Rarity, Slot
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
from tests.fakes import FakeMessageBundle


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
