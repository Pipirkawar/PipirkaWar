"""Доменный пакет монетизации (ГДД §12.5–§12.6, Фаза 4 / Спринт 4.1).

Ре-экспорт публичных VO / сущностей / ошибок: импорт из соседних
доменных пакетов и application-слоя должен идти одной строкой:

    from pipirik_wars.domain.monetization import (
        Currency,
        IdempotencyConflictError,
        IdempotencyKey,
        Payment,
        PaymentStatus,
        StarsAmount,
    )

Это идентично конвенции `domain/roulette/__init__.py` (Спринт 3.5-A) и
`domain/oracle/__init__.py` (Спринт 3.6-A).
"""

from pipirik_wars.domain.monetization.entities import (
    Payment,
    PaymentStatus,
)
from pipirik_wars.domain.monetization.errors import (
    IdempotencyConflictError,
    MonetizationDomainError,
)
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    IdempotencyKey,
    StarsAmount,
)

__all__ = [
    "Currency",
    "IdempotencyConflictError",
    "IdempotencyKey",
    "MonetizationDomainError",
    "Payment",
    "PaymentStatus",
    "StarsAmount",
]
