"""Use-case вокруг блокировок действий."""

from __future__ import annotations

from datetime import timedelta

from pipirik_wars.domain.security import (
    IActivityLockRepository,
    LockAlreadyHeldError,
    LockReason,
)
from pipirik_wars.domain.shared.ports import IClock


class ActivityLockService:
    """Берёт и снимает блок «у этого актора сейчас идёт операция X».

    Использование — внутри транзакции (`IUnitOfWork`):

    >>> async with uow:  # doctest: +SKIP
    ...     await locks.acquire(
    ...         actor_kind="player",
    ...         actor_id=42,  # doctest: +SKIP
    ...         reason=LockReason.FOREST,  # doctest: +SKIP
    ...         ttl=timedelta(minutes=2),
    ...     )  # doctest: +SKIP
    ...     ...  # бизнес-операция                                  # doctest: +SKIP
    ...     await locks.release(actor_kind="player", actor_id=42)  # doctest: +SKIP
    """

    __slots__ = ("_clock", "_repo")

    def __init__(
        self,
        *,
        repository: IActivityLockRepository,
        clock: IClock,
    ) -> None:
        self._repo = repository
        self._clock = clock

    async def acquire(
        self,
        *,
        actor_kind: str,
        actor_id: int,
        reason: LockReason,
        ttl: timedelta,
    ) -> None:
        """Попытаться взять блок. Бросает `LockAlreadyHeldError` при конфликте."""
        if ttl.total_seconds() <= 0:
            raise ValueError("ttl must be positive")
        now = self._clock.now()
        ok = await self._repo.try_acquire(
            actor_kind=actor_kind,
            actor_id=actor_id,
            reason=reason,
            now=now,
            expires_at=now + ttl,
        )
        if not ok:
            raise LockAlreadyHeldError(
                actor_kind=actor_kind,
                actor_id=actor_id,
            )

    async def release(self, *, actor_kind: str, actor_id: int) -> None:
        """Снять блок (NO-OP если блока не было)."""
        await self._repo.release(actor_kind=actor_kind, actor_id=actor_id)
