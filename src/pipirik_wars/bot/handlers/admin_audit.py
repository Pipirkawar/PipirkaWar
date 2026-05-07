"""Handler команды `/audit` (Спринт 2.5-D.5, ГДД §18.6.4).

`/audit [target_tg_id|-] [action|-] [limit]` — read-side листинг
`admin_audit_log`-а. Все аргументы опциональные; разделитель — пробел.
Спецсимвол `-` (минус) или `_` означает «без фильтра» — используется,
чтобы передать только третий позиционный аргумент.

Примеры:

* `/audit` — последние 20 записей по всем админам.
* `/audit 12345` — последние 20 записей админа с tg_id=12345.
* `/audit 12345 admin_player_banned` — только баны от этого админа.
* `/audit - admin_balance_set 50` — все админы, фильтр по action,
  limit=50 (≤ MAX_AUDIT_LIMIT).

Доступ — любой активный админ (read-side observability,
ГДД §18.6.4). Сам факт обращения логируется.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from pipirik_wars.application.admin import (
    DEFAULT_AUDIT_LIMIT,
    AdminAuditActionUnknownError,
    GetAdminAuditTrail,
    GetAdminAuditTrailInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_audit import AuditTrailPresenter

router = Router(name="admin_audit")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

REPLY_NON_PRIVATE_RU = "🍆 Админ-команды доступны только в ЛС бота."

_NO_FILTER_SENTINELS = frozenset({"-", "_"})


def _parse_optional_int(raw: str) -> int | None:
    """Распарсить аргумент как `int` либо `None` (при `-`/`_`).

    Поднимает `ValueError` на любую другую невалидную строку — handler
    сам решает, какой текст показать.
    """
    if raw in _NO_FILTER_SENTINELS:
        return None
    return int(raw)


def _parse_optional_action(raw: str) -> str | None:
    if raw in _NO_FILTER_SENTINELS:
        return None
    return raw


@router.message(Command("audit"))
async def handle_audit(  # noqa: PLR0911 — каждый return = отдельный UX-отказ
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    get_admin_audit_trail: GetAdminAuditTrail,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/audit` — листинг последних записей админ-аудит-лога."""
    presenter = AuditTrailPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    args = (command.args or "").split()
    target_admin_tg_id: int | None = None
    action_value: str | None = None
    limit_arg: int | None = None

    if len(args) >= 1:
        try:
            target_admin_tg_id = _parse_optional_int(args[0])
        except ValueError:
            await message.answer(presenter.bad_tg_id(locale=effective_locale, value=args[0]))
            return
    if len(args) >= 2:
        action_value = _parse_optional_action(args[1])
    if len(args) >= 3:
        try:
            parsed_limit = int(args[2])
        except ValueError:
            await message.answer(presenter.bad_limit(locale=effective_locale, value=args[2]))
            return
        if parsed_limit <= 0:
            await message.answer(presenter.bad_limit(locale=effective_locale, value=args[2]))
            return
        limit_arg = parsed_limit

    use_case_input = GetAdminAuditTrailInput(
        actor_tg_id=tg_identity.tg_user_id,
        target_admin_tg_id=target_admin_tg_id,
        action_value=action_value,
        limit=limit_arg if limit_arg is not None else DEFAULT_AUDIT_LIMIT,
        tg_chat_id=tg_identity.chat_id,
    )

    try:
        out = await get_admin_audit_trail.execute(use_case_input)
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return
    except AdminAuditActionUnknownError as exc:
        await message.answer(presenter.unknown_action(locale=effective_locale, value=exc.value))
        return

    if not out.target_admin_resolved and out.target_admin_tg_id is not None:
        await message.answer(
            presenter.target_not_found(locale=effective_locale, tg_id=out.target_admin_tg_id),
        )
        return

    if not out.records:
        await message.answer(
            presenter.empty(
                locale=effective_locale,
                target_admin_tg_id=out.target_admin_tg_id,
                action=out.action,
            ),
        )
        return

    await message.answer(
        presenter.render(
            locale=effective_locale,
            target_admin_tg_id=out.target_admin_tg_id,
            action=out.action,
            limit=out.limit,
            records=out.records,
        ),
    )
