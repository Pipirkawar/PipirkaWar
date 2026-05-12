"""Unit-тесты handler-а `/prize_pool` (Спринт 4.1-E, E.12)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale, MessageKey
from pipirik_wars.application.monetization import (
    CurrencyPoolStatus,
    GetPrizePoolStatus,
    GetPrizePoolStatusOutput,
)
from pipirik_wars.bot.handlers.admin_prize_pool import (
    REPLY_NON_PRIVATE_RU,
    handle_prize_pool,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.monetization import Currency, PayoutFreeze

_RU = Locale("ru")


class _StubBundle(IMessageBundle):
    def format(
        self,
        key: MessageKey,
        *,
        locale: Locale,
        **kwargs: object,
    ) -> str:
        params = ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"{key}|{locale.code}|{params}"


@pytest.fixture
def bundle() -> IMessageBundle:
    return _StubBundle()


def _msg_mock(chat_type: str = "private") -> MagicMock:
    msg = MagicMock()
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    return msg


def _identity(chat_kind: str = "private", tg_user_id: int = 42) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=None,
    )


def _stub_uc(
    *,
    output: GetPrizePoolStatusOutput | None = None,
) -> GetPrizePoolStatus:
    fake = MagicMock(spec=GetPrizePoolStatus)
    if output is not None:
        fake.execute = AsyncMock(return_value=output)
    else:
        fake.execute = AsyncMock()
    return cast(GetPrizePoolStatus, fake)


def _output_unfrozen() -> GetPrizePoolStatusOutput:
    return GetPrizePoolStatusOutput(
        per_currency=(
            CurrencyPoolStatus(
                currency=Currency.STARS,
                balance_native=1000,
                active_lots=5,
                reserved_lots=1,
                claimed_lots=42,
                refunded_lots=0,
            ),
            CurrencyPoolStatus(
                currency=Currency.TON_NANO,
                balance_native=2_000_000_000,
                active_lots=3,
                reserved_lots=0,
                claimed_lots=10,
                refunded_lots=1,
            ),
            CurrencyPoolStatus(
                currency=Currency.USDT_DECIMAL,
                balance_native=5_000_000,
                active_lots=2,
                reserved_lots=0,
                claimed_lots=7,
                refunded_lots=0,
            ),
        ),
        freeze=PayoutFreeze.unfrozen(),
    )


def _output_frozen() -> GetPrizePoolStatusOutput:
    return GetPrizePoolStatusOutput(
        per_currency=(),
        freeze=PayoutFreeze.frozen(
            admin_id=7,
            at=datetime(2026, 5, 12, 7, 0, tzinfo=UTC),
            reason="Test freeze.",
        ),
    )


@pytest.mark.asyncio
class TestHandlePrizePool:
    async def test_non_private_chat_replies_only_dm(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        uc = _stub_uc()
        await handle_prize_pool(
            message=cast(Message, msg),
            tg_identity=_identity(chat_kind="group"),
            get_prize_pool_status=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_missing_identity_replies_only_dm(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc()
        await handle_prize_pool(
            message=cast(Message, msg),
            tg_identity=None,
            get_prize_pool_status=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_authorization_error_replies_not_authorized(
        self,
        bundle: IMessageBundle,
    ) -> None:
        msg = _msg_mock()
        uc = _stub_uc()
        uc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=AuthorizationError(requirement="x", detail="y"),
        )
        await handle_prize_pool(
            message=cast(Message, msg),
            tg_identity=_identity(),
            get_prize_pool_status=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-prize-pool-not-authorized" in text

    async def test_renders_unfrozen_snapshot(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc(output=_output_unfrozen())
        await handle_prize_pool(
            message=cast(Message, msg),
            tg_identity=_identity(),
            get_prize_pool_status=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        # Header + per-currency rows + unfrozen tail.
        assert "admin-prize-pool-header" in text
        assert "admin-prize-pool-row" in text
        assert "stars" in text  # Currency.STARS.value
        assert "ton_nano" in text
        assert "usdt_decimal" in text
        assert "admin-prize-pool-unfrozen" in text
        assert "admin-prize-pool-frozen" not in text

    async def test_renders_frozen_snapshot(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc(output=_output_frozen())
        await handle_prize_pool(
            message=cast(Message, msg),
            tg_identity=_identity(),
            get_prize_pool_status=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-prize-pool-header" in text
        assert "admin-prize-pool-frozen" in text
        assert "admin-prize-pool-unfrozen" not in text
        assert "admin_id=7" in text
        assert "reason=Test freeze." in text

    async def test_default_locale_when_none(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_uc(output=_output_unfrozen())
        await handle_prize_pool(
            message=cast(Message, msg),
            tg_identity=_identity(),
            get_prize_pool_status=uc,
            bundle=bundle,
            locale=None,
        )
        text = msg.answer.await_args.args[0]
        assert f"|{DEFAULT_LOCALE.code}|" in text
