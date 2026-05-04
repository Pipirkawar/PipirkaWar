"""Доменные сущности подсистемы админ-доступа."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime


class AdminRole(str, enum.Enum):
    """Роли админ-доступа.

    Иерархия (ГДД §18.6):
    - `super_admin` — полный доступ, в том числе UPDATE балансовых констант.
    - `economist`   — UPDATE/READ балансовых констант, READ всего остального.
    - `support`     — операционные действия (анбан, выдача см вручную с ауд.).
    - `read_only`   — только чтение.
    """

    SUPER_ADMIN = "super_admin"
    ECONOMIST = "economist"
    SUPPORT = "support"
    READ_ONLY = "read_only"


@dataclass(frozen=True, slots=True)
class Admin:
    """Админ-аккаунт.

    Идентификатор — внутренний `id` (Postgres serial), но публичный
    «ключ» — `tg_id` (Telegram user_id). Активные = `is_active=True`;
    отозванные сохраняем в БД (для аудита), но не пускаем.
    """

    id: int | None
    tg_id: int
    role: AdminRole
    is_active: bool
    created_at: datetime
    created_by_admin_id: int | None = None
    note: str | None = field(default=None)

    def can_write_balance(self) -> bool:
        """Может ли менять `balance.yaml` через админ-команды."""
        return self.is_active and self.role in {
            AdminRole.SUPER_ADMIN,
            AdminRole.ECONOMIST,
        }

    def can_grant_admin(self) -> bool:
        """Может ли выдавать новых админов."""
        return self.is_active and self.role == AdminRole.SUPER_ADMIN

    def can_manage_runtime_config(self) -> bool:
        """Может ли менять runtime-настройки бота (`MAX_DAU` и т.п.).

        Отличается от `can_write_balance`: балансовые константы — это
        геймдиз (правит `economist`), а runtime-настройки — это
        инфраструктура (правит `super_admin`). На текущей фазе
        изменение `MAX_DAU` через `/set_max_dau` — единственная
        runtime-настройка под этим правом.
        """
        return self.is_active and self.role == AdminRole.SUPER_ADMIN
