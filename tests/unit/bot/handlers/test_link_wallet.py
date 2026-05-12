"""Юнит-тесты `/link_wallet` + `/link_wallet_confirm` handler-ов (Спринт 4.1-D.6).

Покрываем:

1. ``/link_wallet`` в личке: prompt-карточка с inline-клавиатурой выбора
   валюты (TON / USDT) и вызов `GetProfile`.
2. ``/link_wallet`` в группе/прочих чатах → локализованный отказ, ни
   `GetProfile`, ни `LinkWallet` не зовутся.
3. ``/link_wallet`` для незарегистрированного игрока → ``link-wallet-not-registered``.
4. Callback ``link_wallet:select:<ton|usdt>`` → handler снимает
   клавиатуру и шлёт инструкции по соответствующей валюте.
5. Callback с битым ``callback_data`` → toast + снятие клавиатуры,
   `LinkWallet` не зовётся.
6. ``/link_wallet_confirm`` happy path (первая привязка) → зовётся
   `LinkWallet.execute(...)` с правильным `player_id` / `currency` /
   `address` / `proof`; ответ — ``link-wallet-confirm-linked``.
7. ``/link_wallet_confirm`` happy path (replace) → ответ
   ``link-wallet-confirm-relinked``.
8. ``/link_wallet_confirm`` без аргументов / с 1 / с 2 / с 4 → usage.
9. ``/link_wallet_confirm`` с unknown currency-токеном → unsupported.
10. ``/link_wallet_confirm`` для незарегистрированного игрока → not-registered.
11. ``/link_wallet_confirm`` в группе/прочих чатах → локализованный отказ.
12. ``/link_wallet_confirm`` с битым proof → `LinkWallet` бросает `ValueError`
    → handler рендерит ``link-wallet-confirm-invalid-proof``.
13. ``/link_wallet_confirm`` для уже привязанного адреса → `LinkWallet`
    бросает `WalletAlreadyLinkedError` → handler рендерит
    ``link-wallet-confirm-already-linked``.
14. Локаль из middleware пробрасывается в bundle (RU vs EN — маркерные
   строки). Без локали → fallback на `DEFAULT_LOCALE` (`en`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Chat, Message

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.monetization.link_wallet import (
    LinkWallet,
    LinkWalletResult,
)
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.link_wallet import (
    handle_link_wallet,
    handle_link_wallet_confirm,
    handle_link_wallet_select,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.monetization.entities import Wallet
from pipirik_wars.domain.monetization.errors import WalletAlreadyLinkedError
from pipirik_wars.domain.monetization.value_objects import Currency
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

# Реальные валидные TON-адреса для тестов: `Wallet` пропускает адрес
# через `TonAddress`/`UsdtJettonAddress` и более слабых форматов не принимает.
_TON_ADDR_FRIENDLY = "EQBvW8Z5huBkMJYdnfAEM5JqTNkuWX3diqYENkWsIL0XggGG"
_TON_ADDR_FRIENDLY_NEW = "0:" + "ab" * 32
_TON_ADDR_FRIENDLY_OLD = "0:" + "cd" * 32


# ────────────────────────── helpers ───────────────────────────────


def _build_message_mock(chat_type: str = "private") -> MagicMock:
    msg = MagicMock()
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    return msg


def _build_callback_mock(data: str = "link_wallet:select:ton") -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.data = data
    inner_message = MagicMock()
    inner_message.answer = AsyncMock()
    inner_message.edit_reply_markup = AsyncMock()
    callback.message = inner_message
    callback.answer = AsyncMock()
    return callback


def _identity(chat_kind: str = "private", tg_user_id: int = 100) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=None,
    )


def _command(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="link_wallet_confirm", args=args)


def _stub_get_profile(
    *,
    found: bool = True,
    player_id: int = 7,
) -> MagicMock:
    use_case = MagicMock(spec=GetProfile)
    if not found:
        use_case.execute = AsyncMock(return_value=None)
        return use_case
    fake_player = Player(
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
    )
    use_case.execute = AsyncMock(
        return_value=ProfileView(
            player=fake_player,
            display_name=DisplayName(value="Бананчик"),
        ),
    )
    return use_case


def _stub_link_wallet(
    *,
    replaced: bool = False,
    raise_error: Exception | None = None,
    address: str = _TON_ADDR_FRIENDLY,
    currency: Currency = Currency.TON_NANO,
    player_id: int = 7,
) -> MagicMock:
    use_case = MagicMock(spec=LinkWallet)
    if raise_error is not None:
        use_case.execute = AsyncMock(side_effect=raise_error)
        return use_case
    fake_wallet = Wallet(
        player_id=player_id,
        address=address,
        currency=currency,
        linked_at=datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC),
    )
    use_case.execute = AsyncMock(
        return_value=LinkWalletResult(wallet=fake_wallet, replaced=replaced),
    )
    return use_case


# ────────────────────────── /link_wallet ──────────────────────────


@pytest.mark.asyncio
class TestHandleLinkWallet:
    async def test_private_registered_renders_prompt_with_keyboard(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_awaited_once_with(tg_id=100)
        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert sent_text == "ru:link-wallet-prompt"
        # клавиатура — два ряда по одной кнопке.
        keyboard = msg.answer.await_args.kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard) == 2
        assert keyboard.inline_keyboard[0][0].callback_data == "link_wallet:select:ton"
        assert keyboard.inline_keyboard[0][0].text == "ru:link-wallet-button-ton"
        assert keyboard.inline_keyboard[1][0].callback_data == "link_wallet:select:usdt"
        assert keyboard.inline_keyboard[1][0].text == "ru:link-wallet-button-usdt"

    async def test_private_unregistered_replies_not_registered(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile(found=False)
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_awaited_once()
        msg.answer.assert_awaited_once_with("ru:link-wallet-not-registered")

    async def test_group_replies_group_message_no_use_case(self) -> None:
        msg = _build_message_mock("group")
        get_profile = _stub_get_profile()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet(
            cast(Message, msg),
            _identity("group"),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:link-wallet-group")

    async def test_supergroup_replies_group_message(self) -> None:
        msg = _build_message_mock("supergroup")
        get_profile = _stub_get_profile()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet(
            cast(Message, msg),
            _identity("supergroup"),
            cast(GetProfile, get_profile),
            bundle,
            Locale("en"),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("en:link-wallet-group")

    async def test_channel_replies_other_message(self) -> None:
        msg = _build_message_mock("channel")
        get_profile = _stub_get_profile()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet(
            cast(Message, msg),
            _identity("channel"),
            cast(GetProfile, get_profile),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:link-wallet-other")

    async def test_no_locale_defaults_to_english(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            bundle,
            None,  # locale не передана — fallback на DEFAULT_LOCALE = en
        )

        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("en:link-wallet-prompt")


# ────────────────────── callback link_wallet:select ───────────────


@pytest.mark.asyncio
class TestHandleLinkWalletSelect:
    async def test_select_ton_shows_instructions_and_strips_keyboard(self) -> None:
        callback = _build_callback_mock("link_wallet:select:ton")
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_select(
            cast(CallbackQuery, callback),
            _identity("private"),
            bundle,
            Locale("ru"),
        )

        callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        callback.message.answer.assert_awaited_once_with(
            "ru:link-wallet-instructions-ton",
        )

    async def test_select_usdt_shows_usdt_instructions(self) -> None:
        callback = _build_callback_mock("link_wallet:select:usdt")
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_select(
            cast(CallbackQuery, callback),
            _identity("private"),
            bundle,
            Locale("en"),
        )

        callback.message.answer.assert_awaited_once_with(
            "en:link-wallet-instructions-usdt",
        )

    async def test_invalid_callback_data_emits_toast_and_strips_keyboard(self) -> None:
        callback = _build_callback_mock("link_wallet:select:foo")
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_select(
            cast(CallbackQuery, callback),
            _identity("private"),
            bundle,
            Locale("ru"),
        )

        callback.answer.assert_awaited_once()
        toast_text = callback.answer.await_args.args[0]
        assert toast_text == "ru:link-wallet-toast-invalid"
        callback.message.answer.assert_not_awaited()
        callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)

    async def test_no_identity_short_circuits(self) -> None:
        callback = _build_callback_mock("link_wallet:select:ton")
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_select(
            cast(CallbackQuery, callback),
            None,
            bundle,
            Locale("ru"),
        )

        callback.answer.assert_not_awaited()
        callback.message.answer.assert_not_awaited()
        callback.message.edit_reply_markup.assert_not_awaited()


# ────────────────────── /link_wallet_confirm ──────────────────────


@pytest.mark.asyncio
class TestHandleLinkWalletConfirm:
    async def test_happy_path_first_link_calls_use_case_and_renders_linked(
        self,
    ) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile(player_id=42)
        link_wallet = _stub_link_wallet(
            replaced=False,
            address=_TON_ADDR_FRIENDLY,
            currency=Currency.TON_NANO,
            player_id=42,
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_confirm(
            cast(Message, msg),
            _command(f"ton {_TON_ADDR_FRIENDLY} proof123"),
            _identity("private"),
            cast(GetProfile, get_profile),
            cast(LinkWallet, link_wallet),
            bundle,
            Locale("ru"),
        )

        # use-case вызван с правильными аргументами.
        link_wallet.execute.assert_awaited_once()
        cmd = link_wallet.execute.await_args.args[0]
        assert cmd.player_id == 42
        assert cmd.currency == Currency.TON_NANO
        assert cmd.address == _TON_ADDR_FRIENDLY
        assert cmd.proof == "proof123"

        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert sent.startswith("ru:link-wallet-confirm-linked")
        assert f"address={_TON_ADDR_FRIENDLY}" in sent
        assert "currency=ton_nano" in sent

    async def test_happy_path_replace_renders_relinked(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        link_wallet = _stub_link_wallet(
            replaced=True,
            address=_TON_ADDR_FRIENDLY_NEW,
            currency=Currency.USDT_DECIMAL,
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_confirm(
            cast(Message, msg),
            _command(f"usdt {_TON_ADDR_FRIENDLY_NEW} proofZ"),
            _identity("private"),
            cast(GetProfile, get_profile),
            cast(LinkWallet, link_wallet),
            bundle,
            Locale("en"),
        )

        link_wallet.execute.assert_awaited_once()
        cmd = link_wallet.execute.await_args.args[0]
        assert cmd.currency == Currency.USDT_DECIMAL

        sent = msg.answer.await_args.args[0]
        assert sent.startswith("en:link-wallet-confirm-relinked")
        assert f"address={_TON_ADDR_FRIENDLY_NEW}" in sent
        assert "currency=usdt_decimal" in sent

    @pytest.mark.parametrize(
        "args",
        [None, "", "   ", "ton", "ton addr", "ton addr extra1 extra2"],
    )
    async def test_invalid_argument_count_renders_usage(self, args: str | None) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        link_wallet = _stub_link_wallet()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_confirm(
            cast(Message, msg),
            _command(args),
            _identity("private"),
            cast(GetProfile, get_profile),
            cast(LinkWallet, link_wallet),
            bundle,
            Locale("ru"),
        )

        link_wallet.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:link-wallet-confirm-usage")

    async def test_unsupported_currency_renders_unsupported(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        link_wallet = _stub_link_wallet()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_confirm(
            cast(Message, msg),
            _command(f"doge {_TON_ADDR_FRIENDLY} proof"),
            _identity("private"),
            cast(GetProfile, get_profile),
            cast(LinkWallet, link_wallet),
            bundle,
            Locale("ru"),
        )

        link_wallet.execute.assert_not_awaited()
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert sent.startswith("ru:link-wallet-confirm-unsupported")
        assert "code=doge" in sent

    async def test_unregistered_player_renders_not_registered(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile(found=False)
        link_wallet = _stub_link_wallet()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_confirm(
            cast(Message, msg),
            _command(f"ton {_TON_ADDR_FRIENDLY} proof"),
            _identity("private"),
            cast(GetProfile, get_profile),
            cast(LinkWallet, link_wallet),
            bundle,
            Locale("ru"),
        )

        link_wallet.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:link-wallet-confirm-not-registered")

    async def test_group_short_circuits(self) -> None:
        msg = _build_message_mock("group")
        get_profile = _stub_get_profile()
        link_wallet = _stub_link_wallet()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_confirm(
            cast(Message, msg),
            _command(f"ton {_TON_ADDR_FRIENDLY} proof"),
            _identity("group"),
            cast(GetProfile, get_profile),
            cast(LinkWallet, link_wallet),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        link_wallet.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:link-wallet-confirm-group")

    async def test_channel_short_circuits_with_other_message(self) -> None:
        msg = _build_message_mock("channel")
        get_profile = _stub_get_profile()
        link_wallet = _stub_link_wallet()
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_confirm(
            cast(Message, msg),
            _command(f"ton {_TON_ADDR_FRIENDLY} proof"),
            _identity("channel"),
            cast(GetProfile, get_profile),
            cast(LinkWallet, link_wallet),
            bundle,
            Locale("ru"),
        )

        get_profile.execute.assert_not_awaited()
        link_wallet.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:link-wallet-confirm-other")

    async def test_invalid_proof_value_error_renders_invalid_proof(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        link_wallet = _stub_link_wallet(
            raise_error=ValueError("LinkWallet: TON Connect proof verification failed"),
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_confirm(
            cast(Message, msg),
            _command(f"ton {_TON_ADDR_FRIENDLY} badproof"),
            _identity("private"),
            cast(GetProfile, get_profile),
            cast(LinkWallet, link_wallet),
            bundle,
            Locale("ru"),
        )

        link_wallet.execute.assert_awaited_once()
        msg.answer.assert_awaited_once_with("ru:link-wallet-confirm-invalid-proof")

    async def test_already_linked_renders_already_linked(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        link_wallet = _stub_link_wallet(
            raise_error=WalletAlreadyLinkedError(
                player_id=7,
                currency=Currency.TON_NANO,
                existing_address=_TON_ADDR_FRIENDLY_OLD,
            ),
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_confirm(
            cast(Message, msg),
            _command(f"ton {_TON_ADDR_FRIENDLY_OLD} proofX"),
            _identity("private"),
            cast(GetProfile, get_profile),
            cast(LinkWallet, link_wallet),
            bundle,
            Locale("ru"),
        )

        link_wallet.execute.assert_awaited_once()
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert sent.startswith("ru:link-wallet-confirm-already-linked")
        assert f"address={_TON_ADDR_FRIENDLY_OLD}" in sent
        assert "currency=ton_nano" in sent

    async def test_currency_token_case_insensitive(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        link_wallet = _stub_link_wallet(currency=Currency.TON_NANO)
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_confirm(
            cast(Message, msg),
            _command(f"TON {_TON_ADDR_FRIENDLY} proofY"),
            _identity("private"),
            cast(GetProfile, get_profile),
            cast(LinkWallet, link_wallet),
            bundle,
            Locale("ru"),
        )

        link_wallet.execute.assert_awaited_once()
        cmd = link_wallet.execute.await_args.args[0]
        assert cmd.currency == Currency.TON_NANO

    async def test_no_locale_defaults_to_english(self) -> None:
        msg = _build_message_mock("private")
        get_profile = _stub_get_profile()
        link_wallet = _stub_link_wallet(
            replaced=False,
            address=_TON_ADDR_FRIENDLY,
            currency=Currency.TON_NANO,
        )
        bundle = cast(IMessageBundle, FakeMessageBundle())

        await handle_link_wallet_confirm(
            cast(Message, msg),
            _command(f"ton {_TON_ADDR_FRIENDLY} proof"),
            _identity("private"),
            cast(GetProfile, get_profile),
            cast(LinkWallet, link_wallet),
            bundle,
            None,
        )

        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert sent.startswith("en:link-wallet-confirm-linked")
