"""Реализация `IUnitOfWork` поверх SQLAlchemy 2.x async session."""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pipirik_wars.domain.shared.ports import IUnitOfWork


class SqlAlchemyUnitOfWork(IUnitOfWork):
    """Async UoW.

    Открывает сессию в `__aenter__`, коммитит в `__aexit__` (или
    откатывает при исключении). Сама сессия открывается заново каждый
    раз — UoW рассчитан на короткие транзакции, не на длинные.

    Сессия доступна как `uow.session` для репозиториев / сервисов,
    которые пробрасываются явно (см. композиционный root в `bot/main.py`).
    """

    __slots__ = ("_session", "_session_maker")

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_maker = session_maker
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        """Текущая сессия. Доступна только внутри `async with uow:`."""
        if self._session is None:
            raise RuntimeError("UnitOfWork is not entered")
        return self._session

    async def __aenter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("Nested UnitOfWork is not allowed")
        self._session = self._session_maker()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._session is None:  # pragma: no cover — защитный invariant
            return
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not entered")
        await self._session.commit()

    async def rollback(self) -> None:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not entered")
        await self._session.rollback()
