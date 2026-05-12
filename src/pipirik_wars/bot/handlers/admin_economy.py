"""Handler-ы команд экономики админ-интерфейса (Спринт 2.5-C, ГДД §16/§18.6.4).

В этом модуле живут:

- `/grant_length <tg_id> <delta_cm> <reason>` — TOTP-обязательная.
- `/grant_thickness <tg_id> <new_level> <reason>` — TOTP-обязательная.
- `/balance_get <key>` — read-only, без TOTP.
- `/balance_set <key> <value> <reason>` — TOTP-обязательная.

Все TOTP-команды идут двухфазно: handler первой фазы вызывает
`RequestAdminConfirm` (выдаёт `<token>`), вторая фаза — общий
`/confirm`-handler (`bot/handlers/admin_support.py`), который через
**registry-dispatcher** (`CONFIRM_DISPATCHERS`) роутит на одну из
`dispatch_*`-функций ниже. Каждая dispatch-функция строит
`idempotency_key` (см. `_idempotency.py`) и вызывает свой use-case.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from pipirik_wars.application.admin import (
    BalanceKeyError,
    BanPlayer,
    BanPlayerInput,
    GetBalanceValue,
    GetBalanceValueInput,
    GrantLength,
    GrantLengthBlockedError,
    GrantLengthInput,
    GrantThickness,
    GrantThicknessBlockedError,
    GrantThicknessInput,
    IBroadcastTaskSpawner,
    RequestAdminConfirm,
    RequestAdminConfirmInput,
    RunBroadcastAnnouncement,
    SetBalanceValue,
    SetBalanceValueInput,
    ThicknessLevelInvalidError,
    VerifyAdminConfirmOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale, MessageKey
from pipirik_wars.application.monetization import FreezePayouts, RefundLot, UnfreezePayouts
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.handlers._idempotency import build_admin_idempotency_key
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_economy import (
    GetBalanceValuePresenter,
    GrantLengthPresenter,
    GrantThicknessPresenter,
    IdempotencyReplayPresenter,
    SetBalanceValuePresenter,
)
from pipirik_wars.bot.presenters.admin_support import (
    BanPlayerPresenter,
    ConfirmPresenter,
)
from pipirik_wars.domain.admin import TotpNotConfiguredError
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.errors import (
    AnticheatSoftBanError,
    LengthDeltaInvalidError,
)
from pipirik_wars.domain.shared.ports import IClock
from pipirik_wars.shared.errors import ConfigError

router = Router(name="admin_economy")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

REPLY_NON_PRIVATE_RU = "🍆 Админ-команды доступны только в ЛС бота."

COMMAND_KIND_BAN = "ban"
COMMAND_KIND_GRANT_LENGTH = "grant_length"
COMMAND_KIND_GRANT_THICKNESS = "grant_thickness"
COMMAND_KIND_BALANCE_SET = "balance_set"


# ── /grant_length (фаза 1) ──────────────────────────────────────────────────


@router.message(Command("grant_length"))
async def handle_grant_length(  # noqa: PLR0911 — каждый return = отдельный UX-отказ
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    request_admin_confirm: RequestAdminConfirm,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/grant_length <tg_id> <±delta_cm> <reason>` — выдать `/confirm`-токен."""
    presenter = GrantLengthPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(presenter.usage(locale=effective_locale))
        return

    parts = raw.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(presenter.usage(locale=effective_locale))
        return

    try:
        target_tg_id = int(parts[0])
    except ValueError:
        await message.answer(presenter.bad_id(locale=effective_locale, value=parts[0]))
        return

    try:
        delta_cm = int(parts[1])
    except ValueError:
        await message.answer(presenter.bad_delta(locale=effective_locale, value=parts[1]))
        return
    if delta_cm == 0:
        await message.answer(presenter.bad_delta(locale=effective_locale, value=parts[1]))
        return

    reason = parts[2].strip() if len(parts) == 3 else ""
    if not reason:
        await message.answer(presenter.no_reason(locale=effective_locale))
        return

    try:
        result = await request_admin_confirm.execute(
            RequestAdminConfirmInput(
                actor_tg_id=tg_identity.tg_user_id,
                command_kind=COMMAND_KIND_GRANT_LENGTH,
                target_kind="player",
                target_id=str(target_tg_id),
                payload={
                    "target_tg_id": target_tg_id,
                    "delta_cm": delta_cm,
                    "reason": reason,
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


# ── /grant_thickness (фаза 1) ───────────────────────────────────────────────


@router.message(Command("grant_thickness"))
async def handle_grant_thickness(  # noqa: PLR0911 — каждый return = отдельный UX-отказ
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    request_admin_confirm: RequestAdminConfirm,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/grant_thickness <tg_id> <new_level> <reason>` — выдать `/confirm`-токен."""
    presenter = GrantThicknessPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(presenter.usage(locale=effective_locale))
        return

    parts = raw.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(presenter.usage(locale=effective_locale))
        return

    try:
        target_tg_id = int(parts[0])
    except ValueError:
        await message.answer(presenter.bad_id(locale=effective_locale, value=parts[0]))
        return

    try:
        new_level = int(parts[1])
    except ValueError:
        await message.answer(presenter.bad_level(locale=effective_locale, value=parts[1]))
        return

    reason = parts[2].strip() if len(parts) == 3 else ""
    if not reason:
        await message.answer(presenter.no_reason(locale=effective_locale))
        return

    try:
        result = await request_admin_confirm.execute(
            RequestAdminConfirmInput(
                actor_tg_id=tg_identity.tg_user_id,
                command_kind=COMMAND_KIND_GRANT_THICKNESS,
                target_kind="player",
                target_id=str(target_tg_id),
                payload={
                    "target_tg_id": target_tg_id,
                    "new_level": new_level,
                    "reason": reason,
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


# ── /balance_get (read-only, без TOTP) ──────────────────────────────────────


@router.message(Command("balance_get"))
async def handle_balance_get(
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    get_balance_value: GetBalanceValue,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/balance_get <key>` — прочитать значение балансового ключа (read-only)."""
    presenter = GetBalanceValuePresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    key = (command.args or "").strip()
    if not key:
        await message.answer(presenter.usage(locale=effective_locale))
        return

    try:
        result = await get_balance_value.execute(
            GetBalanceValueInput(
                actor_tg_id=tg_identity.tg_user_id,
                key=key,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return
    except BalanceKeyError as e:
        await message.answer(
            presenter.key_not_found(
                locale=effective_locale,
                key=e.key,
                segment=e.segment,
                reason=e.reason,
            ),
        )
        return

    await message.answer(
        presenter.result(
            locale=effective_locale,
            key=result.key,
            value=result.raw_value,
            version=result.balance_version,
        ),
    )


# ── /balance_set (фаза 1) ───────────────────────────────────────────────────


@router.message(Command("balance_set"))
async def handle_balance_set(  # noqa: PLR0911 — каждый return = отдельный UX-отказ
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    request_admin_confirm: RequestAdminConfirm,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/balance_set <key> <value> <reason>` — выдать `/confirm`-токен.

    `value` — JSON-фрагмент (`2`, `"text"`, `[1,2]`, `{"a": 1}`). На фазе 1
    значение хранится в payload как сырой JSON-string, чтобы pydantic-
    валидация прошла на фазе 2.
    """
    presenter = SetBalanceValuePresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(presenter.usage(locale=effective_locale))
        return

    parts = raw.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(presenter.usage(locale=effective_locale))
        return
    key = parts[0]
    value_raw = parts[1]
    reason = parts[2].strip()

    if not reason:
        await message.answer(presenter.no_reason(locale=effective_locale))
        return

    parsed_value = _parse_balance_value(value_raw)
    if parsed_value is _PARSE_FAILED:
        await message.answer(presenter.bad_value(locale=effective_locale, value=value_raw))
        return

    try:
        result = await request_admin_confirm.execute(
            RequestAdminConfirmInput(
                actor_tg_id=tg_identity.tg_user_id,
                command_kind=COMMAND_KIND_BALANCE_SET,
                target_kind="balance_key",
                target_id=key,
                payload={
                    "key": key,
                    "value": parsed_value,
                    "reason": reason,
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


_PARSE_FAILED = object()


def _parse_balance_value(raw: str) -> Any:
    """Парсинг raw-строки в Python-значение через JSON.

    Возвращает `_PARSE_FAILED` при ошибке парсинга. Не использует
    bare `json.loads(raw)` без try/except — иначе пользователь
    получит трассировку.
    """
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return _PARSE_FAILED


# ── Dispatch-ы для фазы 2 (вызываются из /confirm) ─────────────────────────


@dataclass(frozen=True, slots=True)
class ConfirmDispatchDeps:
    """Контейнер всех use-case-ов, нужных dispatcher-ам `/confirm`.

    Передаётся `handle_confirm` → dispatcher. Альтернатива — отдельные
    параметры `handle_confirm`-функции; так компактнее.

    `refund_lot` добавлен в 4.1-E.13 для `dispatch_refund_lot`
    (`bot/handlers/admin_refund_lot.py`). `freeze_payouts` / `unfreeze_payouts`
    — в 4.1-E.14 для `dispatch_(un)freeze_payouts`
    (`bot/handlers/admin_freeze_payouts.py`). Расширение этого dataclass-а
    требует синхронного обновления `admin_support.handle_confirm`,
    который строит этот контейнер из aiogram-workflow-data.
    """

    grant_length: GrantLength
    grant_thickness: GrantThickness
    set_balance_value: SetBalanceValue
    ban_player: BanPlayer
    run_broadcast_announcement: RunBroadcastAnnouncement
    broadcast_task_spawner: IBroadcastTaskSpawner
    clock: IClock
    refund_lot: RefundLot
    freeze_payouts: FreezePayouts
    unfreeze_payouts: UnfreezePayouts


ConfirmDispatcher = Callable[
    [
        VerifyAdminConfirmOutput,
        Message,
        TgIdentity,
        Locale,
        IMessageBundle,
        ConfirmDispatchDeps,
    ],
    Awaitable[None],
]


async def dispatch_grant_length(  # noqa: PLR0911 — каждый return = отдельный UX-отказ
    result: VerifyAdminConfirmOutput,
    message: Message,
    identity: TgIdentity,
    locale: Locale,
    bundle: IMessageBundle,
    deps: ConfirmDispatchDeps,
) -> None:
    presenter = GrantLengthPresenter(bundle=bundle)
    replay_presenter = IdempotencyReplayPresenter(bundle=bundle)

    target_tg_id_raw = result.payload.get("target_tg_id")
    delta_raw = result.payload.get("delta_cm")
    reason_raw = result.payload.get("reason")
    if (
        not isinstance(target_tg_id_raw, int)
        or not isinstance(delta_raw, int)
        or not isinstance(reason_raw, str)
    ):
        await message.answer(
            ConfirmPayloadInvalidPresenter(bundle=bundle).message(
                locale=locale,
                command_kind=result.command_kind,
            ),
        )
        return

    idempotency_key = build_admin_idempotency_key(
        admin_tg_id=identity.tg_user_id,
        command=COMMAND_KIND_GRANT_LENGTH,
        target=str(target_tg_id_raw),
        when=deps.clock.now(),
    )

    try:
        out = await deps.grant_length.execute(
            GrantLengthInput(
                actor_tg_id=identity.tg_user_id,
                target_tg_id=target_tg_id_raw,
                delta_cm=delta_raw,
                reason=reason_raw,
                idempotency_key=idempotency_key,
                tg_chat_id=identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=locale))
        return
    except PlayerNotFoundError:
        await message.answer(presenter.not_found(locale=locale, tg_id=target_tg_id_raw))
        return
    except GrantLengthBlockedError as e:
        await message.answer(
            presenter.blocked(locale=locale, tg_id=target_tg_id_raw, reason=e.reason),
        )
        return
    except AnticheatSoftBanError:
        await message.answer(presenter.soft_ban(locale=locale, tg_id=target_tg_id_raw))
        return
    except LengthDeltaInvalidError as e:
        await message.answer(
            presenter.bad_delta(locale=locale, value=str(e.delta_cm)),
        )
        return

    if out.was_idempotent_replay:
        await message.answer(
            replay_presenter.replay(locale=locale, command_kind=result.command_kind),
        )
        return
    if out.clamped_from is not None:
        await message.answer(
            presenter.success_clamped(
                locale=locale,
                tg_id=target_tg_id_raw,
                requested_delta_cm=out.clamped_from,
                applied_delta_cm=out.applied_delta_cm,
                new_length_cm=out.new_length_cm,
            ),
        )
        return
    await message.answer(
        presenter.success(
            locale=locale,
            tg_id=target_tg_id_raw,
            applied_delta_cm=out.applied_delta_cm,
            new_length_cm=out.new_length_cm,
        ),
    )


async def dispatch_grant_thickness(  # noqa: PLR0911 — каждый return = отдельный UX-отказ
    result: VerifyAdminConfirmOutput,
    message: Message,
    identity: TgIdentity,
    locale: Locale,
    bundle: IMessageBundle,
    deps: ConfirmDispatchDeps,
) -> None:
    presenter = GrantThicknessPresenter(bundle=bundle)
    replay_presenter = IdempotencyReplayPresenter(bundle=bundle)

    target_tg_id_raw = result.payload.get("target_tg_id")
    new_level_raw = result.payload.get("new_level")
    reason_raw = result.payload.get("reason")
    if (
        not isinstance(target_tg_id_raw, int)
        or not isinstance(new_level_raw, int)
        or not isinstance(reason_raw, str)
    ):
        await message.answer(
            ConfirmPayloadInvalidPresenter(bundle=bundle).message(
                locale=locale,
                command_kind=result.command_kind,
            ),
        )
        return

    idempotency_key = build_admin_idempotency_key(
        admin_tg_id=identity.tg_user_id,
        command=COMMAND_KIND_GRANT_THICKNESS,
        target=str(target_tg_id_raw),
        when=deps.clock.now(),
    )

    try:
        out = await deps.grant_thickness.execute(
            GrantThicknessInput(
                actor_tg_id=identity.tg_user_id,
                target_tg_id=target_tg_id_raw,
                new_level=new_level_raw,
                reason=reason_raw,
                idempotency_key=idempotency_key,
                tg_chat_id=identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=locale))
        return
    except PlayerNotFoundError:
        await message.answer(presenter.not_found(locale=locale, tg_id=target_tg_id_raw))
        return
    except GrantThicknessBlockedError as e:
        await message.answer(
            presenter.blocked(locale=locale, tg_id=target_tg_id_raw, reason=e.reason),
        )
        return
    except ThicknessLevelInvalidError as e:
        await message.answer(
            presenter.level_invalid(
                locale=locale,
                level=e.level,
                max_level=e.max_level,
                reason_code=e.reason_code,
            ),
        )
        return

    if out.was_idempotent_replay:
        await message.answer(
            replay_presenter.replay(locale=locale, command_kind=result.command_kind),
        )
        return
    if out.was_already_at_level:
        await message.answer(
            presenter.already_at_level(
                locale=locale,
                tg_id=target_tg_id_raw,
                level=out.new_level,
            ),
        )
        return
    await message.answer(
        presenter.success(
            locale=locale,
            tg_id=target_tg_id_raw,
            previous_level=out.previous_level,
            new_level=out.new_level,
        ),
    )


async def dispatch_balance_set(
    result: VerifyAdminConfirmOutput,
    message: Message,
    identity: TgIdentity,
    locale: Locale,
    bundle: IMessageBundle,
    deps: ConfirmDispatchDeps,
) -> None:
    presenter = SetBalanceValuePresenter(bundle=bundle)
    replay_presenter = IdempotencyReplayPresenter(bundle=bundle)

    key_raw = result.payload.get("key")
    value_raw = result.payload.get("value")
    reason_raw = result.payload.get("reason")
    if not isinstance(key_raw, str) or not isinstance(reason_raw, str):
        await message.answer(
            ConfirmPayloadInvalidPresenter(bundle=bundle).message(
                locale=locale,
                command_kind=result.command_kind,
            ),
        )
        return
    # `value_raw` может быть любым JSON-типом — не валидируем здесь.

    idempotency_key = build_admin_idempotency_key(
        admin_tg_id=identity.tg_user_id,
        command=COMMAND_KIND_BALANCE_SET,
        target=key_raw,
        when=deps.clock.now(),
    )

    try:
        out = await deps.set_balance_value.execute(
            SetBalanceValueInput(
                actor_tg_id=identity.tg_user_id,
                key=key_raw,
                raw_value=value_raw,
                reason=reason_raw,
                idempotency_key=idempotency_key,
                tg_chat_id=identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=locale))
        return
    except BalanceKeyError as e:
        await message.answer(
            presenter.key_not_found(
                locale=locale,
                key=e.key,
                segment=e.segment,
                reason=e.reason,
            ),
        )
        return
    except ConfigError as e:
        await message.answer(
            presenter.validation_error(locale=locale, key=key_raw, error=str(e)),
        )
        return

    if out.was_idempotent_replay:
        await message.answer(
            replay_presenter.replay(locale=locale, command_kind=result.command_kind),
        )
        return
    if out.was_already_at_value:
        await message.answer(
            presenter.already_at_value(
                locale=locale,
                key=out.key,
                value=out.new_raw_value,
            ),
        )
        return
    await message.answer(
        presenter.success(
            locale=locale,
            key=out.key,
            previous_value=out.previous_raw_value,
            new_value=out.new_raw_value,
            new_version=out.new_balance_version,
        ),
    )


# Reusable presenter для invalid payload (узкий — не выносим в отдельный файл).


class ConfirmPayloadInvalidPresenter:
    __slots__ = ("_bundle",)

    def __init__(self, *, bundle: IMessageBundle) -> None:
        self._bundle = bundle

    def message(self, *, locale: Locale, command_kind: str) -> str:
        # Переиспользуем готовый ключ — payload сломан = неизвестный command_kind
        # с точки зрения dispatch-логики.
        return self._bundle.format(
            MessageKey("admin-confirm-unknown-command-kind"),
            locale=locale,
            command_kind=command_kind,
        )


async def dispatch_ban(
    result: VerifyAdminConfirmOutput,
    message: Message,
    identity: TgIdentity,
    locale: Locale,
    bundle: IMessageBundle,
    deps: ConfirmDispatchDeps,
) -> None:
    """Dispatch для `command_kind="ban"` — финализирует бан игрока."""
    presenter = ConfirmPresenter(bundle=bundle)
    ban_presenter = BanPlayerPresenter(bundle=bundle)

    target_tg_id_raw = result.payload.get("target_tg_id")
    reason_raw = result.payload.get("reason")
    if not isinstance(target_tg_id_raw, int) or not isinstance(reason_raw, str):
        await message.answer(
            presenter.unknown_command_kind(
                locale=locale,
                command_kind=result.command_kind,
            ),
        )
        return

    try:
        ban_result = await deps.ban_player.execute(
            BanPlayerInput(
                actor_tg_id=identity.tg_user_id,
                target_tg_id=target_tg_id_raw,
                reason=reason_raw,
                tg_chat_id=identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=locale))
        return
    except PlayerNotFoundError:
        await message.answer(
            ban_presenter.not_found(locale=locale, tg_id=target_tg_id_raw),
        )
        return

    if ban_result.was_already_banned:
        await message.answer(
            presenter.success_ban_already(locale=locale, tg_id=target_tg_id_raw),
        )
        return
    await message.answer(
        presenter.success_ban(locale=locale, tg_id=target_tg_id_raw),
    )


CONFIRM_DISPATCHERS: dict[str, ConfirmDispatcher] = {
    COMMAND_KIND_BAN: dispatch_ban,
    COMMAND_KIND_GRANT_LENGTH: dispatch_grant_length,
    COMMAND_KIND_GRANT_THICKNESS: dispatch_grant_thickness,
    COMMAND_KIND_BALANCE_SET: dispatch_balance_set,
}


__all__ = [
    "COMMAND_KIND_BALANCE_SET",
    "COMMAND_KIND_BAN",
    "COMMAND_KIND_GRANT_LENGTH",
    "COMMAND_KIND_GRANT_THICKNESS",
    "CONFIRM_DISPATCHERS",
    "ConfirmDispatchDeps",
    "ConfirmDispatcher",
    "dispatch_balance_set",
    "dispatch_ban",
    "dispatch_grant_length",
    "dispatch_grant_thickness",
    "router",
]
