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
    VerifyAdminConfirmOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.monetization import (
    FreezePayoutsInput,
    UnfreezePayoutsInput,
)
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.handlers.admin_economy import (
    CONFIRM_DISPATCHERS,
    ConfirmDispatchDeps,
    ConfirmPayloadInvalidPresenter,
)
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


# ── Фаза 2: dispatch_freeze_payouts / dispatch_unfreeze_payouts (вызываются из /confirm) ─


async def dispatch_freeze_payouts(
    result: VerifyAdminConfirmOutput,
    message: Message,
    identity: TgIdentity,
    locale: Locale,
    bundle: IMessageBundle,
    deps: ConfirmDispatchDeps,
) -> None:
    """Фаза 2 `/freeze_payouts` — вызывает `FreezePayouts.execute(...)` после TOTP.

    Диспетчеризуется из `admin_support.handle_confirm` по
    `result.command_kind == COMMAND_KIND_FREEZE_PAYOUTS`. Payload из фазы 1
    — ``{reason: str}`` (см. `_PAYLOAD_KEY_REASON` выше).

    Обработка веток:

    * `AuthorizationError` — админа деактивировали между фазами 1 и 2 (race);
    * `out.was_already_frozen=True` — идемпотентный retry (тот же
      админ и та же причина) → `already_frozen`;
    * успех → `success(reason)`.
    """
    presenter = FreezePayoutsPresenter(bundle=bundle)

    reason_raw = result.payload.get(_PAYLOAD_KEY_REASON)
    if not isinstance(reason_raw, str):
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
        out = await deps.freeze_payouts.execute(
            FreezePayoutsInput(
                actor_tg_id=identity.tg_user_id,
                reason=reason_raw,
                tg_chat_id=identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=locale))
        return

    if out.was_already_frozen:
        await message.answer(
            presenter.already_frozen(locale=locale, reason=reason_raw),
        )
        return

    await message.answer(
        presenter.success(locale=locale, reason=reason_raw),
    )


async def dispatch_unfreeze_payouts(
    result: VerifyAdminConfirmOutput,
    message: Message,
    identity: TgIdentity,
    locale: Locale,
    bundle: IMessageBundle,
    deps: ConfirmDispatchDeps,
) -> None:
    """Фаза 2 `/unfreeze_payouts` — вызывает `UnfreezePayouts.execute(...)` после TOTP.

    Диспетчеризуется из `admin_support.handle_confirm` по
    `result.command_kind == COMMAND_KIND_UNFREEZE_PAYOUTS`. Payload из фазы 1
    — пустой (параметров у команды нет; reason в admin-аудит пишет
    сам use-case дефолтом).

    Обработка веток:

    * `AuthorizationError` — админа деактивировали между фазами 1 и 2 (race);
    * `out.was_already_unfrozen=True` — идемпотентный retry (выплаты
      и так были разрешены) → `already_unfrozen`;
    * успех → `success`.
    """
    presenter = UnfreezePayoutsPresenter(bundle=bundle)

    try:
        out = await deps.unfreeze_payouts.execute(
            UnfreezePayoutsInput(
                actor_tg_id=identity.tg_user_id,
                reason=None,
                tg_chat_id=identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=locale))
        return

    if out.was_already_unfrozen:
        await message.answer(presenter.already_unfrozen(locale=locale))
        return

    await message.answer(presenter.success(locale=locale))


# Регистрация в общем registry-диспетчере `/confirm`-handler-а. Импорт
# `CONFIRM_DISPATCHERS` сразу мутирует словарь — модуль должен быть
# подтянут в `bot/handlers/__init__.py` до `register_routers`-вызова,
# что и происходит при `include_router(admin_freeze_payouts_router)`
# — это будет сделано в E.14.d (аналогично admin_refund_lot).
CONFIRM_DISPATCHERS[COMMAND_KIND_FREEZE_PAYOUTS] = dispatch_freeze_payouts
CONFIRM_DISPATCHERS[COMMAND_KIND_UNFREEZE_PAYOUTS] = dispatch_unfreeze_payouts


__all__ = [
    "COMMAND_KIND_FREEZE_PAYOUTS",
    "COMMAND_KIND_UNFREEZE_PAYOUTS",
    "REPLY_NON_PRIVATE_RU",
    "dispatch_freeze_payouts",
    "dispatch_unfreeze_payouts",
    "handle_freeze_payouts",
    "handle_unfreeze_payouts",
    "router",
]
