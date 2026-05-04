"""Доменная подсистема админ-доступа.

`Admin` — это NOT игрок: это аккаунт с ролью (`super_admin`, `economist`,
`support`, `read_only`), идентифицируемый по `tg_id`. Используется и в
ТГ-админ-командах (`/admin_*`), и в опциональной веб-панели (Спринт 4.5).
ГДД §18.6, §18.6.4 (bootstrap).
"""

from pipirik_wars.domain.admin.entities import Admin, AdminRole
from pipirik_wars.domain.admin.repositories import IAdminRepository

__all__ = ["Admin", "AdminRole", "IAdminRepository"]
