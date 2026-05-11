"""`/claim_prize <lot_id>` handler (Спринт 4.1-D, шаг D.7.b).

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
6. Doменные ошибки от use-case-а (`PrizeLotNotFoundError`,
   `PrizeLotStatusTransitionError`, `WalletNotLinkedError`) могут
   прилететь из-за race-condition между pre-load и use-case-execute —
   обрабатываем теми же ветками, что и пред-проверки.

Локали ключей `claim-prize-*` лежат в `locales/{ru,en}.ftl`.
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.monetization.claim_prize import (
    ClaimPrize,
    ClaimPrizeCommand,
)
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.claim_prize import ClaimPrizePresenter
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


@router.message(Command("claim_prize"))
async def handle_claim_prize(  # noqa: PLR0911, PLR0912 — каждая ветка возврата = отдельная пользовательская ошибка, плоский switch уместен
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

    lot = await prize_lot_repository.get_by_id(lot_id=lot_id)
    if lot is None:
        await message.answer(
            presenter.not_found(locale=effective_locale, lot_id=lot_id),
        )
        return
    if lot.status is PrizeLotStatus.CLAIMED:
        await message.answer(
            presenter.already_claimed(locale=effective_locale, lot_id=lot_id),
        )
        return
    if lot.status is not PrizeLotStatus.RESERVED:
        await message.answer(
            presenter.not_reserved(
                locale=effective_locale,
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
        await message.answer(
            presenter.wallet_not_linked(
                locale=effective_locale,
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
        # Race-condition между pre-load и use-case (лот удалили
        # параллельно). Рендерим ту же ветку, что и pre-check.
        _LOGGER.info(
            "claim_prize: lot vanished between pre-load and execute",
            extra={"lot_id": lot_id, "player_id": player_id},
        )
        await message.answer(
            presenter.not_found(locale=effective_locale, lot_id=lot_id),
        )
        return
    except PrizeLotStatusTransitionError as err:
        # Race-condition: лот сменил статус между pre-load и use-case
        # (другой агент зарефандил или мы повторно дёргаем).
        _LOGGER.info(
            "claim_prize: lot status changed between pre-load and execute",
            extra={
                "lot_id": lot_id,
                "player_id": player_id,
                "from_status": err.from_status.value,
            },
        )
        if err.from_status is PrizeLotStatus.CLAIMED:
            await message.answer(
                presenter.already_claimed(locale=effective_locale, lot_id=lot_id),
            )
        else:
            await message.answer(
                presenter.not_reserved(
                    locale=effective_locale,
                    lot_id=lot_id,
                    status=err.from_status.value,
                ),
            )
        return
    except WalletNotLinkedError:
        # Race-condition: кошелёк отвязали между pre-load и use-case.
        _LOGGER.info(
            "claim_prize: wallet unlinked between pre-load and execute",
            extra={"lot_id": lot_id, "player_id": player_id},
        )
        await message.answer(
            presenter.wallet_not_linked(
                locale=effective_locale,
                currency_code=lot.currency.value,
            ),
        )
        return

    if result.refunded:
        await message.answer(
            presenter.refund(
                locale=effective_locale,
                lot_id=lot_id,
                currency_code=lot.currency.value,
                amount_native=lot.amount_native,
                actual_fee_native=_actual_fee(result),
                fee_buffer_native=lot.fee_buffer_native.value,
            ),
        )
        return

    assert result.payout is not None  # `claimed=True` гарантирует `payout`
    await message.answer(
        presenter.success(
            locale=effective_locale,
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


def _actual_fee(result: object) -> int:
    """Извлечь ``actual_fee_native`` из refund-ветки `ClaimPrizeResult`.

    В refund-ветке ``result.payout is None`` (по контракту use-case-а),
    но фактическая комиссия сети известна — она пришла от
    `ITonPayoutAdapter.payout(...)`. Сейчас use-case её не пробрасывает
    в `ClaimPrizeResult.refund`, поэтому presenter получит `0`
    (placeholder); D.10.c расширит контракт, добавив
    ``ClaimPrizeResult.refund_actual_fee_native``.
    """
    # Намеренно `_ = result` — параметр зарезервирован под будущее
    # расширение `ClaimPrizeResult`.
    del result
    return 0


__all__ = [
    "handle_claim_prize",
    "router",
]
