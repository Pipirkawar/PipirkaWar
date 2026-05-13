"""Доменные порты (интерфейсы) для слоёв `application` и `infrastructure`.

Каждый порт описывает контракт, реализация которого живёт в
`infrastructure/` (production) или в `tests/fakes/` (для unit-тестов).
В самом `domain/` нельзя импортировать ничего, кроме stdlib и других
модулей `domain/` — это проверяется `import-linter` (см. `.importlinter`).
"""

from pipirik_wars.domain.shared.ports.audit import (
    AuditAction,
    AuditEntry,
    AuditRecord,
    AuditSource,
    IAuditLogger,
    IAuditLogQuery,
)
from pipirik_wars.domain.shared.ports.clock import IClock
from pipirik_wars.domain.shared.ports.idempotency import IIdempotencyKey
from pipirik_wars.domain.shared.ports.random import IRandom
from pipirik_wars.domain.shared.ports.rate_limiter import IRateLimiter
from pipirik_wars.domain.shared.ports.scheduler import IDelayedJobScheduler
from pipirik_wars.domain.shared.ports.uow import IUnitOfWork

__all__ = [
    "AuditAction",
    "AuditEntry",
    "AuditRecord",
    "AuditSource",
    "IAuditLogQuery",
    "IAuditLogger",
    "IClock",
    "IDelayedJobScheduler",
    "IIdempotencyKey",
    "IRandom",
    "IRateLimiter",
    "IUnitOfWork",
]
