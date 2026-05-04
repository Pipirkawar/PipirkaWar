"""Application-сервис подсистемы безопасности.

`ActivityLockService` оборачивает `IActivityLockRepository` в use-case
с поведением «попробуй взять — если занят, бросай ошибку».
"""

from pipirik_wars.application.security.activity_lock_service import (
    ActivityLockService,
)

__all__ = ["ActivityLockService"]
