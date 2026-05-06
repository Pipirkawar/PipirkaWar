"""Доменные VO + ошибки подсистемы TOTP-подтверждения опасных команд.

Спринт 2.5-A.3 (ГДД §18.6) — TOTP-подтверждение для команд `/ban`,
`/grant_*`, `/balance_set`, `/announce`. Поток:

1. Админ вызывает опасную команду (например, `/ban 12345 spam`).
2. Handler собирает payload и вызывает `RequestAdminConfirm` —
   получает однократный `token` и время до истечения. В чат
   приходит сообщение «введи 6-значный код TOTP».
3. Админ присылает 6-значный код. Handler вызывает
   `VerifyAdminConfirm(token, code)` — если ОК, получает обратно
   payload и продолжает выполнение команды; если нет — сообщение
   об ошибке + audit-запись `ADMIN_CONFIRM_FAILED`.

Сам TOTP-secret хранится в `admins.totp_secret` (BASE32) — добавляется
миграцией `0017_admins_totp_secret`. `None` означает «у админа не
настроено 2FA», опасные команды для него отказываются.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from pipirik_wars.shared.errors import DomainError


@dataclass(frozen=True, slots=True)
class AdminConfirmRequest:
    """Описание ожидающего подтверждения admin-действия.

    `payload` — namespace-аргументы команды, чтобы handler смог
    продолжить выполнение после успешного подтверждения, не зная,
    что внутри (Liskov: разные команды возвращают разные payload-ы).
    """

    admin_id: int
    command_kind: str
    target_kind: str
    target_id: str
    payload: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class AdminConfirmEntry:
    """Состояние ожидающего подтверждения, как оно лежит в store."""

    request: AdminConfirmRequest
    expires_at: datetime


class AdminConfirmError(DomainError):
    """Базовое исключение TOTP-подтверждения."""


class ConfirmTokenNotFoundError(AdminConfirmError):
    """Токен не существует (никогда не выдавался или уже отработал)."""


class ConfirmTokenExpiredError(AdminConfirmError):
    """Токен существовал, но TTL истёк."""


class ConfirmAdminMismatchError(AdminConfirmError):
    """Подтверждает не тот админ, что инициировал команду."""


class ConfirmCodeInvalidError(AdminConfirmError):
    """6-значный код TOTP не сошёлся."""


class TotpNotConfiguredError(AdminConfirmError):
    """У админа `totp_secret IS NULL` — 2FA не настроено."""


__all__ = [
    "AdminConfirmEntry",
    "AdminConfirmError",
    "AdminConfirmRequest",
    "ConfirmAdminMismatchError",
    "ConfirmCodeInvalidError",
    "ConfirmTokenExpiredError",
    "ConfirmTokenNotFoundError",
    "TotpNotConfiguredError",
]
