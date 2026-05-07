"""Доменные ошибки use-case-а `SetupAdminTotp` (Спринт 2.5-D.6, ГДД §18.6).

Команда `/admin_setup_totp <password>` — self-service выдача TOTP-секрета
живому super-admin-у. Защищена одноразовым `bootstrap_admin_password`,
прокинутым админу out-of-band (например, через переменную окружения
бота, доступную только оператору VM). Возможные «несчастливые» ветки —
здесь:

- `BootstrapPasswordNotConfiguredError` — оператор не задал
  `BOOTSTRAP_ADMIN_PASSWORD` в окружении бота. Команда не должна
  работать «впустую» — если её можно вызвать без пароля, то
  достаточно пройти RBAC, и self-service-выдача нового секрета
  становится тривиальной для атакующего.
- `BootstrapPasswordInvalidError` — пароль не сошёлся (constant-time
  check). Не раскрываем, был ли пароль настроен или просто введён
  неверно — это второй фактор после RBAC.
- `TotpAlreadyConfiguredError` — у админа уже есть `totp_secret`.
  Перезапись запрещена: если злоумышленник перехватил bootstrap-пароль,
  он не сможет молча подменить чужой секрет (super-admin сначала
  должен явно сбросить поле в БД). Соответствует ГДД §18.6.5
  «потерял 2FA → super-admin сбрасывает в БД».
"""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError


class BootstrapPasswordNotConfiguredError(DomainError):
    """В окружении бота не задан `BOOTSTRAP_ADMIN_PASSWORD`.

    Если переменная не настроена, команда `/admin_setup_totp` должна
    отказывать всегда — это намеренный fail-closed для self-service-а.
    """


class BootstrapPasswordInvalidError(DomainError):
    """Введённый bootstrap-пароль не сошёлся."""


class TotpAlreadyConfiguredError(DomainError):
    """У админа уже настроен `totp_secret` — перезапись запрещена.

    Сбросить можно только вручную в БД (super-admin via SQL). Это
    защита от тихой подмены чужого секрета злоумышленником,
    перехватившим bootstrap-пароль.
    """


__all__ = [
    "BootstrapPasswordInvalidError",
    "BootstrapPasswordNotConfiguredError",
    "TotpAlreadyConfiguredError",
]
