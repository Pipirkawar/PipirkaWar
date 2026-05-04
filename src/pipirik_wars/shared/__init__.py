"""Shared-слой: кросс-инструменты, не зависящие от слоёв.

Содержит logger, metrics, общие исключения. Используется всеми слоями.
"""

from pipirik_wars.shared.errors import (
    ConcurrencyError,
    ConfigError,
    DomainError,
    IntegrityError,
    PipirikError,
)

__all__ = [
    "ConcurrencyError",
    "ConfigError",
    "DomainError",
    "IntegrityError",
    "PipirikError",
]
