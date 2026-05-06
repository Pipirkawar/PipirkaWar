"""Реализация `IAdminAuditLogger` поверх таблицы `admin_audit_log`."""

from __future__ import annotations

from pipirik_wars.domain.admin import AdminAuditEntry, IAdminAuditLogger
from pipirik_wars.infrastructure.db.models import AdminAuditLogORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyAdminAuditLogger(IAdminAuditLogger):
    """Пишет admin-audit-запись в той же транзакции, что и сама мутация.

    Любая ошибка пробрасывается дальше — `IUnitOfWork.__aexit__` сделает
    rollback всей транзакции. ГДД §0: «без аудита операция не считается
    выполненной».
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def record(self, entry: AdminAuditEntry) -> None:
        row = AdminAuditLogORM(
            admin_id=entry.admin_id,
            action=entry.action.value,
            target_kind=entry.target_kind,
            target_id=entry.target_id,
            before=entry.before,
            after=entry.after,
            reason=entry.reason,
            idempotency_key=entry.idempotency_key,
            source=entry.source.value,
            tg_chat_id=entry.tg_chat_id,
            ip=entry.ip,
            occurred_at=entry.occurred_at,
        )
        self._uow.session.add(row)
        await self._uow.session.flush()
