"""Handler `/refund_lot <lot_id> <reason>` (Спринт 4.1-E, E.13, ГДД §12.6.6).

`/refund_lot` — двухфазная admin-команда «принудительно вернуть лот в
крипто-пул» (super-admin + TOTP). Применяется, когда лот «завис» в
``RESERVED``-статусе из-за бага инфраструктуры (TON-RPC лежит, expire-cron
сломан) или когда нужно «откатить» некорректно сгенерированный
``ACTIVE``-лот (после правки баланса).

Логика двух фаз:

* **Фаза 1** (этот handler — `handle_refund_lot`): парсит `lot_id` и
  `reason`, вызывает `RequestAdminConfirm` с
  ``command_kind="refund_lot"`` и payload-ом ``{lot_id, reason}``,
  возвращает админу `confirm_issued`-сообщение с одноразовым токеном.
  `RequestAdminConfirm` сам проверяет, что админ активен и у него
  настроен TOTP (см. `AuthorizationError` / `TotpNotConfiguredError`).
* **Фаза 2** (общий handler `/confirm` в `admin_support.py` → dispatcher
  `dispatch_refund_lot` в этом же модуле, придёт в E.13.c): после
  верификации TOTP-кода в `VerifyAdminConfirm` диспетчер вызывает
  `RefundLot.execute(...)` — атомарный refund-flow с двойным audit-ом
  (player-side `PRIZE_LOT_REFUNDED` + admin-side `ADMIN_REFUND_LOT`).

Команда работает только в ЛС бота — `lot_id` и `reason` не должны
попадать в групповой чат (даже если все участники — админы).
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from pipirik_wars.application.admin import (
    RequestAdminConfirm,
    RequestAdminConfirmInput,
    VerifyAdminConfirmOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.monetization import RefundLotInput
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.handlers.admin_economy import (
    CONFIRM_DISPATCHERS,
    ConfirmDispatchDeps,
    ConfirmPayloadInvalidPresenter,
)
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_refund_lot import RefundLotPresenter
from pipirik_wars.domain.admin import TotpNotConfiguredError
from pipirik_wars.domain.monetization import (
    PrizeLotNotFoundError,
    PrizeLotStatusTransitionError,
)

router = Router(name="admin_refund_lot")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

REPLY_NON_PRIVATE_RU = "🍆 Админ-команды доступны только в ЛС бота."

#: ``command_kind``-маркер, под которым `RequestAdminConfirm` сохраняет
#: payload в `IAdminConfirmStore`, а `dispatch_refund_lot` (E.13.c)
#: регистрируется в `CONFIRM_DISPATCHERS`. Должен быть стабильным —
#: токены, выданные старой версией handler-а, не должны «потеряться»
#: после деплоя новой.
COMMAND_KIND_REFUND_LOT = "refund_lot"

#: Параметры payload-а, ожидаемые `dispatch_refund_lot` (E.13.c).
#: Зафиксированы здесь, чтобы handler и dispatcher оставались в
#: синхронизации. Меняй обе стороны вместе.
_PAYLOAD_KEY_LOT_ID = "lot_id"
_PAYLOAD_KEY_REASON = "reason"


@router.message(Command("refund_lot"))
async def handle_refund_lot(  # noqa: PLR0911 — каждый return = отдельный UX-отказ
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    request_admin_confirm: RequestAdminConfirm,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/refund_lot <lot_id> <reason>` — выдать `/confirm`-токен (фаза 1)."""
    presenter = RefundLotPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(presenter.usage(locale=effective_locale))
        return

    parts = raw.split(maxsplit=1)
    if len(parts) < 2:
        # Без reason-аргумента команда не имеет смысла — see ГДД §12.6.6
        # «причина refund-а попадает в admin-аудит, без неё не пускаем».
        await message.answer(presenter.usage(locale=effective_locale))
        return

    try:
        lot_id = int(parts[0])
    except ValueError:
        await message.answer(presenter.bad_lot_id(locale=effective_locale, value=parts[0]))
        return
    if lot_id <= 0:
        await message.answer(presenter.bad_lot_id(locale=effective_locale, value=parts[0]))
        return

    reason = parts[1].strip()
    if not reason:
        await message.answer(presenter.no_reason(locale=effective_locale))
        return

    try:
        result = await request_admin_confirm.execute(
            RequestAdminConfirmInput(
                actor_tg_id=tg_identity.tg_user_id,
                command_kind=COMMAND_KIND_REFUND_LOT,
                target_kind="prize_lot",
                target_id=str(lot_id),
                payload={
                    _PAYLOAD_KEY_LOT_ID: lot_id,
                    _PAYLOAD_KEY_REASON: reason,
                },
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return
    except TotpNotConfiguredError:
        await message.answer(presenter.totp_not_configured(locale=effective_locale))
        return

    await message.answer(
        presenter.confirm_issued(
            locale=effective_locale,
            token=result.token,
            ttl_seconds=result.ttl_seconds,
        ),
    )


# ── Фаза 2: dispatch_refund_lot (вызывается из /confirm) ─────────────────


async def dispatch_refund_lot(
    result: VerifyAdminConfirmOutput,
    message: Message,
    identity: TgIdentity,
    locale: Locale,
    bundle: IMessageBundle,
    deps: ConfirmDispatchDeps,
) -> None:
    """Фаза 2 `/refund_lot` — вызывает `RefundLot.execute(...)` после TOTP.

    Диспетчеризуется из `admin_support.handle_confirm` по
    `result.command_kind == COMMAND_KIND_REFUND_LOT`. Payload из фазы 1
    — ``{lot_id: int, reason: str}`` (см. `_PAYLOAD_KEY_*` выше).

    Обработка веток:

    * `AuthorizationError` — админа деактивировали между фазами 1 и 2,
      это редкий race-condition (в отличие от фазы 1, где эта ветвь
      бывает при вызове из не-админ-а).
    * `PrizeLotNotFoundError` — админ передал несуществующий lot_id.
    * `PrizeLotStatusTransitionError` — лот в terminal-статусе `CLAIMED`,
      возврат через `/refund_lot` запрещён доменом (ГДД §12.6.6).
    * `out.was_already_refunded=True` — идемпотентный retry после
      успешного рефанда (напр. админ повторил /confirm с новым
      токеном по тому же lot_id) — отвечаем `already_refunded`.
    """
    presenter = RefundLotPresenter(bundle=bundle)

    lot_id_raw = result.payload.get(_PAYLOAD_KEY_LOT_ID)
    reason_raw = result.payload.get(_PAYLOAD_KEY_REASON)
    if not isinstance(lot_id_raw, int) or not isinstance(reason_raw, str):
        # Payload собирается фазой 1 — валидным он быть обязан.
        # Если нет — в TOTP-store-е что-то сломалось; возвращаем
        # общий «invalid command_kind»-ответ, не светим детали payload-а.
        await message.answer(
            ConfirmPayloadInvalidPresenter(bundle=bundle).message(
                locale=locale,
                command_kind=result.command_kind,
            ),
        )
        return

    try:
        out = await deps.refund_lot.execute(
            RefundLotInput(
                actor_tg_id=identity.tg_user_id,
                lot_id=lot_id_raw,
                reason=reason_raw,
                tg_chat_id=identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=locale))
        return
    except PrizeLotNotFoundError:
        await message.answer(presenter.not_found(locale=locale, lot_id=lot_id_raw))
        return
    except PrizeLotStatusTransitionError as e:
        await message.answer(
            presenter.bad_transition(
                locale=locale,
                lot_id=lot_id_raw,
                current_status=e.from_status.value,
            ),
        )
        return

    if out.was_already_refunded:
        await message.answer(
            presenter.already_refunded(
                locale=locale,
                lot_id=out.lot_id,
                pool_after_native=out.pool_after_native,
            ),
        )
        return

    await message.answer(
        presenter.success(
            locale=locale,
            lot_id=out.lot_id,
            currency=out.currency,
            amount_native=out.amount_native,
            pool_after_native=out.pool_after_native,
        ),
    )


# Регистрация в общем registry-диспетчере `/confirm`-handler-а. Импорт
# `CONFIRM_DISPATCHERS` сразу мутирует словарь — модуль должен быть
# подтянут в `bot/handlers/__init__.py` до `register_routers`-вызова,
# что и происходит при `include_router(admin_refund_lot_router)` —
# это будет сделано в E.13.d. Аналогично dispatch_announce.
CONFIRM_DISPATCHERS[COMMAND_KIND_REFUND_LOT] = dispatch_refund_lot


__all__ = [
    "COMMAND_KIND_REFUND_LOT",
    "REPLY_NON_PRIVATE_RU",
    "dispatch_refund_lot",
    "handle_refund_lot",
    "router",
]
