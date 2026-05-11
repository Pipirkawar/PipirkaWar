"""Юнит-тесты `/claim_prize <lot_id>` handler-а (Спринт 4.1-D, D.7.b).

Покрываем:

1.  `/claim_prize 42` в личке → happy-path success (CLAIMED).
2.  `/claim_prize 42` → happy-path refund (fee overflow).
3.  Чат-гарды: группа / other / без tg_identity.
4.  Незарегистрированный игрок → `claim-prize-not-registered`.
5.  Без аргументов / с лишними → `claim-prize-usage`.
6.  Невалидный lot_id (не число / ≤ 0) → `claim-prize-invalid-lot-id`.
7.  Лот не найден → `claim-prize-not-found`.
8.  Лот уже забран (CLAIMED) → `claim-prize-already-claimed`.
9.  Лот не в RESERVED (ACTIVE/REFUNDED) → `claim-prize-not-reserved`.
10. Кошелёк не привязан → `claim-prize-wallet-not-linked`.
11. Race-condition: PrizeLotNotFoundError → `claim-prize-not-found`.
12. Race-condition: PrizeLotStatusTransitionError(CLAIMED) →
    `claim-prize-already-claimed`.
13. Race-condition: WalletNotLinkedError → `claim-prize-wallet-not-linked`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.monetization.claim_prize import (
    ClaimPrize,
    ClaimPrizeResult,
)
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.claim_prize import handle_claim_prize
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.monetization.entities import (
    PrizeLot,
    PrizeLotStatus,
    Wallet,
)
from pipirik_wars.domain.monetization.errors import (
    PrizeLotNotFoundError,
    PrizeLotStatusTransitionError,
    WalletNotLinkedError,
)
from pipirik_wars.domain.monetization.ports import (
    IPrizeLotRepository,
    IWalletRepository,
    PayoutResult,
)
from pipirik_wars.domain.monetization.value_objects import Currency, FeeBufferAmount
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

_WALLET_ADDR = "EQBvW8Z5huBkMJYdnfAEM5JqTNkuWX3diqYENkWsIL0XggGG"
_NOW = datetime(2026, 5, 11, 14, 0, 0, tzinfo=UTC)

# ────────────────────────── helpers ───────────────────────────────


def _msg(chat_type: str = "private") -> MagicMock:
    m = MagicMock()
    m.chat = Chat(id=42, type=chat_type)
    m.answer = AsyncMock()
    return m


def _cmd(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="claim_prize", args=args)


def _identity(chat_kind: str = "private", tg_user_id: int = 100) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=None,
    )


def _get_profile(
    *,
    found: bool = True,
    player_id: int = 7,
) -> MagicMock:
    use_case = MagicMock(spec=GetProfile)
    if not found:
        use_case.execute = AsyncMock(return_value=None)
        return use_case
    p = Player(
        id=player_id,
        tg_id=100,
        username=Username(value="alice"),
        length=Length(cm=47),
        thickness=Thickness(level=5),
        title=Title.NEWBIE,
        name=PlayerName(value="Test"),
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )
    use_case.execute = AsyncMock(
        return_value=ProfileView(player=p, display_name=DisplayName(value="Alice")),
    )
    return use_case


def _lot(
    *,
    lot_id: int = 42,
    status: PrizeLotStatus = PrizeLotStatus.RESERVED,
    currency: Currency = Currency.TON_NANO,
    amount_native: int = 2_500_000_000,
    fee_buffer: int = 100_000_000,
) -> PrizeLot:
    claimed_at = _NOW if status is PrizeLotStatus.CLAIMED else None
    return PrizeLot(
        id=lot_id,
        currency=currency,
        amount_native=amount_native,
        fee_buffer_native=FeeBufferAmount(fee_buffer),
        status=status,
        created_at=_NOW,
        claimed_at=claimed_at,
    )


def _wallet(
    *,
    player_id: int = 7,
    currency: Currency = Currency.TON_NANO,
) -> Wallet:
    return Wallet(
        player_id=player_id,
        address=_WALLET_ADDR,
        currency=currency,
        linked_at=_NOW,
    )


def _lot_repo(
    lot: PrizeLot | None = None,
) -> MagicMock:
    repo = MagicMock(spec=IPrizeLotRepository)
    repo.get_by_id = AsyncMock(return_value=lot)
    return repo


def _wallet_repo(
    wallet: Wallet | None = None,
) -> MagicMock:
    repo = MagicMock(spec=IWalletRepository)
    repo.get_by_player_and_currency = AsyncMock(return_value=wallet)
    return repo


def _claim_prize_use_case(
    *,
    claimed: bool = True,
    refunded: bool = False,
    raise_error: Exception | None = None,
    lot_id: int = 42,
) -> MagicMock:
    uc = MagicMock(spec=ClaimPrize)
    if raise_error is not None:
        uc.execute = AsyncMock(side_effect=raise_error)
        return uc
    payout = PayoutResult(tx_hash="abc123", actual_fee_native=8_000_000) if claimed else None
    uc.execute = AsyncMock(
        return_value=ClaimPrizeResult(
            claimed=claimed,
            refunded=refunded,
            payout=payout,
            lot_id=lot_id,
        ),
    )
    return uc


async def _call(
    *,
    args: str | None = "42",
    chat_kind: str = "private",
    tg_identity: TgIdentity | None = None,
    get_profile: MagicMock | None = None,
    claim_prize: MagicMock | None = None,
    lot_repo: MagicMock | None = None,
    wallet_repo: MagicMock | None = None,
    locale: Locale | None = None,
) -> MagicMock:
    """Общий хелпер вызова handler-а. Возвращает message mock."""
    message = _msg(chat_kind)
    tg = tg_identity or _identity(chat_kind)
    bundle = cast(IMessageBundle, FakeMessageBundle())
    gp = get_profile or _get_profile()
    cp = claim_prize or _claim_prize_use_case()
    lr = lot_repo or _lot_repo(_lot())
    wr = wallet_repo or _wallet_repo(_wallet())

    await handle_claim_prize(
        cast(Message, message),
        _cmd(args),
        tg,
        cast(GetProfile, gp),
        cast(ClaimPrize, cp),
        cast(IPrizeLotRepository, lr),
        cast(IWalletRepository, wr),
        bundle,
        locale,
    )
    return message


# ────────────────────────── тесты ─────────────────────────────────


@pytest.mark.asyncio
class TestClaimPrizeChatGuards:
    async def test_group_renders_group_message(self) -> None:
        msg = await _call(chat_kind="group")
        text = msg.answer.call_args[0][0]
        assert "claim-prize-group" in text

    async def test_supergroup_renders_group_message(self) -> None:
        msg = await _call(chat_kind="supergroup")
        text = msg.answer.call_args[0][0]
        assert "claim-prize-group" in text

    async def test_other_chat_renders_other_message(self) -> None:
        msg = await _call(
            chat_kind="channel",
            tg_identity=TgIdentity(
                tg_user_id=100,
                chat_id=42,
                chat_kind="channel",
                language_code=None,
            ),
        )
        text = msg.answer.call_args[0][0]
        assert "claim-prize-other" in text

    async def test_no_tg_identity_renders_other_message(self) -> None:
        message = _msg("private")
        bundle = cast(IMessageBundle, FakeMessageBundle())
        gp = _get_profile()
        cp = _claim_prize_use_case()
        lr = _lot_repo(_lot())
        wr = _wallet_repo(_wallet())

        await handle_claim_prize(
            cast(Message, message),
            _cmd("42"),
            None,
            cast(GetProfile, gp),
            cast(ClaimPrize, cp),
            cast(IPrizeLotRepository, lr),
            cast(IWalletRepository, wr),
            bundle,
            None,
        )
        text = message.answer.call_args[0][0]
        assert "claim-prize-other" in text


@pytest.mark.asyncio
class TestClaimPrizeArgParsing:
    async def test_no_args_renders_usage(self) -> None:
        msg = await _call(args=None)
        text = msg.answer.call_args[0][0]
        assert "claim-prize-usage" in text

    async def test_empty_args_renders_usage(self) -> None:
        msg = await _call(args="")
        text = msg.answer.call_args[0][0]
        assert "claim-prize-usage" in text

    async def test_extra_args_renders_usage(self) -> None:
        msg = await _call(args="42 99")
        text = msg.answer.call_args[0][0]
        assert "claim-prize-usage" in text

    async def test_invalid_lot_id_str(self) -> None:
        msg = await _call(args="abc")
        text = msg.answer.call_args[0][0]
        assert "claim-prize-invalid-lot-id" in text
        assert "raw=abc" in text

    async def test_zero_lot_id(self) -> None:
        msg = await _call(args="0")
        text = msg.answer.call_args[0][0]
        assert "claim-prize-invalid-lot-id" in text

    async def test_negative_lot_id(self) -> None:
        msg = await _call(args="-1")
        text = msg.answer.call_args[0][0]
        assert "claim-prize-invalid-lot-id" in text


@pytest.mark.asyncio
class TestClaimPrizeNotRegistered:
    async def test_not_registered_renders_message(self) -> None:
        msg = await _call(get_profile=_get_profile(found=False))
        text = msg.answer.call_args[0][0]
        assert "claim-prize-not-registered" in text


@pytest.mark.asyncio
class TestClaimPrizeLotChecks:
    async def test_lot_not_found(self) -> None:
        msg = await _call(lot_repo=_lot_repo(None))
        text = msg.answer.call_args[0][0]
        assert "claim-prize-not-found" in text
        assert "lot_id=42" in text

    async def test_lot_already_claimed(self) -> None:
        msg = await _call(
            lot_repo=_lot_repo(_lot(status=PrizeLotStatus.CLAIMED)),
        )
        text = msg.answer.call_args[0][0]
        assert "claim-prize-already-claimed" in text
        assert "lot_id=42" in text

    async def test_lot_active_not_reserved(self) -> None:
        msg = await _call(
            lot_repo=_lot_repo(_lot(status=PrizeLotStatus.ACTIVE)),
        )
        text = msg.answer.call_args[0][0]
        assert "claim-prize-not-reserved" in text
        assert "status=active" in text

    async def test_lot_refunded_not_reserved(self) -> None:
        msg = await _call(
            lot_repo=_lot_repo(_lot(status=PrizeLotStatus.REFUNDED)),
        )
        text = msg.answer.call_args[0][0]
        assert "claim-prize-not-reserved" in text
        assert "status=refunded" in text


@pytest.mark.asyncio
class TestClaimPrizeWalletCheck:
    async def test_wallet_not_linked(self) -> None:
        msg = await _call(wallet_repo=_wallet_repo(None))
        text = msg.answer.call_args[0][0]
        assert "claim-prize-wallet-not-linked" in text
        assert "currency=ton_nano" in text


@pytest.mark.asyncio
class TestClaimPrizeSuccess:
    async def test_success_renders_with_tx_hash(self) -> None:
        msg = await _call()
        text = msg.answer.call_args[0][0]
        assert "claim-prize-success" in text
        assert "tx_hash=abc123" in text
        assert "address=" + _WALLET_ADDR in text

    async def test_success_en_locale(self) -> None:
        msg = await _call(locale=Locale("en"))
        text = msg.answer.call_args[0][0]
        assert text.startswith("en:")


@pytest.mark.asyncio
class TestClaimPrizeRefund:
    async def test_refund_renders(self) -> None:
        msg = await _call(
            claim_prize=_claim_prize_use_case(claimed=False, refunded=True),
        )
        text = msg.answer.call_args[0][0]
        assert "claim-prize-refund" in text
        assert "lot_id=42" in text
        assert "currency=ton_nano" in text


@pytest.mark.asyncio
class TestClaimPrizeRaceConditions:
    async def test_race_lot_vanished(self) -> None:
        msg = await _call(
            claim_prize=_claim_prize_use_case(
                raise_error=PrizeLotNotFoundError(lot_id=42),
            ),
        )
        text = msg.answer.call_args[0][0]
        assert "claim-prize-not-found" in text

    async def test_race_lot_already_claimed(self) -> None:
        msg = await _call(
            claim_prize=_claim_prize_use_case(
                raise_error=PrizeLotStatusTransitionError(
                    lot_id=42,
                    from_status=PrizeLotStatus.CLAIMED,
                    to_status=PrizeLotStatus.CLAIMED,
                ),
            ),
        )
        text = msg.answer.call_args[0][0]
        assert "claim-prize-already-claimed" in text

    async def test_race_lot_status_changed_to_active(self) -> None:
        msg = await _call(
            claim_prize=_claim_prize_use_case(
                raise_error=PrizeLotStatusTransitionError(
                    lot_id=42,
                    from_status=PrizeLotStatus.ACTIVE,
                    to_status=PrizeLotStatus.CLAIMED,
                ),
            ),
        )
        text = msg.answer.call_args[0][0]
        assert "claim-prize-not-reserved" in text
        assert "status=active" in text

    async def test_race_wallet_unlinked(self) -> None:
        msg = await _call(
            claim_prize=_claim_prize_use_case(
                raise_error=WalletNotLinkedError(
                    player_id=7,
                    currency=Currency.TON_NANO,
                ),
            ),
        )
        text = msg.answer.call_args[0][0]
        assert "claim-prize-wallet-not-linked" in text
