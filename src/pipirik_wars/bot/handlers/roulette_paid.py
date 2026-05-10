"""Handler команды `/roulette_paid` (Спринт 4.1-A, ГДД §12.5).

`/roulette_paid` (платная рулетка за Telegram Stars) в личке бота:

1. Зовёт `GetProfile` use-case — берёт текущего игрока и его уровень
   толщины. Если игрок не найден — `not_registered`.
2. Считает pre-spin gate-ы по `RoulettePaidConfig` (с учётом
   hot-reload через `IBalanceConfig`):
   - `player.thickness.level >= roulette.paid.min_thickness_level`
     (по дефолту `1`, т. е. почти никогда не блокирует);
   - **длинной gate-ы нет** — рулетка стоит ⭐, а не см.
3. На gate-фейле отвечает `RoulettePaidPresenter.requirement_thickness(...)`
   карточкой и **не** показывает кнопки покупок — это снимает риск
   создания invoice-а на заведомо проигрышной попытке.
4. На прохождении gate-ов отвечает `RoulettePaidPresenter.prompt(...)`
   + клавиатура с двумя кнопками `[Купить 1⭐]` (callback_data
   `roulette_paid:buy_single`) и `[Купить 9⭐ × 10]` (callback_data
   `roulette_paid:buy_pack_10`).

В группе/супергруппе — короткая инструкция «открой ЛС» (как у
`/upgrade`, `/forest`, `/profile`, `/roulette_free`).

Кнопки `[Купить ...]` (`roulette_paid:buy_*`):

1. Handler читает текущие цены из `IBalanceConfig.get().roulette.paid`
   (race-неуязвимость — `pre_checkout_query` всё равно проверит сумму
   на актуальность).
2. Выбирает `pack` (`SINGLE` либо `PACK_10`) по callback-action-у.
3. Сериализует `invoice_payload = "paid_roulette:single"` либо
   `"paid_roulette:pack_10"` через `invoice_payload_for(...)`.
4. Зовёт `bot.send_invoice(...)` с `currency=TG_STARS_CURRENCY` (`XTR`),
   `prices=[LabeledPrice(label, amount=cost_stars)]`,
   `payload=invoice_payload`.
5. Снимает inline-клавиатуру у pre-spin карточки (один pre-spin → одна
   попытка покупки за раз; повторное нажатие требует свежей `/roulette_paid`).

`pre_checkout_query`-handler:

1. Ack-ает `bot.answer_pre_checkout_query(query.id, ok=True)` после
   валидации `invoice_payload`-а через `parse_invoice_payload(...)` и
   валидации суммы на матчинг текущему `RoulettePaidConfig`-у.
2. На непонятный payload / неподдерживаемый currency / нематчинг суммы —
   `ok=False, error_message=...` (Telegram покажет ошибку пользователю
   и **не** проведёт платёж).

`successful_payment`-handler (Telegram-payment подтверждён):

1. Парсит `invoice_payload` → `PaidRoulettePack`.
2. Строит `idempotency_key = f"paid_roulette:{player_id}:{tg_payment_charge_id}"`
   (стабильный id платежа от Telegram гарантирует идемпотентность —
   повторный callback с тем же id не проведёт двойного списания).
3. Зовёт `SpinPaidRoulette.execute(SpinPaidRouletteCommand(...))`.
4. Маппинг исходов:
   - `idempotent=True` → `result_idempotent` карточка + toast
     `toast_already_processed`.
   - `outcomes=...` → `render_result(result)` карточка + toast
     `toast_payment_ok`.
5. Маппинг доменных ошибок:
   - `RouletteThicknessGateError` → toast + `requirement_thickness`
     карточка (handler-pre-check мог пропустить, если YAML был
     hot-reload-нут между показом prompt-а и оплатой). `payments`-row
     остаётся в БД через `IPaymentLedger.charge` — refund-flow в 4.1-D.
   - `PlayerNotFoundError` → `not_registered` (race с unregister-ом;
     платёж в БД остаётся).
   - Любая другая ошибка — toast `toast_error`, текст не правится.
"""

from __future__ import annotations

import logging
from typing import Final

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.monetization import (
    PaidRoulettePack,
    SpinPaidRoulette,
    SpinPaidRouletteCommand,
)
from pipirik_wars.application.player import GetProfile
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters import (
    TG_STARS_CURRENCY,
    RoulettePaidPresenter,
    invoice_payload_for,
    parse_invoice_payload,
    parse_roulette_paid_callback_data,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.monetization import IdempotencyKey
from pipirik_wars.domain.player import PlayerNotFoundError
from pipirik_wars.domain.roulette import RouletteThicknessGateError

router = Router(name="roulette_paid")
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


@router.message(Command("roulette_paid"))
async def handle_roulette_paid(
    message: Message,
    tg_identity: TgIdentity | None,
    get_profile: GetProfile,
    balance: IBalanceConfig,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Команда `/roulette_paid` — показать pre-spin карточку с двумя кнопками."""
    presenter = RoulettePaidPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE
    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type

    if chat_kind in ("group", "supergroup"):
        await message.answer(presenter.group(locale=effective_locale))
        return
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.other(locale=effective_locale))
        return

    paid_cfg = balance.get().roulette.paid
    if paid_cfg is None:
        # Defence-in-depth: balance.yaml::roulette.paid должен присутствовать
        # начиная с A.4. Если отсутствует — это баг конфигурации; команда
        # реагирует тем же способом, что и channel — «только в личке»
        # (вместо тихого падения), а ошибку логируем для алерта.
        _LOGGER.error(
            "roulette_paid: balance.roulette.paid is None (config missing); command unavailable",
            extra={"tg_id": tg_identity.tg_user_id},
        )
        await message.answer(presenter.other(locale=effective_locale))
        return

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return

    player = view.player

    if player.thickness.level < paid_cfg.min_thickness_level:
        await message.answer(
            presenter.requirement_thickness(
                required=paid_cfg.min_thickness_level,
                actual=player.thickness.level,
                locale=effective_locale,
            )
        )
        return

    text = presenter.prompt(
        single_cost_stars=paid_cfg.cost_stars_single,
        pack10_cost_stars=paid_cfg.cost_stars_pack10,
        pack10_spins=paid_cfg.pack10_spins,
        locale=effective_locale,
    )
    await message.answer(
        text,
        reply_markup=presenter.pack_keyboard(
            single_cost_stars=paid_cfg.cost_stars_single,
            pack10_cost_stars=paid_cfg.cost_stars_pack10,
            pack10_spins=paid_cfg.pack10_spins,
            locale=effective_locale,
        ),
    )


@router.callback_query(F.data.startswith("roulette_paid:"))
async def handle_roulette_paid_buy(
    callback: CallbackQuery,
    tg_identity: TgIdentity | None,
    bot: Bot,
    balance: IBalanceConfig,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """Обработчик инлайн-кнопок `[Купить ...]` под `/roulette_paid`.

    На клик отправляет invoice через `bot.send_invoice(...)` и снимает
    клавиатуру pre-spin карточки. Сам spin / charge выполняется
    позже — после `successful_payment`-callback-а.
    """
    if tg_identity is None or callback.data is None or callback.message is None:
        return

    presenter = RoulettePaidPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    paid_cfg = balance.get().roulette.paid
    if paid_cfg is None:
        # Race с конфиг-перезагрузкой: balance.yaml::roulette.paid пропал
        # между показом prompt-а и нажатием кнопки. На UI-уровне этого не
        # должно быть (pre-check выше), но если случилось — toast + снятие
        # клавиатуры.
        _LOGGER.error(
            "roulette_paid.callback: balance.roulette.paid is None at click time",
            extra={"tg_id": tg_identity.tg_user_id, "data": callback.data},
        )
        await callback.answer(
            presenter.toast_error(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    try:
        parsed = parse_roulette_paid_callback_data(callback.data)
    except ValueError:
        _LOGGER.warning(
            "roulette_paid.callback: invalid callback_data",
            extra={"data": callback.data, "tg_id": tg_identity.tg_user_id},
        )
        await callback.answer(
            presenter.toast_error(locale=effective_locale),
            show_alert=False,
        )
        await _strip_keyboard(callback)
        return

    if parsed.action == "buy_single":
        pack = PaidRoulettePack.SINGLE
        cost_stars = paid_cfg.cost_stars_single
    else:
        pack = PaidRoulettePack.PACK_10
        cost_stars = paid_cfg.cost_stars_pack10

    payload = invoice_payload_for(pack)

    # Снимаем клавиатуру до отправки invoice-а — один pre-spin → одна
    # попытка оплаты. Повторный клик после снятия клавиатуры невозможен.
    await _strip_keyboard(callback)

    await bot.send_invoice(
        chat_id=tg_identity.chat_id,
        title=presenter.invoice_title(pack=pack, locale=effective_locale),
        description=presenter.invoice_description(
            pack=pack,
            cost_stars=cost_stars,
            pack10_spins=paid_cfg.pack10_spins,
            locale=effective_locale,
        ),
        payload=payload,
        currency=TG_STARS_CURRENCY,
        prices=presenter.invoice_prices(
            pack=pack,
            cost_stars=cost_stars,
            pack10_spins=paid_cfg.pack10_spins,
            locale=effective_locale,
        ),
    )

    # Сам callback требует ack (иначе кнопка останется «крутиться» у
    # пользователя). Никакого тоста — invoice-карточка появится сама.
    await callback.answer()


@router.pre_checkout_query()
async def handle_pre_checkout_query(
    query: PreCheckoutQuery,
    bot: Bot,
    balance: IBalanceConfig,
) -> None:
    """`pre_checkout_query`-handler — валидация invoice-а до списания.

    Telegram присылает этот update **до** фактического списания Stars.
    Мы обязаны ответить `ok=True/False` в течение 10 секунд, иначе
    Telegram автоматически отказывает в платеже. Валидируем:

    1. `invoice_payload` парсится в `PaidRoulettePack`.
    2. `currency == "XTR"` (Telegram Stars).
    3. `total_amount` матчит текущий `cost_stars_*` из конфига.
    4. `roulette.paid`-блок присутствует.

    На любую неудачу — `ok=False` с человекочитаемым `error_message`-ом
    (на английском — Telegram сам не локализует, и большинство
    интеграций показывают эту строку как есть).
    """
    paid_cfg = balance.get().roulette.paid
    if paid_cfg is None:
        await bot.answer_pre_checkout_query(
            pre_checkout_query_id=query.id,
            ok=False,
            error_message="Paid roulette is temporarily unavailable.",
        )
        return

    if query.currency != TG_STARS_CURRENCY:
        await bot.answer_pre_checkout_query(
            pre_checkout_query_id=query.id,
            ok=False,
            error_message=f"Unsupported currency: {query.currency}.",
        )
        return

    try:
        pack = parse_invoice_payload(query.invoice_payload)
    except ValueError:
        _LOGGER.warning(
            "roulette_paid.pre_checkout: invalid invoice_payload",
            extra={
                "tg_id": query.from_user.id,
                "payload": query.invoice_payload,
            },
        )
        await bot.answer_pre_checkout_query(
            pre_checkout_query_id=query.id,
            ok=False,
            error_message="Invalid invoice payload.",
        )
        return

    expected_amount = (
        paid_cfg.cost_stars_single
        if pack is PaidRoulettePack.SINGLE
        else paid_cfg.cost_stars_pack10
    )
    if query.total_amount != expected_amount:
        _LOGGER.warning(
            "roulette_paid.pre_checkout: amount mismatch",
            extra={
                "tg_id": query.from_user.id,
                "pack": pack.value,
                "expected": expected_amount,
                "got": query.total_amount,
            },
        )
        await bot.answer_pre_checkout_query(
            pre_checkout_query_id=query.id,
            ok=False,
            error_message=("Price has changed. Please reopen /roulette_paid and try again."),
        )
        return

    await bot.answer_pre_checkout_query(pre_checkout_query_id=query.id, ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(
    message: Message,
    tg_identity: TgIdentity | None,
    get_profile: GetProfile,
    spin_paid_roulette: SpinPaidRoulette,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`successful_payment`-handler — фактический spin после подтверждения платежа.

    Telegram присылает этот update только после успешного списания
    Stars (после `pre_checkout_query` с `ok=True`). Здесь мы:

    1. Парсим `invoice_payload` → `PaidRoulettePack`.
    2. Строим `idempotency_key` из `telegram_payment_charge_id`.
    3. Зовём `SpinPaidRoulette.execute(...)`.
    4. Рендерим результат в чат игрока.

    Если этот handler ловит `successful_payment`, **не относящийся** к
    нашей рулетке (другой invoice-ный payload-формат) — мы тихо игнорим
    (фильтруем по prefix-у `paid_roulette:`). Это даёт безопасный coexist
    с другими invoice-flow в Спринтах 4.1-D / 4.1-E.
    """
    payment = message.successful_payment
    if payment is None or tg_identity is None:
        return

    presenter = RoulettePaidPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    try:
        pack = parse_invoice_payload(payment.invoice_payload)
    except ValueError:
        # `successful_payment` от другой invoice-flow — не наш payload.
        # Не трогаем платёж и не пишем в чат.
        return

    view = await get_profile.execute(tg_id=tg_identity.tg_user_id)
    if view is None:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return
    assert view.player.id is not None

    idempotency_key = IdempotencyKey(
        f"paid_roulette:{view.player.id}:{payment.telegram_payment_charge_id}",
    )

    try:
        result = await spin_paid_roulette.execute(
            SpinPaidRouletteCommand(
                player_id=view.player.id,
                pack=pack,
                idempotency_key=idempotency_key,
                provider_payment_id=payment.telegram_payment_charge_id,
            ),
        )
    except RouletteThicknessGateError as exc:
        await message.answer(
            presenter.requirement_thickness(
                required=exc.required_level,
                actual=exc.thickness_level,
                locale=effective_locale,
            ),
        )
        return
    except PlayerNotFoundError:
        await message.answer(presenter.not_registered(locale=effective_locale))
        return
    except Exception:
        _LOGGER.exception(
            "roulette_paid.successful_payment: unexpected error",
            extra={
                "tg_id": tg_identity.tg_user_id,
                "tg_payment_charge_id": payment.telegram_payment_charge_id,
            },
        )
        await message.answer(presenter.toast_error(locale=effective_locale))
        return

    await message.answer(
        presenter.render_result(result=result, locale=effective_locale),
    )


async def _strip_keyboard(callback: CallbackQuery) -> None:
    """Снять inline-клавиатуру у сообщения, к которому привязан callback.

    Любые ошибки edit-а (старое сообщение, недоступное `InaccessibleMessage`)
    поглощаем — это не критично для UX.
    """
    msg = callback.message
    if msg is None:
        return
    try:
        await msg.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except Exception:
        _LOGGER.debug(
            "roulette_paid.callback: failed to strip keyboard",
            extra={"chat_id": msg.chat.id if hasattr(msg, "chat") else None},
        )
