"""Handler-ы admin-команд канала анонсов (Спринт 4.9).

`/announce_weekly` — принудительная публикация еженедельного дайджеста.
`/announce_leaderboard` — публикация текущего лидерборда.

Обе команды требуют:
- IsAdminFilter (middleware AdminGuard)
- ЛС бота (private chat)
- TOTP-подтверждение через двухфазный flow (RequestAdminConfirm → /confirm)
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from pipirik_wars.application.admin import (
    RequestAdminConfirm,
    RequestAdminConfirmInput,
    VerifyAdminConfirmOutput,
)
from pipirik_wars.application.announcements import (
    PublishLeaderboard,
    PublishWeeklyDigest,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.application.i18n.message_bundle import MessageKey
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.handlers.admin_economy import (
    CONFIRM_DISPATCHERS,
    ConfirmDispatchDeps,
)
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.domain.admin import TotpNotConfiguredError

router = Router(name="admin_announcements")
router.message.filter(IsAdminFilter())

REPLY_NON_PRIVATE_RU = "\U0001f346 Админ-команды доступны только в ЛС бота."
COMMAND_KIND_ANNOUNCE_WEEKLY = "announce_weekly"
COMMAND_KIND_ANNOUNCE_LEADERBOARD = "announce_leaderboard"

_TARGET_KIND = "announcement_channel"
_TARGET_ID = "all"


@router.message(Command("announce_weekly"))
async def handle_announce_weekly(
    message: Message,
    tg_identity: TgIdentity | None,
    request_admin_confirm: RequestAdminConfirm,
    publish_weekly_digest: PublishWeeklyDigest | None,
    announcement_channel_id: int | None,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/announce_weekly` — фаза 1, запрос TOTP-подтверждения."""
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    if publish_weekly_digest is None or announcement_channel_id is None:
        await message.answer(
            bundle.format(
                MessageKey("announce-channel-disabled"),
                locale=effective_locale,
            ),
        )
        return

    try:
        confirm_out = await request_admin_confirm.execute(
            RequestAdminConfirmInput(
                actor_tg_id=tg_identity.tg_user_id,
                command_kind=COMMAND_KIND_ANNOUNCE_WEEKLY,
                target_kind=_TARGET_KIND,
                target_id=_TARGET_ID,
                payload={"channel_id": announcement_channel_id},
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(
            bundle.format(
                MessageKey("admin-announce-not-authorized"),
                locale=effective_locale,
            ),
        )
        return
    except TotpNotConfiguredError:
        await message.answer(
            bundle.format(
                MessageKey("admin-announce-totp-not-configured"),
                locale=effective_locale,
            ),
        )
        return

    await message.answer(
        bundle.format(
            MessageKey("announce-weekly-confirm"),
            locale=effective_locale,
            token=confirm_out.token,
        ),
    )


@router.message(Command("announce_leaderboard"))
async def handle_announce_leaderboard(
    message: Message,
    tg_identity: TgIdentity | None,
    request_admin_confirm: RequestAdminConfirm,
    publish_leaderboard: PublishLeaderboard | None,
    announcement_channel_id: int | None,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/announce_leaderboard` — фаза 1, запрос TOTP-подтверждения."""
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(REPLY_NON_PRIVATE_RU)
        return

    if publish_leaderboard is None or announcement_channel_id is None:
        await message.answer(
            bundle.format(
                MessageKey("announce-channel-disabled"),
                locale=effective_locale,
            ),
        )
        return

    try:
        confirm_out = await request_admin_confirm.execute(
            RequestAdminConfirmInput(
                actor_tg_id=tg_identity.tg_user_id,
                command_kind=COMMAND_KIND_ANNOUNCE_LEADERBOARD,
                target_kind=_TARGET_KIND,
                target_id=_TARGET_ID,
                payload={"channel_id": announcement_channel_id},
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(
            bundle.format(
                MessageKey("admin-announce-not-authorized"),
                locale=effective_locale,
            ),
        )
        return
    except TotpNotConfiguredError:
        await message.answer(
            bundle.format(
                MessageKey("admin-announce-totp-not-configured"),
                locale=effective_locale,
            ),
        )
        return

    await message.answer(
        bundle.format(
            MessageKey("announce-leaderboard-confirm"),
            locale=effective_locale,
            token=confirm_out.token,
        ),
    )


# ── Фаза 2: dispatch-функции (вызываются из /confirm) ──


async def dispatch_announce_weekly(
    result: VerifyAdminConfirmOutput,
    message: Message,
    identity: TgIdentity,
    locale: Locale,
    bundle: IMessageBundle,
    deps: ConfirmDispatchDeps,
) -> None:
    """Фаза 2 — вызывается `handle_confirm` после TOTP-верификации."""
    channel_id_raw = result.payload.get("channel_id")
    if not isinstance(channel_id_raw, int):
        await message.answer("Ошибка: channel_id не задан.")
        return

    try:
        await deps.publish_weekly_digest.execute(channel_id=channel_id_raw)
    except Exception:
        await message.answer(
            "\u274c Ошибка при публикации дайджеста. Проверь логи.",
        )
        return

    await message.answer(
        f"\u2705 Еженедельный дайджест опубликован в канал {channel_id_raw}.",
    )


async def dispatch_announce_leaderboard(
    result: VerifyAdminConfirmOutput,
    message: Message,
    identity: TgIdentity,
    locale: Locale,
    bundle: IMessageBundle,
    deps: ConfirmDispatchDeps,
) -> None:
    """Фаза 2 — вызывается `handle_confirm` после TOTP-верификации."""
    channel_id_raw = result.payload.get("channel_id")
    if not isinstance(channel_id_raw, int):
        await message.answer("Ошибка: channel_id не задан.")
        return

    try:
        await deps.publish_leaderboard.execute(channel_id=channel_id_raw)
    except Exception:
        await message.answer(
            "\u274c Ошибка при публикации лидерборда. Проверь логи.",
        )
        return

    await message.answer(
        f"\u2705 Лидерборд опубликован в канал {channel_id_raw}.",
    )


CONFIRM_DISPATCHERS[COMMAND_KIND_ANNOUNCE_WEEKLY] = dispatch_announce_weekly
CONFIRM_DISPATCHERS[COMMAND_KIND_ANNOUNCE_LEADERBOARD] = dispatch_announce_leaderboard
