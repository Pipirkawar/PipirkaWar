"""Application-слой расширенного админ-интерфейса (Спринт 2.5).

Use-case-ы, общие для всех опасных команд:

* `RequestAdminConfirm` — выдаёт одноразовый `token` и регистрирует
  ожидание TOTP-кода в `IAdminConfirmStore` (TTL 60 секунд).
* `VerifyAdminConfirm` — забирает токен из store-а, проверяет
  6-значный код через `ITotpVerifier`, возвращает payload команды
  для продолжения работы.

Сами целевые команды (`/ban`, `/grant_*`, `/balance_set`, `/announce`)
живут в `application/admin/<command>/` и появятся в Спринтах 2.5-B/C/D.
"""

from pipirik_wars.application.admin.request_confirm import (
    RequestAdminConfirm,
    RequestAdminConfirmInput,
    RequestAdminConfirmOutput,
    TokenFactory,
)
from pipirik_wars.application.admin.verify_confirm import (
    VerifyAdminConfirm,
    VerifyAdminConfirmInput,
    VerifyAdminConfirmOutput,
)

__all__ = [
    "RequestAdminConfirm",
    "RequestAdminConfirmInput",
    "RequestAdminConfirmOutput",
    "TokenFactory",
    "VerifyAdminConfirm",
    "VerifyAdminConfirmInput",
    "VerifyAdminConfirmOutput",
]
