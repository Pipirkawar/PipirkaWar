"""Юнит-тесты `/roulette_paid`-handler-а (Спринт 4.1-A).

Покрывает:

* `/roulette_paid` в личке (success → prompt + keyboard, gate-fail,
  not-registered, group/channel/no-identity reject);
* buy-callback (`roulette_paid:buy_single` / `roulette_paid:buy_pack_10`)
  → `bot.send_invoice(...)` + снятие клавиатуры;
* `pre_checkout_query` → `ok=True/False` ветки (валид payload + сумма,
  unknown payload, currency mismatch, amount mismatch, нет paid-конфига);
* `successful_payment` → `SpinPaidRoulette.execute(...)` + рендер
  (success single, success pack-10, idempotent, thickness-gate-error,
  player-not-found, generic exception, foreign payload — игнор).

Вместо реального aiogram-Bot-а используется `MagicMock(spec=Bot)` с
`AsyncMock`-обёрнутыми методами — handler не зависит от транспорта.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, PreCheckoutQuery, SuccessfulPayment, User

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.monetization import (
    PaidRoulettePack,
    SpinPaidRoulette,
    SpinPaidRouletteResult,
)
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.roulette_paid import (
    handle_pre_checkout_query,
    handle_roulette_paid,
    handle_roulette_paid_buy,
    handle_successful_payment,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.monetization import (
    Currency,
    IdempotencyKey,
    Payment,
    PaymentStatus,
)
from pipirik_wars.domain.player import (
    DisplayName,
    Length,
    Player,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.domain.roulette import (
    RouletteOutcome,
    RouletteOutcomeKind,
    RouletteThicknessGateError,
)
from tests.fakes import FakeBalanceConfig, FakeMessageBundle
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)


def _msg(chat_type: str = "private") -> MagicMock:
    msg = MagicMock(spec=Message)
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


def _player(*, thickness_level: int = 2, player_id: int = 1) -> Player:
    return Player(
        id=player_id,
        tg_id=100,
        username=Username(value="alice"),
        length=Length(cm=5_000),
        thickness=Thickness(level=thickness_level),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _profile_view(*, thickness_level: int = 2, player_id: int = 1) -> ProfileView:
    return ProfileView(
        player=_player(thickness_level=thickness_level, player_id=player_id),
        display_name=DisplayName(value="Пипирик"),
    )


def _stub_profile(view: ProfileView | None = None) -> MagicMock:
    use_case = MagicMock(spec=GetProfile)
    use_case.execute = AsyncMock(return_value=view if view is not None else _profile_view())
    return use_case


def _stub_balance() -> IBalanceConfig:
    return FakeBalanceConfig(build_valid_balance())


def _bundle() -> IMessageBundle:
    return cast(IMessageBundle, FakeMessageBundle())


def _payment(*, idempotency_key: str = "paid_roulette:1:tg-charge-001") -> Payment:
    return Payment(
        player_id=1,
        currency=Currency.STARS,
        amount_native=1,
        idempotency_key=IdempotencyKey(idempotency_key),
        status=PaymentStatus.CONFIRMED,
        created_at=_NOW,
        provider_payment_id="tg-charge-001",
        confirmed_at=_NOW,
    )


def _spin_result(
    *,
    pack: PaidRoulettePack = PaidRoulettePack.SINGLE,
    outcomes: tuple[RouletteOutcome, ...] | None = None,
    spent_stars: int = 1,
    idempotent: bool = False,
) -> SpinPaidRouletteResult:
    if outcomes is None:
        outcomes = (RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42),)
    return SpinPaidRouletteResult(
        outcomes=outcomes,
        spent_stars=spent_stars,
        pack=pack,
        payment=_payment() if not idempotent else None,
        idempotent=idempotent,
    )


def _stub_spin(
    *,
    result: SpinPaidRouletteResult | None = None,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=SpinPaidRoulette)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
    else:
        use_case.execute = AsyncMock(return_value=result if result is not None else _spin_result())
    return use_case


# ---------------- /roulette_paid (command) ----------------


@pytest.mark.asyncio
class TestHandleRoulettePaidCommand:
    async def test_private_success_shows_prompt_with_keyboard(self) -> None:
        msg = _msg("private")
        get_profile = _stub_profile(_profile_view(thickness_level=2))

        await handle_roulette_paid(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("ru:roulette-paid-prompt[")
        kwargs = msg.answer.await_args.kwargs
        kb = kwargs["reply_markup"]
        (single_btn,) = kb.inline_keyboard[0]
        (pack10_btn,) = kb.inline_keyboard[1]
        assert single_btn.callback_data == "roulette_paid:buy_single"
        assert pack10_btn.callback_data == "roulette_paid:buy_pack_10"

    async def test_group_chat_rejected(self) -> None:
        msg = _msg("group")
        get_profile = _stub_profile()

        await handle_roulette_paid(
            cast(Message, msg),
            _identity("group"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:roulette-paid-group")
        get_profile.execute.assert_not_awaited()

    async def test_channel_or_no_identity_rejected(self) -> None:
        msg = _msg("channel")
        get_profile = _stub_profile()

        await handle_roulette_paid(
            cast(Message, msg),
            None,
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:roulette-paid-other")
        get_profile.execute.assert_not_awaited()

    async def test_player_not_found(self) -> None:
        msg = _msg("private")
        get_profile = MagicMock(spec=GetProfile)
        get_profile.execute = AsyncMock(return_value=None)

        await handle_roulette_paid(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:roulette-paid-not-registered")

    async def test_thickness_gate_blocks(self) -> None:
        # `Thickness.level` начинается с 1, поэтому имитируем gate тем,
        # что поднимаем `paid.min_thickness_level` в конфиге до 2.
        # У игрока thickness=1 → ниже порога → отказ.
        msg = _msg("private")
        get_profile = _stub_profile(_profile_view(thickness_level=1))

        balance = build_valid_balance()
        assert balance.roulette.paid is not None
        balance = balance.model_copy(
            update={
                "roulette": balance.roulette.model_copy(
                    update={
                        "paid": balance.roulette.paid.model_copy(update={"min_thickness_level": 2})
                    }
                )
            }
        )

        await handle_roulette_paid(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            FakeBalanceConfig(balance),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("ru:roulette-paid-requirement-thickness[")
        kwargs = msg.answer.await_args.kwargs
        # Без клавиатуры на gate-fail.
        assert "reply_markup" not in kwargs


# ---------------- buy-callback ----------------


def _callback(
    *,
    data: str | None,
    has_message: bool = True,
) -> MagicMock:
    cb = MagicMock()
    cb.data = data
    cb.answer = AsyncMock()
    cb.from_user = MagicMock()
    cb.from_user.id = 100
    if has_message:
        msg = MagicMock()
        msg.chat = Chat(id=42, type="private")
        msg.message_id = 555
        msg.edit_reply_markup = AsyncMock()
        cb.message = msg
    else:
        cb.message = None
    return cb


def _stub_bot() -> MagicMock:
    bot = MagicMock(spec=Bot)
    bot.send_invoice = AsyncMock()
    bot.answer_pre_checkout_query = AsyncMock()
    return bot


@pytest.mark.asyncio
class TestHandleRoulettePaidBuyCallback:
    async def test_buy_single_sends_invoice(self) -> None:
        cb = _callback(data="roulette_paid:buy_single")
        bot = _stub_bot()

        await handle_roulette_paid_buy(
            cb,
            _identity("private"),
            cast(Bot, bot),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        bot.send_invoice.assert_awaited_once()
        kwargs = bot.send_invoice.await_args.kwargs
        assert kwargs["chat_id"] == 42
        assert kwargs["currency"] == "XTR"
        assert kwargs["payload"] == "paid_roulette:single"
        assert len(kwargs["prices"]) == 1
        assert kwargs["prices"][0].amount == 1
        # Клавиатура снята до отправки invoice-а.
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        cb.answer.assert_awaited_once()

    async def test_buy_pack_10_sends_invoice(self) -> None:
        cb = _callback(data="roulette_paid:buy_pack_10")
        bot = _stub_bot()

        await handle_roulette_paid_buy(
            cb,
            _identity("private"),
            cast(Bot, bot),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        bot.send_invoice.assert_awaited_once()
        kwargs = bot.send_invoice.await_args.kwargs
        assert kwargs["payload"] == "paid_roulette:pack_10"
        assert kwargs["prices"][0].amount == 9

    async def test_invalid_callback_data_handled(self) -> None:
        cb = _callback(data="roulette_paid:buy_pack_99")
        bot = _stub_bot()

        await handle_roulette_paid_buy(
            cb,
            _identity("private"),
            cast(Bot, bot),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        bot.send_invoice.assert_not_awaited()
        cb.answer.assert_awaited_once()
        # Клавиатура снята даже на ошибке.
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)

    async def test_no_identity_short_circuits(self) -> None:
        cb = _callback(data="roulette_paid:buy_single")
        bot = _stub_bot()

        await handle_roulette_paid_buy(
            cb,
            None,
            cast(Bot, bot),
            _stub_balance(),
            _bundle(),
            Locale("ru"),
        )

        bot.send_invoice.assert_not_awaited()


# ---------------- pre_checkout_query ----------------


def _pre_checkout(
    *,
    payload: str = "paid_roulette:single",
    currency: str = "XTR",
    total_amount: int = 1,
) -> MagicMock:
    q = MagicMock(spec=PreCheckoutQuery)
    q.id = "test-pre-checkout-id"
    q.invoice_payload = payload
    q.currency = currency
    q.total_amount = total_amount
    q.from_user = MagicMock(spec=User)
    q.from_user.id = 100
    return q


@pytest.mark.asyncio
class TestHandlePreCheckoutQuery:
    async def test_valid_single_payload_acks_ok(self) -> None:
        bot = _stub_bot()
        await handle_pre_checkout_query(
            _pre_checkout(payload="paid_roulette:single", total_amount=1),
            cast(Bot, bot),
            _stub_balance(),
        )
        bot.answer_pre_checkout_query.assert_awaited_once_with(
            pre_checkout_query_id="test-pre-checkout-id",
            ok=True,
        )

    async def test_valid_pack_10_payload_acks_ok(self) -> None:
        bot = _stub_bot()
        await handle_pre_checkout_query(
            _pre_checkout(payload="paid_roulette:pack_10", total_amount=9),
            cast(Bot, bot),
            _stub_balance(),
        )
        bot.answer_pre_checkout_query.assert_awaited_once_with(
            pre_checkout_query_id="test-pre-checkout-id",
            ok=True,
        )

    async def test_unsupported_currency_rejects(self) -> None:
        bot = _stub_bot()
        await handle_pre_checkout_query(
            _pre_checkout(currency="USD"),
            cast(Bot, bot),
            _stub_balance(),
        )
        kwargs = bot.answer_pre_checkout_query.await_args.kwargs
        assert kwargs["ok"] is False
        assert "USD" in kwargs["error_message"]

    async def test_invalid_payload_rejects(self) -> None:
        bot = _stub_bot()
        await handle_pre_checkout_query(
            _pre_checkout(payload="some-other-flow:foo"),
            cast(Bot, bot),
            _stub_balance(),
        )
        kwargs = bot.answer_pre_checkout_query.await_args.kwargs
        assert kwargs["ok"] is False
        assert "payload" in kwargs["error_message"].lower()

    async def test_amount_mismatch_rejects(self) -> None:
        bot = _stub_bot()
        await handle_pre_checkout_query(
            _pre_checkout(payload="paid_roulette:single", total_amount=999),
            cast(Bot, bot),
            _stub_balance(),
        )
        kwargs = bot.answer_pre_checkout_query.await_args.kwargs
        assert kwargs["ok"] is False
        assert "price" in kwargs["error_message"].lower()


# ---------------- successful_payment ----------------


def _msg_with_payment(
    *,
    payload: str = "paid_roulette:single",
    total_amount: int = 1,
    charge_id: str = "tg-charge-001",
) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=42, type="private")
    msg.answer = AsyncMock()
    payment = MagicMock(spec=SuccessfulPayment)
    payment.invoice_payload = payload
    payment.total_amount = total_amount
    payment.currency = "XTR"
    payment.telegram_payment_charge_id = charge_id
    payment.provider_payment_charge_id = ""
    msg.successful_payment = payment
    return msg


@pytest.mark.asyncio
class TestHandleSuccessfulPayment:
    async def test_single_success_renders_length_outcome(self) -> None:
        msg = _msg_with_payment(payload="paid_roulette:single")
        spin = _stub_spin(
            result=_spin_result(
                pack=PaidRoulettePack.SINGLE,
                outcomes=(RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=42),),
                spent_stars=1,
            )
        )

        await handle_successful_payment(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, _stub_profile()),
            cast(SpinPaidRoulette, spin),
            _bundle(),
            Locale("ru"),
        )

        spin.execute.assert_awaited_once()
        cmd = spin.execute.await_args.args[0]
        assert cmd.player_id == 1
        assert cmd.pack is PaidRoulettePack.SINGLE
        assert cmd.idempotency_key.value == "paid_roulette:1:tg-charge-001"
        assert cmd.provider_payment_id == "tg-charge-001"
        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("ru:roulette-paid-result-single-length[")

    async def test_pack_10_success_renders_aggregated(self) -> None:
        outcomes = tuple(
            RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=10) for _ in range(10)
        )
        msg = _msg_with_payment(payload="paid_roulette:pack_10", total_amount=9)
        spin = _stub_spin(
            result=_spin_result(
                pack=PaidRoulettePack.PACK_10,
                outcomes=outcomes,
                spent_stars=9,
            )
        )

        await handle_successful_payment(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, _stub_profile()),
            cast(SpinPaidRoulette, spin),
            _bundle(),
            Locale("ru"),
        )

        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("ru:roulette-paid-result-pack-10[")
        assert "n_spins=10" in sent_text
        assert "total_length_cm=100" in sent_text

    async def test_idempotent_replay_short_circuits(self) -> None:
        msg = _msg_with_payment()
        spin = _stub_spin(
            result=_spin_result(
                pack=PaidRoulettePack.SINGLE,
                outcomes=(),
                spent_stars=0,
                idempotent=True,
            )
        )

        await handle_successful_payment(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, _stub_profile()),
            cast(SpinPaidRoulette, spin),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:roulette-paid-result-idempotent")

    async def test_thickness_gate_error(self) -> None:
        msg = _msg_with_payment()
        spin = _stub_spin(
            error=RouletteThicknessGateError(
                player_id=1,
                thickness_level=1,
                required_level=2,
            )
        )

        await handle_successful_payment(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, _stub_profile()),
            cast(SpinPaidRoulette, spin),
            _bundle(),
            Locale("ru"),
        )

        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("ru:roulette-paid-requirement-thickness[")

    async def test_player_not_found_error(self) -> None:
        msg = _msg_with_payment()
        spin = _stub_spin(error=PlayerNotFoundError(tg_id=100))

        await handle_successful_payment(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, _stub_profile()),
            cast(SpinPaidRoulette, spin),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:roulette-paid-not-registered")

    async def test_unexpected_error_falls_back_to_toast_text(self) -> None:
        msg = _msg_with_payment()
        spin = _stub_spin(error=RuntimeError("DB connection lost"))

        await handle_successful_payment(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, _stub_profile()),
            cast(SpinPaidRoulette, spin),
            _bundle(),
            Locale("ru"),
        )

        msg.answer.assert_awaited_once_with("ru:roulette-paid-toast-error")

    async def test_foreign_payload_silently_ignored(self) -> None:
        msg = _msg_with_payment(payload="some-other-flow:foo")
        spin = _stub_spin()

        await handle_successful_payment(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, _stub_profile()),
            cast(SpinPaidRoulette, spin),
            _bundle(),
            Locale("ru"),
        )

        spin.execute.assert_not_awaited()
        msg.answer.assert_not_awaited()

    async def test_player_not_found_at_lookup_short_circuits(self) -> None:
        msg = _msg_with_payment()
        get_profile = MagicMock(spec=GetProfile)
        get_profile.execute = AsyncMock(return_value=None)
        spin = _stub_spin()

        await handle_successful_payment(
            cast(Message, msg),
            _identity("private"),
            cast(GetProfile, get_profile),
            cast(SpinPaidRoulette, spin),
            _bundle(),
            Locale("ru"),
        )

        spin.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:roulette-paid-not-registered")
