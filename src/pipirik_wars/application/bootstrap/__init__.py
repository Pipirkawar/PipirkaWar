"""Bootstrap-сценарии (одноразовые при первом запуске).

`BootstrapSuperAdmin` — выдаёт первый `super_admin`-аккаунт из
env-переменной `BOOTSTRAP_ADMIN_IDS` при пустой таблице `admins`.
ГДД §18.6.4, `development_plan.md` Спринт 0.2.6.
"""

from pipirik_wars.application.bootstrap.admin import (
    BootstrapResult,
    BootstrapSuperAdmin,
)

__all__ = ["BootstrapResult", "BootstrapSuperAdmin"]
