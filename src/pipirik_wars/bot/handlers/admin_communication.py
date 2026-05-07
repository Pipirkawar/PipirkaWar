"""Handler-ы коммуникационных admin-команд (Спринт 2.5-D.4, ГДД §18.6.5).

`/announce <ru|en|*> <текст>` — глобальная рассылка от super-admin-а
с обязательным TOTP-подтверждением. Идёт двухфазно (см.
`application/admin/broadcast_announcement.py`):

* Фаза 1: `handle_announce` парсит `args`, валидирует/RBAC через
  `BroadcastAnnouncement.execute(...)`, кладёт payload в
  `IAdminConfirmStore` через `RequestAdminConfirm`, отвечает админу
  «нажми /confirm».
* Фаза 2: `dispatch_announce` (зарегистрирован в
  `bot/handlers/admin_economy.py::CONFIRM_DISPATCHERS`) вызывается
  обобщённым `handle_confirm` после успешной TOTP-верификации.
  Запускает фоновую задачу `RunBroadcastAnnouncement` через
  `IBroadcastTaskSpawner`, отвечает админу «отправляю N игрокам»;
  фоновая задача шлёт сообщения с throttle ≤ 25 msg/sec и фиксирует
  итог в admin-аудите (`ADMIN_BROADCAST_SENT`).

Roadmap: если в Спринте 4.5 появится web-панель админа — этот же
use-case-flow (фаза 1 → confirm → фаза 2) будет переиспользован
из web-handler-а; локали из `admin-announce-*` тоже общие, никакой
дополнительной работы не потребуется.
"""

from __future__ import annotations

import contextlib

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from pipirik_wars.application.admin import (
    BROADCAST_MESSAGE_MAX_LEN,
    BroadcastAnnouncement,
    BroadcastAnnouncementInput,
    BroadcastLocaleFilter,
    BroadcastLocaleFilterInvalidError,
    BroadcastMessageEmptyError,
    BroadcastMessageTooLongError,
    RequestAdminConfirm,
    RequestAdminConfirmInput,
    RunBroadcastAnnouncement,
    RunBroadcastAnnouncementInput,
    VerifyAdminConfirmOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.handlers.admin_economy import (
    CONFIRM_DISPATCHERS,
    ConfirmDispatchDeps,
)
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_communication import AnnouncePresenter
from pipirik_wars.domain.admin import TotpNotConfiguredError

router = Router(name="admin_communication")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

#: command_kind для регистрации в `CONFIRM_DISPATCHERS`. Должен совпадать
#: со значением `AdminCommandKind.BROADCAST_ANNOUNCEMENT.value`,
#: иначе registry-роутинг сломается «молча».
COMMAND_KIND_BROADCAST_ANNOUNCEMENT = "broadcast_announcement"

REPLY_NON_PRIVATE_RU = "🍆 Админ-команды доступны только в ЛС бота."


@router.message(Command("announce"))
async def handle_announce(  # noqa: PLR0911 — каждый return = отдельный UX-отказ
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    broadcast_announcement: BroadcastAnnouncement,
    request_admin_confirm: RequestAdminConfirm,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/announce <ru|en|*> <text>` — фаза 1, выдать `/confirm`-токен."""
    presenter = AnnouncePresenter(bundle=bundle)
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
        await message.answer(presenter.usage(locale=effective_locale))
        return
    locale_filter_raw, message_raw = parts[0], parts[1]

    try:
        announce_out = await broadcast_announcement.execute(
            BroadcastAnnouncementInput(
                actor_tg_id=tg_identity.tg_user_id,
                locale_filter_raw=locale_filter_raw,
                message_raw=message_raw,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return
    except BroadcastLocaleFilterInvalidError as e:
        await message.answer(presenter.bad_locale(locale=effective_locale, value=e.value))
        return
    except BroadcastMessageEmptyError:
        await message.answer(presenter.empty_message(locale=effective_locale))
        return
    except BroadcastMessageTooLongError as e:
        await message.answer(
            presenter.too_long(
                locale=effective_locale,
                length=e.length,
                max_length=BROADCAST_MESSAGE_MAX_LEN,
            ),
        )
        return

    try:
        confirm_out = await request_admin_confirm.execute(
            RequestAdminConfirmInput(
                actor_tg_id=tg_identity.tg_user_id,
                command_kind=COMMAND_KIND_BROADCAST_ANNOUNCEMENT,
                target_kind="locale_filter",
                target_id=announce_out.locale_filter.value,
                payload={
                    "locale_filter": announce_out.locale_filter.value,
                    "message": announce_out.message,
                    "recipient_count": announce_out.recipient_count,
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
            token=confirm_out.token,
            ttl_seconds=confirm_out.ttl_seconds,
            recipient_count=announce_out.recipient_count,
            locale_filter=announce_out.locale_filter.value,
        ),
    )


async def dispatch_announce(
    result: VerifyAdminConfirmOutput,
    message: Message,
    identity: TgIdentity,
    locale: Locale,
    bundle: IMessageBundle,
    deps: ConfirmDispatchDeps,
) -> None:
    """Фаза 2 `/announce` — запускает фоновую рассылку после успешного TOTP.

    Не блокирует handler: отправляет «отправляю N игрокам» и через
    `IBroadcastTaskSpawner.spawn(...)` отдаёт coro фоновой задаче. Сама
    рассылка пишет итог в admin-аудит и отвечает админу финальным
    сообщением «отправлено: X, failed: Y, blocked: Z».
    """
    presenter = AnnouncePresenter(bundle=bundle)

    locale_filter_raw = result.payload.get("locale_filter")
    message_raw = result.payload.get("message")
    if not isinstance(locale_filter_raw, str) or not isinstance(message_raw, str):
        # Payload собирается фазой 1 — валидным он быть обязан. Если не
        # тот — уже что-то сломалось в TOTP-store-е; отвечаем в виде
        # «not authorized», чтобы не светить детали в чужой чат.
        await message.answer(presenter.not_authorized(locale=locale))
        return

    try:
        locale_filter = BroadcastLocaleFilter(locale_filter_raw)
    except ValueError:
        await message.answer(presenter.not_authorized(locale=locale))
        return

    recipient_count_raw = result.payload.get("recipient_count")
    recipient_count = recipient_count_raw if isinstance(recipient_count_raw, int) else 0

    await message.answer(
        presenter.progress_start(
            locale=locale,
            recipient_count=recipient_count,
            locale_filter=locale_filter.value,
        ),
    )

    deps.broadcast_task_spawner.spawn(
        _run_broadcast_and_report(
            run_broadcast_announcement=deps.run_broadcast_announcement,
            input_=RunBroadcastAnnouncementInput(
                actor_tg_id=identity.tg_user_id,
                locale_filter=locale_filter,
                message=message_raw,
                tg_chat_id=identity.chat_id,
            ),
            message=message,
            locale=locale,
            presenter=presenter,
        ),
    )


async def _run_broadcast_and_report(
    *,
    run_broadcast_announcement: RunBroadcastAnnouncement,
    input_: RunBroadcastAnnouncementInput,
    message: Message,
    locale: Locale,
    presenter: AnnouncePresenter,
) -> None:
    """Coro, прокинутая в `IBroadcastTaskSpawner.spawn(...)`.

    Запускает use-case рассылки и шлёт админу финальный отчёт. Любые
    исключения внутри (включая `AdminAuthorizationDeniedError`, если
    у админа отозвали роль между фазами 1 и 2) поглощаются и
    превращаются в локализованное «фоновая рассылка завершилась с
    ошибкой» — иначе background-task закроется с unobserved exception
    и super-admin никогда не увидит результата.
    """
    try:
        out = await run_broadcast_announcement.execute(input_)
    except Exception:
        with contextlib.suppress(Exception):
            await message.answer(presenter.progress_failed(locale=locale))
        return

    with contextlib.suppress(Exception):
        await message.answer(
            presenter.progress_final(
                locale=locale,
                recipient_count=out.recipient_count,
                sent_count=out.sent_count,
                failed_count=out.failed_count,
                blocked_count=out.blocked_count,
            ),
        )


# Регистрация в общем registry-диспетчере `/confirm`-handler-а. Импорт
# `CONFIRM_DISPATCHERS` сразу мутирует словарь — модуль должен быть
# подтянут в `bot/handlers/__init__.py` до `register_routers`-вызова,
# что и происходит при `include_router(admin_communication_router)`.
CONFIRM_DISPATCHERS[COMMAND_KIND_BROADCAST_ANNOUNCEMENT] = dispatch_announce


__all__ = [
    "COMMAND_KIND_BROADCAST_ANNOUNCEMENT",
    "dispatch_announce",
    "router",
]
