"""Unit of Work — границы транзакции.

Любая мутация состояния в `application/` идёт **только** внутри
`async with uow: ...`. Это гарантия атомарности: либо вся
бизнес-операция применилась (длина игрока, audit-запись, idempotency-ключ),
либо ничего. ГДД §0 — «безопасность и целостность данных».

Конкретная реализация (`infrastructure/db/uow.py`) — поверх SQLAlchemy
async session с явным `commit/rollback`. На время Спринта 0.1 здесь
только интерфейс.
"""

from __future__ import annotations

import abc
from types import TracebackType
from typing import Self


class IUnitOfWork(abc.ABC):
    """Контекст транзакции."""

    @abc.abstractmethod
    async def __aenter__(self) -> Self:
        """Открыть транзакцию."""

    @abc.abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Закрыть транзакцию: commit при отсутствии исключения, иначе rollback."""

    @abc.abstractmethod
    async def commit(self) -> None:
        """Явный commit. Обычно вызывается из `__aexit__`."""

    @abc.abstractmethod
    async def rollback(self) -> None:
        """Явный rollback."""
