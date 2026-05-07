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

    @abc.abstractmethod
    async def set_totp_secret(self, *, admin_id: int, secret: str) -> None:
        """Записать `totp_secret` для существующего админа.

        Используется use-case-ом `SetupAdminTotp` (Спринт 2.5-D.6, ГДД §18.6.5)
        для self-service-выдачи нового TOTP-секрета. Перезатирает текущее
        значение `admins.totp_secret` без проверки, был ли там уже секрет;
        проверка «уже настроено» делается на слое use-case-а
        (`TotpAlreadyConfiguredError`) — репо здесь намеренно «глуп», чтобы
        в тестах можно было задать любое исходное состояние.

        `secret` ожидается уже сгенерированным `ITotpSecretGenerator` —
        BASE32-строка. Репо не валидирует формат: это инвариант домена,
        не БД. Единственный SQL — `UPDATE admins SET totp_secret = :secret
        WHERE id = :admin_id`.

        Поднимает `ConcurrencyError`, если строка с таким `id` не найдена
        (по аналогии с другими репо: пишем 0 строк → конкурентное
        удаление/ротация → откат UoW + явная ошибка).
        """
