"""Репозиторий админ-аккаунтов (порт)."""

from __future__ import annotations

import abc

from pipirik_wars.domain.admin.entities import Admin, AdminRole


class IAdminRepository(abc.ABC):
    """Доступ к таблице `admins`.

    Все методы исполняются внутри контекста `IUnitOfWork` — отдельная
    транзакция не открывается.
    """

    @abc.abstractmethod
    async def count_active(self) -> int:
        """Сколько активных админов в системе. Используется bootstrap-логикой."""

    @abc.abstractmethod
    async def get_by_tg_id(self, tg_id: int) -> Admin | None:
        """Найти админа по Telegram-ID или вернуть `None`."""

    @abc.abstractmethod
    async def add(
        self,
        *,
        tg_id: int,
        role: AdminRole,
        created_by_admin_id: int | None,
        note: str | None,
    ) -> Admin:
        """Добавить админа. Возвращает только что созданную сущность с заполненным `id`.

        Поднимает `ConcurrencyError`, если `tg_id` уже существует.
        """
