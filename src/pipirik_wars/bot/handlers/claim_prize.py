"""`/claim_prize <lot_id>` + `claim_prize:<lot_id>` callback handlers (Спринт 4.1-D, D.7.b/D.7.c).

`/claim_prize <lot_id>` (личка-only) — игрок забирает зарезервированный
крипто-лот, выпавший ему в результате рулетки. Поток:

1. Парсим `lot_id` из аргументов команды (положительное целое).
2. Чат-гард: только в личке + игрок зарегистрирован (`/start`).
3. Подгружаем лот: `IPrizeLotRepository.get_by_id(lot_id)`.
   * Нет — `not_found(lot_id)`.
   * Статус `CLAIMED` — `already_claimed(lot_id)` (idempotency UX).
   * Статус не `RESERVED` — `not_reserved(lot_id, status=...)`.
4. Подгружаем привязанный кошелёк по `(player_id, lot.currency)`:
   * Нет — `wallet_not_linked(currency=lot.currency.value)`.
5. Вызываем ``ClaimPrize.execute(ClaimPrizeCommand(...))``.
   * `ClaimPrizeResult.claimed=True` → `success(...)` с `tx_hash`.
   * `ClaimPrizeResult.refunded=True` → `refund(...)` (комиссия съела
     буфер, лот возвращён в пул).
6. Доменные ошибки от use-case-а (`PrizeLotNotFoundError`,
   `PrizeLotStatusTransitionError`, `WalletNotLinkedError`) могут
   прилететь из-за race-condition между pre-load и use-case-execute —
   обрабатываем теми же ветками, что и пред-проверки.

`claim_prize:<lot_id>` callback — приходит от inline-кнопки «Забрать
приз», которую рисует ``ClaimPrizePresenter.prompt_keyboard(...)`` (и
roulette-handler-ы при `RouletteOutcomeKind.CRYPTO_LOT`). Callback
снимает клавиатуру у исходного сообщения, парсит `lot_id` и вызывает
ту же логику, что и message-handler `/claim_prize`. На битый
callback_data — toast `toast_invalid` + снятие клавиатуры (повторный
клик бесполезен).

Локали ключей `claim-prize-*` лежат в `locales/{ru,en}.ftl`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Final, TypeAlias

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.monetization.claim_prize import (
    ClaimPrize,
    ClaimPrizeCommand,
    ClaimPrizeResult,
)
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.claim_prize import (
    ClaimPrizePresenter,
    claim_prize_callback_data,
    parse_claim_prize_callback_data,
)
from pipirik_wars.domain.monetization.entities import PrizeLotStatus
from pipirik_wars.domain.monetization.errors import (
    PrizeLotNotFoundError,
    PrizeLotStatusTransitionError,
    WalletNotLinkedError,
)
from pipirik_wars.domain.monetization.ports import (
    IPrizeLotRepository,
    IWalletRepository,
)

router = Router(name="claim_prize")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

_ARG_COUNT: Final[int] = 1

# Каллбэк-рендера ответа. Бывает ``message.answer`` или
# ``callback.message.answer`` (оба возвращают ``Awaitable[Message]``).
_SendText: TypeAlias = Callable[[str], Awaitable[Message]]


@router.message(Command("claim_prize"))
async def handle_claim_prize(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    get_profile: GetProfile,
    claim_prize: ClaimPrize,
    prize_lot_repository: IPrizeLotRepository,
    wallet_repository: IWalletRepository,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/claim_prize <lot_id>` — забрать зарезервированный крипто-лот."""
    presenter = ClaimPrizePresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    parsed = _parse_lot_id(command.args)
    if parsed is None:
        await message.answer(presenter.usage(locale=effective_locale))
        return
    if isinstance(parsed, _InvalidLotId):
        await message.answer(
            presenter.invalid_lot_id(locale=effective_locale, raw=parsed.raw),
        )
        return
    lot_id = parsed

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None or view.player.id is None:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return
    player_id = view.player.id

    await _process_claim(
        send_text=message.answer,
        player_id=player_id,
        lot_id=lot_id,
        presenter=presenter,
        locale=effective_locale,
        claim_prize=claim_prize,
        prize_lot_repository=prize_lot_repository,
        wallet_repository=wallet_repository,
    )


@router.callback_query(F.data.startswith("claim_prize:"))
async def handle_claim_prize_callback(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    get_profile: GetProfile,
    claim_prize: ClaimPrize,
    prize_lot_repository: IPrizeLotRepository,
    wallet_repository: IWalletRepository,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Callback `claim_prize:<lot_id>` — кнопка «Забрать приз»."""
    if tg_identity is None or callback.data is None or callback.message is None:
        return

    presenter = ClaimPrizePresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_claim_prize_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "claim_prize.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(
            presenter.toast_invalid(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        await callback.message.answer(
            presenter.invalid_callback(locale=effective_locale),
        )
        return

    # Снимаем клавиатуру: повторный клик на тот же prompt бесполезен —
    # лот либо выплачен, либо ошибка пользователя (нет кошелька / лот
    # уже забран / etc).
    await _strip_keyboard(callback)

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None or view.player.id is None:
        await callback.message.answer(
            presenter.not_registered(locale=effective_locale),
        )
        return

    await _process_claim(
        send_text=callback.message.answer,
        player_id=view.player.id,
        lot_id=parsed.lot_id,
        presenter=presenter,
        locale=effective_locale,
        claim_prize=claim_prize,
        prize_lot_repository=prize_lot_repository,
        wallet_repository=wallet_repository,
    )


async def _process_claim(  # noqa: PLR0911 — кросс-handler-овый switch с одинаковым результатом
    *,
    send_text: _SendText,
    player_id: int,
    lot_id: int,
    presenter: ClaimPrizePresenter,
    locale: Locale,
    claim_prize: ClaimPrize,
    prize_lot_repository: IPrizeLotRepository,
    wallet_repository: IWalletRepository,
) -> None:
    """Общий процесс «забрать приз»: pre-load checks + use-case + render.

    Используется и message-handler-ом `/claim_prize`, и callback-handler-ом
    `claim_prize:<lot_id>` (после собственного парсинга и проверки
    регистрации). `send_text` — async-каллбэк рендера сообщения (или
    `message.answer`, или `callback.message.answer`).
    """
    lot = await prize_lot_repository.get_by_id(lot_id=lot_id)
    if lot is None:
        await send_text(presenter.not_found(locale=locale, lot_id=lot_id))
        return
    if lot.status is PrizeLotStatus.CLAIMED:
        await send_text(presenter.already_claimed(locale=locale, lot_id=lot_id))
        return
    if lot.status is not PrizeLotStatus.RESERVED:
        await send_text(
            presenter.not_reserved(
                locale=locale,
                lot_id=lot_id,
                status=lot.status.value,
            ),
        )
        return

    wallet = await wallet_repository.get_by_player_and_currency(
        player_id=player_id,
        currency=lot.currency,
    )
    if wallet is None:
        await send_text(
            presenter.wallet_not_linked(
                locale=locale,
                currency_code=lot.currency.value,
            ),
        )
        return

    try:
        result = await claim_prize.execute(
            ClaimPrizeCommand(
                player_id=player_id,
                lot_id=lot_id,
                recipient_address=wallet.address,
            )
        )
    except PrizeLotNotFoundError:
        _LOGGER.info(
            "claim_prize: lot vanished between pre-load and execute",
            extra={"lot_id": lot_id, "player_id": player_id},
        )
        await send_text(presenter.not_found(locale=locale, lot_id=lot_id))
        return
    except PrizeLotStatusTransitionError as err:
        _LOGGER.info(
            "claim_prize: lot status changed between pre-load and execute",
            extra={
                "lot_id": lot_id,
                "player_id": player_id,
                "from_status": err.from_status.value,
            },
        )
        if err.from_status is PrizeLotStatus.CLAIMED:
            await send_text(presenter.already_claimed(locale=locale, lot_id=lot_id))
        else:
            await send_text(
                presenter.not_reserved(
                    locale=locale,
                    lot_id=lot_id,
                    status=err.from_status.value,
                ),
            )
        return
    except WalletNotLinkedError:
        _LOGGER.info(
            "claim_prize: wallet unlinked between pre-load and execute",
            extra={"lot_id": lot_id, "player_id": player_id},
        )
        await send_text(
            presenter.wallet_not_linked(
                locale=locale,
                currency_code=lot.currency.value,
            ),
        )
        return

    if result.refunded:
        await send_text(
            presenter.refund(
                locale=locale,
                lot_id=lot_id,
                currency_code=lot.currency.value,
                amount_native=lot.amount_native,
                actual_fee_native=_refund_actual_fee(result),
                fee_buffer_native=lot.fee_buffer_native.value,
            ),
        )
        return

    assert result.payout is not None  # `claimed=True` гарантирует `payout`
    await send_text(
        presenter.success(
            locale=locale,
            lot_id=lot_id,
            currency_code=lot.currency.value,
            amount_native=lot.amount_native,
            actual_fee_native=result.payout.actual_fee_native,
            tx_hash=result.payout.tx_hash,
            recipient_address=wallet.address,
        ),
    )


class _InvalidLotId:
    """Маркер «парсер видел не-пустую строку, но это не положительное число»."""

    __slots__ = ("raw",)

    def __init__(self, raw: str) -> None:
        self.raw = raw


def _parse_lot_id(raw_args: str | None) -> int | _InvalidLotId | None:
    """Распарсить аргументы `/claim_prize`.

    Возвращает:
    * ``int`` — корректный `lot_id` (положительное целое);
    * ``_InvalidLotId(raw)`` — пользователь передал что-то не похожее на
      положительное целое (для рендера `invalid_lot_id(raw)`);
    * ``None`` — аргументов вообще нет / больше одного (для рендера
      `usage`).
    """
    if raw_args is None:
        return None
    stripped = raw_args.strip()
    if not stripped:
        return None
    tokens = stripped.split()
    if len(tokens) != _ARG_COUNT:
        return None
    raw = tokens[0]
    try:
        lot_id = int(raw)
    except ValueError:
        return _InvalidLotId(raw)
    if lot_id < 1:
        return _InvalidLotId(raw)
    return lot_id


def _refund_actual_fee(result: ClaimPrizeResult) -> int:
    """Извлечь ``actual_fee_native`` из refund-ветки `ClaimPrizeResult`.

    В refund-ветке ``result.payout is None`` (по контракту use-case-а
    на D.7), но фактическая комиссия сети известна — она пришла от
    `ITonPayoutAdapter.payout(...)`. Use-case её не пробрасывает
    в `ClaimPrizeResult` (D.7), поэтому presenter получит `0`
    (placeholder); D.10.c расширит контракт, добавив
    ``ClaimPrizeResult.refund_actual_fee_native``.
    """
    # Намеренно `_ = result` — параметр зарезервирован под будущее
    # расширение `ClaimPrizeResult`.
    del result
    return 0


async def _strip_keyboard(callback: CallbackQuery) -> None:
    """Снять inline-клавиатуру у сообщения, в которое пришёл callback.

    Любые ошибки edit-а (старое сообщение, недоступный
    `InaccessibleMessage`) поглощаем — это не критично для UX.
    """
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug(
            "claim_prize.callback: failed to strip keyboard",
            exc_info=True,
        )


def build_claim_prize_keyboard(
    *,
    bundle: IMessageBundle,
    locale: Locale,
    lot_id: int,
) -> InlineKeyboardMarkup:
    """Построить inline-клавиатуру «Забрать приз» для одного CRYPTO_LOT-исхода.

    Используется roulette-handler-ом для прикрепления кнопки к
    результирующей карточке (`render_result(...)`-у). На клике
    игрок попадает в callback `claim_prize:<lot_id>`, который дёргает
    тот же flow, что и `/claim_prize`. Возвращает готовый
    `InlineKeyboardMarkup`; кнопка локализована (`claim-prize-button`).
    """
    return ClaimPrizePresenter(bundle=bundle).prompt_keyboard(
        locale=locale,
        lot_id=lot_id,
    )


def build_claim_prize_keyboard_multi(
    *,
    bundle: IMessageBundle,
    locale: Locale,
    lot_ids: list[int],
) -> InlineKeyboardMarkup:
    """Построить inline-клавиатуру для нескольких CRYPTO_LOT-исходов (PACK_10).

    Каждый ``lot_id`` — отдельная строка inline-кнопки с callback
    ``claim_prize:<lot_id>``. Для единственного лота — единственная
    кнопка (как у `build_claim_prize_keyboard`).
    """
    from aiogram.types import InlineKeyboardButton  # noqa: PLC0415

    presenter = ClaimPrizePresenter(bundle=bundle)
    label = presenter.button_text(locale=locale)
    rows = [
        [
            InlineKeyboardButton(
                text=f"{label} #{lot_id}",
                callback_data=claim_prize_callback_data(lot_id),
            ),
        ]
        for lot_id in lot_ids
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


__all__ = [
    "build_claim_prize_keyboard",
    "build_claim_prize_keyboard_multi",
    "handle_claim_prize",
    "handle_claim_prize_callback",
    "router",
]
