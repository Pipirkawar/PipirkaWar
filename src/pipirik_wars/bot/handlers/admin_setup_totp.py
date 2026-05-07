"""Handler команды `/admin_setup_totp` (Спринт 2.5-D.6, ГДД §18.6.5).

`/admin_setup_totp <bootstrap_password>` — self-service выдача
TOTP-секрета super-admin-у. Вызывается один раз при первом подключении
2FA: после успешного выполнения `admin.totp_secret` заполнен, и все
последующие опасные команды могут проходить TOTP-confirm-flow.

Особенности:

* Только в ЛС бота — пароль и `otpauth://`-URI не должны попасть в
  групповой чат (даже если все участники — админы).
* На router-уровне висит `IsAdminFilter` (как у остальных admin-router-ов).
  Use-case дополнительно проверяет `is_active` и RBAC-матрицу
  (`AdminCommandKind.SETUP_TOTP` ⇒ только `SUPER_ADMIN`).
* Сам секрет и `otpauth://`-URI **не пишутся в чат**: они логируются
  на `INFO`-уровне в `structlog` с явным маркером `admin_totp_setup`.
  В чат уходит короткое подтверждение «настроено, секрет в логах сервера».
  Это компромисс: в чат-историю Telegram-а такие данные класть нельзя
  (если кто-то сможет прочитать историю чата — он получит секрет даже
  спустя месяцы); но оператор должен иметь возможность скопировать
  секрет/URI в TOTP-приложение, поэтому отдаём их в server-side-логи.
"""

from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import Message

from pipirik_wars.application.admin import (
    SetupAdminTotp,
    SetupAdminTotpInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import DEFAULT_LOCALE, IMessageBundle, Locale
from pipirik_wars.bot.filters import IsAdminFilter
from pipirik_wars.bot.middlewares import TgIdentity
from pipirik_wars.bot.presenters.admin_setup_totp import SetupAdminTotpPresenter
from pipirik_wars.domain.admin import (
    AdminAuthorizationDeniedError,
    BootstrapPasswordInvalidError,
    BootstrapPasswordNotConfiguredError,
    TotpAlreadyConfiguredError,
)

router = Router(name="admin_setup_totp")
router.message.filter(IsAdminFilter())

#: Структурированный logger handler-а. Маркер `event="admin_totp_setup"`
#: — точка фильтрации в централизованных логах: только эта запись
#: содержит `provisioning_uri`, остальные admin-команды его не пишут.
_log = structlog.get_logger(__name__)


@router.message(Command("admin_setup_totp"))
async def handle_admin_setup_totp(  # noqa: PLR0911 — каждый return = отдельный UX-отказ
    message: Message,
    command: CommandObject,
    tg_identity: TgIdentity | None,
    setup_admin_totp: SetupAdminTotp,
    bundle: IMessageBundle,
    locale: Locale | None = None,
) -> None:
    """`/admin_setup_totp <bootstrap_password>` — настроить TOTP-секрет.

    Каждая ветка ниже ⇒ отдельный UX-отказ; общий принцип — наружу
    (в чат) идёт только локализованный текст без подсказок «какой
    именно шаг провалился» (для подсказок есть structlog).
    """
    presenter = SetupAdminTotpPresenter(bundle=bundle)
    effective_locale = locale or DEFAULT_LOCALE

    chat_kind = tg_identity.chat_kind if tg_identity is not None else message.chat.type
    if chat_kind != "private" or tg_identity is None:
        await message.answer(presenter.non_private(locale=effective_locale))
        return

    raw = (command.args or "").strip()
    if not raw:
        await message.answer(presenter.usage(locale=effective_locale))
        return

    try:
        out = await setup_admin_totp.execute(
            SetupAdminTotpInput(
                actor_tg_id=tg_identity.tg_user_id,
                password=raw,
                tg_chat_id=tg_identity.chat_id,
            ),
        )
    except AuthorizationError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return
    except AdminAuthorizationDeniedError:
        await message.answer(presenter.not_authorized(locale=effective_locale))
        return
    except BootstrapPasswordNotConfiguredError:
        await message.answer(presenter.password_not_configured(locale=effective_locale))
        return
    except BootstrapPasswordInvalidError:
        await message.answer(presenter.password_invalid(locale=effective_locale))
        return
    except TotpAlreadyConfiguredError:
        await message.answer(presenter.already_configured(locale=effective_locale))
        return

    # Секрет и `otpauth://`-URI пишем только в server-side-логи.
    # `event="admin_totp_setup"` — единственная точка, где `provisioning_uri`
    # вообще оказывается в логах; в `admin_audit_log` этих полей нет
    # (см. `SetupAdminTotp` use-case, шаг 8 «before/after = None»).
    _log.info(
        "admin_totp_setup",
        actor_tg_id=tg_identity.tg_user_id,
        secret=out.secret,
        provisioning_uri=out.provisioning_uri,
    )
    await message.answer(presenter.success(locale=effective_locale))


__all__ = ["router"]
