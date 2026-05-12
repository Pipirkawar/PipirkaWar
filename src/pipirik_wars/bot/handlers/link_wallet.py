"""`/link_wallet` + `/link_wallet_confirm` handlers (Спринт 4.1-D, шаг D.6).

`/link_wallet` (личка-only) — пользовательская точка входа: показывает
выбор валюты (TON / USDT) с инлайн-кнопками. Клик на кнопку через
callback `link_wallet:select:<ton|usdt>` рисует инструкции по подписи
кошелька через TON-Connect-совместимый клиент.

`/link_wallet_confirm <currency> <address> <proof>` — серверная точка
входа: вызывает `LinkWallet.execute(...)`. На D.6 это «ручной» вход
для теста и интеграционной проверки use-case-а; на D.10 эту команду
будет дергать TON-Connect-bridge, переводя ``tonconnect_proof`` от
кошелька в `LinkWalletCommand`.

Все ошибки доменных и application-слоёв ловит `ErrorHandlerMiddleware`
кроме явно ожидаемых:

* ``ValueError`` — невалидная подпись TON-Connect / неподдерживаемая
  валюта на VO-уровне. Handler рендерит локализованную ошибку и
  выходит — это пользовательская проблема, не runtime-bug.
* `WalletAlreadyLinkedError` — игрок просит привязать уже привязанный
  адрес. Handler рендерит «уже привязан» — не runtime-bug, а
  ожидаемая ветка UX.

Локали ключей `link-wallet-*` лежат в `locales/{ru,en}.ftl`.
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Message

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.monetization.link_wallet import (
    LinkWallet,
    LinkWalletCommand,
)
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.link_wallet import (
    LinkWalletPresenter,
    parse_link_wallet_callback_data,
)
from pipirik_wars.domain.monetization.errors import (
    TonProofReplayedError,
    WalletAlreadyLinkedError,
)
from pipirik_wars.domain.monetization.value_objects import Currency

router = Router(name="link_wallet")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

# Маппинг user-facing «коротких» CLI-ключей валюты на доменный enum.
# Совпадает с `LinkWalletCurrencyKey` в презентере, продублирован тут
# намеренно: handler не зависит от структуры callback_data.
_CURRENCY_BY_CLI: Final[dict[str, Currency]] = {
    "ton": Currency.TON_NANO,
    "usdt": Currency.USDT_DECIMAL,
}
_CONFIRM_ARG_COUNT: Final[int] = 3


@router.message(Command("link_wallet"))
async def handle_link_wallet(
    message: Message,
    tg_identity: TgIdentity | None,
    get_profile: GetProfile,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/link_wallet` — показать prompt выбора валюты для привязки кошелька."""
    presenter = LinkWalletPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return

    await message.answer(
        presenter.prompt(locale=effective_locale),
        reply_markup=presenter.prompt_keyboard(locale=effective_locale),
    )


@router.callback_query(F.data.startswith("link_wallet:"))
async def handle_link_wallet_select(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Обработчик инлайн-кнопок выбора валюты под `/link_wallet`.

    После клика снимает клавиатуру (один prompt → один выбор) и
    отправляет локализованные инструкции по подписи кошелька через
    TON-Connect-совместимый клиент.
    """
    if tg_identity is None or callback.data is None or callback.message is None:
        return

    presenter = LinkWalletPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        parsed = parse_link_wallet_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "link_wallet.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(
            presenter.toast_invalid(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    # Снимаем клавиатуру до отправки инструкций — повторные клики на тот
    # же prompt бесполезны.
    await _strip_keyboard(callback)
    await callback.message.answer(
        presenter.instructions(
            currency_key=parsed.currency_key,
            locale=effective_locale,
        ),
    )


@router.message(Command("link_wallet_confirm"))
async def handle_link_wallet_confirm(  # noqa: PLR0911 — каждая ветка возврата = отдельная пользовательская ошибка, плоский switch уместен
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    get_profile: GetProfile,
    link_wallet: LinkWallet,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/link_wallet_confirm <currency> <address> <proof>` — backend-вход.

    Принимает три аргумента: ``ton`` или ``usdt``, TON-адрес кошелька,
    TON-Connect-proof (произвольная не-пустая строка; реальный
    верификатор отыграет её Ed25519-подписью). Дергает
    `LinkWallet.execute(...)` и рисует ответ в локали игрока.

    Возможные ответы:

    * ``usage`` — нет/неверное число аргументов.
    * ``unsupported`` — валюта не в `{ton, usdt}`.
    * ``invalid_proof`` — TON-Connect-верификация вернула `False`.
    * ``already_linked`` — адрес уже привязан (idempotency-ветка).
    * ``linked`` / ``relinked`` — успех (первая привязка / замена).
    """
    presenter = LinkWalletPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.confirm_group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.confirm_other(locale=effective_locale))
        return

    parsed_args = _parse_confirm_args(command.args)
    if parsed_args is None:
        await message.answer(presenter.confirm_usage(locale=effective_locale))
        return
    currency_raw, address, proof = parsed_args

    if currency_raw not in _CURRENCY_BY_CLI:
        await message.answer(
            presenter.confirm_unsupported_currency(
                locale=effective_locale,
                code=currency_raw,
            ),
        )
        return
    currency = _CURRENCY_BY_CLI[currency_raw]

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None or view.player.id is None:
        await message.answer(presenter.confirm_not_registered(locale=effective_locale))
        return

    try:
        result = await link_wallet.execute(
            LinkWalletCommand(
                player_id=view.player.id,
                address=address,
                currency=currency,
                proof=proof,
                # Спринт 4.1-F (шаг F.4.b): scope/nonce пробрасываются в
                # use-case для anti-replay через `INonceStore.consume_nonce`.
                # В этом sandbox-handler-е (D.6) `scope`+`nonce` ещё не
                # парсятся из proof-payload-а (это F.5.a + F.8.b);
                # передаём sentinel — use-case бросит
                # `TonProofReplayedError` (consume вернёт `False`), которая
                # рендерится как «invalid proof» (бытым-CLI-debug-flow).
                scope=f"link_wallet:{view.player.id}:{currency.value}",
                nonce=proof,
            )
        )
    except WalletAlreadyLinkedError:
        await message.answer(
            presenter.confirm_already_linked(
                locale=effective_locale,
                address=address,
                currency_code=currency.value,
            ),
        )
        return
    except ValueError:
        # `LinkWallet.execute` бросает `ValueError` при провале
        # TON-Connect-верификации. Это не runtime-bug — это
        # пользовательская ошибка (битый proof / подделка).
        _LOGGER.info(
            "link_wallet.confirm: TON Connect proof verification failed",
            extra={"tg_id": tg_identity.tg_user_id, "currency": currency.value},
        )
        await message.answer(presenter.confirm_invalid_proof(locale=effective_locale))
        return
    except TonProofReplayedError:
        # Спринт 4.1-F (шаг F.4.b): consume_nonce вернул False (replay,
        # expired, или nonce никогда не выдавался). Рендерим как
        # `invalid_proof` — в F.8.c добавится отдельная локаль.
        _LOGGER.info(
            "link_wallet.confirm: TON Connect nonce already consumed",
            extra={"tg_id": tg_identity.tg_user_id, "currency": currency.value},
        )
        await message.answer(presenter.confirm_invalid_proof(locale=effective_locale))
        return

    if result.replaced:
        await message.answer(
            presenter.confirm_relinked(
                locale=effective_locale,
                address=result.wallet.address,
                currency_code=currency.value,
            ),
        )
    else:
        await message.answer(
            presenter.confirm_linked(
                locale=effective_locale,
                address=result.wallet.address,
                currency_code=currency.value,
            ),
        )


def _parse_confirm_args(raw_args: str | None) -> tuple[str, str, str] | None:
    """Распарсить аргументы `/link_wallet_confirm`.

    Возвращает кортеж ``(currency, address, proof)``, либо ``None``
    если число аргументов не равно трём.
    """
    if raw_args is None:
        return None
    stripped = raw_args.strip()
    if not stripped:
        return None
    tokens = stripped.split()
    if len(tokens) != _CONFIRM_ARG_COUNT:
        return None
    currency_raw, address, proof = tokens
    return currency_raw.lower(), address, proof


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
            "link_wallet.callback: failed to strip keyboard",
            exc_info=True,
        )


__all__ = [
    "handle_link_wallet",
    "handle_link_wallet_confirm",
    "handle_link_wallet_select",
    "router",
]
