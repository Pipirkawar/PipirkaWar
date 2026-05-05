"""Реализация `IAuditLogger` поверх таблицы `audit_log`."""

from __future__ import annotations

from pipirik_wars.domain.shared.ports import AuditEntry, IAuditLogger
from pipirik_wars.infrastructure.db.models import AuditLogORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyAuditLogger(IAuditLogger):
    """Пишет audit-запись в той же транзакции, что и сама бизнес-операция.

    Бросает любую исходную ошибку дальше — UoW.__aexit__ сделает rollback
    всей транзакции. ГДД §0: «целостность данных» — без аудит-записи
    операция не считается выполненной.
    """

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def record(self, entry: AuditEntry) -> None:
        row = AuditLogORM(
            occurred_at=entry.occurred_at,
            action=entry.action.value,
            actor_id=entry.actor_id,
            target_kind=entry.target_kind,
            target_id=entry.target_id,
            before=entry.before,
            after=entry.after,
            reason=entry.reason,
            idempotency_key=entry.idempotency_key,
            source=entry.source.value,
            clamped_from=entry.clamped_from,
        )
        self._uow.session.add(row)
        await self._uow.session.flush()
