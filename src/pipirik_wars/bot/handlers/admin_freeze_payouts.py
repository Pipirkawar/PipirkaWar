"""Handlers `/freeze_payouts <reason>` и `/unfreeze_payouts` (Спринт 4.1-E, E.14, ГДД §12.6.6).

`/freeze_payouts` и `/unfreeze_payouts` — двухфазные admin-команды
«(раз)заморозить криптовалютные выплаты глобально» (super-admin + TOTP).
Применяются как kill-switch при подозрении на эксплойт TON/USDT-выплат
или при инциденте в инфраструктуре (TON Center лежит, jetton-провайдер
вернул мусор, баланс хост-кошелька утёк и т.п.).

Логика двух фаз (зеркалит `/refund_lot` из E.13):

* **Фаза 1** (этот модуль — `handle_freeze_payouts` /
  `handle_unfreeze_payouts`): парсит аргументы (`reason` для freeze,
  без аргументов для unfreeze), вызывает `RequestAdminConfirm` с
  ``command_kind="freeze_payouts"`` / ``"unfreeze_payouts"`` и
  payload-ом (`{reason}` для freeze, пустой для unfreeze), возвращает
  админу `confirm_issued`-сообщение с одноразовым токеном.
  `RequestAdminConfirm` сам проверяет, что админ активен и у него
  настроен TOTP (см. `AuthorizationError` / `TotpNotConfiguredError`).
* **Фаза 2** (общий handler `/confirm` в `admin_support.py` →
  dispatcher-ы `dispatch_freeze_payouts` / `dispatch_unfreeze_payouts`,
  придут в E.14.c): после верификации TOTP-кода в
  `VerifyAdminConfirm` диспетчер вызывает
  `FreezePayouts.execute(...)` / `UnfreezePayouts.execute(...)` —
  атомарную (раз)заморозку singleton-`payout_freeze` с admin-аудитом.

Команды работают только в ЛС бота — `reason` админа не должен
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
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_freeze_payouts import (
    FreezePayoutsPresenter,
    UnfreezePayoutsPresenter,
)
from pipirik_wars.domain.admin import TotpNotConfiguredError

router = Router(name="admin_freeze_payouts")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

REPLY_NON_PRIVATE_RU = "🍆 Админ-команды доступны только в ЛС бота."

#: ``command_kind``-маркеры, под которыми `RequestAdminConfirm` сохраняет
#: payload в `IAdminConfirmStore`, а `dispatch_(un)freeze_payouts`
#: (E.14.c) регистрируются в `CONFIRM_DISPATCHERS`. Стабильные строки —
#: токены, выданные старой версией handler-а, не должны «потеряться»
#: после деплоя новой.
COMMAND_KIND_FREEZE_PAYOUTS = "freeze_payouts"
COMMAND_KIND_UNFREEZE_PAYOUTS = "unfreeze_payouts"

#: Параметры payload-а, ожидаемые `dispatch_freeze_payouts` (E.14.c).
#: Зафиксированы здесь, чтобы handler и dispatcher оставались в
#: синхронизации. Меняй обе стороны вместе.
_PAYLOAD_KEY_REASON = "reason"

#: `target_kind` / `target_id` для `RequestAdminConfirm`-входа: freeze —
#: глобальный singleton, целевого объекта нет. Совпадает с
#: `_PAYOUT_FREEZE_TARGET_*` из `application/monetization/freeze_payouts.py`.
_TARGET_KIND = "payout_freeze"
_TARGET_ID = "all"


@router.message(Command("freeze_payouts"))
async def handle_freeze_payouts(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    request_admin_confirm: RequestAdminConfirm,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/freeze_payouts <reason>` — выдать `/confirm`-токен (фаза 1)."""
    presenter = FreezePayoutsPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    raw = (command.args or "").strip()
    if not raw:
        # Без reason-аргумента команда не имеет смысла — see ГДД §12.6.6
        # «причина freeze-а попадает в admin-аудит, без неё не пускаем».
        await message.answer(presenter.no_reason(locale=effective_locale))
        return

    try:
        result = await request_admin_confirm.execute(
            RequestAdminConfirmInput(
                actor_tg_id=tg_identity.tg_user_id,
                command_kind=COMMAND_KIND_FREEZE_PAYOUTS,
                target_kind=_TARGET_KIND,
                target_id=_TARGET_ID,
                payload={
                    _PAYLOAD_KEY_REASON: raw,
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


@router.message(Command("unfreeze_payouts"))
async def handle_unfreeze_payouts(
    message: Message,
    tg_identity: TgIdentity | None,
    request_admin_confirm: RequestAdminConfirm,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/unfreeze_payouts` — выдать `/confirm`-токен (фаза 1).

    Аргументов нет: причина «снятия» не существенна для audit-trail-а
    (event `ADMIN_UNFREEZE_PAYOUTS` сам по себе фиксирует факт снятия;
    инициатор и время известны). Если в будущем понадобится reason —
    добавим как опциональный аргумент.
    """
    presenter = UnfreezePayoutsPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    try:
        result = await request_admin_confirm.execute(
            RequestAdminConfirmInput(
                actor_tg_id=tg_identity.tg_user_id,
                command_kind=COMMAND_KIND_UNFREEZE_PAYOUTS,
                target_kind=_TARGET_KIND,
                target_id=_TARGET_ID,
                payload={},
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


__all__ = [
    "COMMAND_KIND_FREEZE_PAYOUTS",
    "COMMAND_KIND_UNFREEZE_PAYOUTS",
    "REPLY_NON_PRIVATE_RU",
    "handle_freeze_payouts",
    "handle_unfreeze_payouts",
    "router",
]
