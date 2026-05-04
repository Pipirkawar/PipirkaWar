"""pydantic-settings: вся конфигурация — из env. Никакого хардкода.

Структура:
- `Settings` — корень, агрегирует под-секции.
- `DatabaseSettings` — подключение к Postgres.
- `BootstrapSettings` — `BOOTSTRAP_ADMIN_IDS` для одноразового
  bootstrap первого `super_admin`-а (ГДД §18.6.4).
"""

from pipirik_wars.infrastructure.settings.settings import (
    BootstrapSettings,
    DatabaseSettings,
    Settings,
)

__all__ = ["BootstrapSettings", "DatabaseSettings", "Settings"]
