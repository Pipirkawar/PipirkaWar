"""Фейк Unit of Work: считает commit/rollback и эмулирует rollback на исключении."""

from __future__ import annotations

from types import TracebackType
from typing import Self

from pipirik_wars.domain.shared.ports import IUnitOfWork


class FakeUnitOfWork(IUnitOfWork):
    """In-memory UoW.

    Не реализует «откат» данных (тестовые fakes сами должны это делать,
    если им важна транзакционность), но честно считает commit/rollback —
    позволяет тестам проверять, что use-case коммитит ровно один раз.
    """

    __slots__ = ("_in_context", "commits", "rollbacks")

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self._in_context = False

    async def __aenter__(self) -> Self:
        if self._in_context:
            raise RuntimeError("FakeUnitOfWork: nested context not allowed")
        self._in_context = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                await self.commit()
            else:
                await self.rollback()
        finally:
            self._in_context = False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
