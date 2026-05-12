"""Реализация ``IPayoutFreezeRepository`` поверх ``payout_freeze`` (Спринт 4.1-E, E.11a).

Контракт порта — см. ``pipirik_wars.domain.monetization.ports.
IPayoutFreezeRepository``. Singleton-таблица ``payout_freeze``: одна
строка с ``id = 1`` (CHECK ``id = 1`` гарантирует уникальность). Seed
``(id=1, is_frozen=FALSE)`` создаётся в Alembic-миграции ``0037``,
поэтому ``get_state()`` никогда не возвращает ``None`` после
``alembic upgrade head``.

Подходы:

* ``get_state()`` — ``SELECT * FROM payout_freeze WHERE id=1``. Если
  строка отсутствует (например, integration-тест применил
  ``Base.metadata.create_all`` без seed-INSERT-а) — fallback на
  ``PayoutFreeze.unfrozen()``-default, чтобы caller не получил
  ``None``-сюрприза.
* ``set_frozen(*, admin_id, at, reason)`` — ``UPDATE payout_freeze
  SET is_frozen=TRUE, frozen_by_admin_id=:admin, frozen_at=:at,
  reason=:reason WHERE id=1``. Идемпотентно: повторный вызов с
  теми же параметрами просто перезапишет одно и то же.
* ``set_unfrozen()`` — ``UPDATE payout_freeze SET is_frozen=FALSE,
  frozen_by_admin_id=NULL, frozen_at=NULL, reason=NULL WHERE id=1``.

CHECK-инварианты миграции ``0037`` — last-line-of-defense; доменные
invariants ``PayoutFreeze.__post_init__`` сторожат то же самое ещё до
записи (``set_frozen``/``set_unfrozen`` строят ``PayoutFreeze``-VO до
UPDATE-а через фабрики ``PayoutFreeze.frozen(...)`` / ``unfrozen()``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update

from pipirik_wars.domain.monetization.entities import PayoutFreeze
from pipirik_wars.domain.monetization.ports import IPayoutFreezeRepository
from pipirik_wars.infrastructure.db.models import PayoutFreezeORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

_SINGLETON_ID: int = 1


class SqlAlchemyPayoutFreezeRepository(IPayoutFreezeRepository):
    """SQLAlchemy-реализация ``IPayoutFreezeRepository`` поверх singleton-таблицы."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        """DI-конструктор.

        Args:
            uow: Unit-of-Work, поверх которого репозиторий работает.
                Caller обязан открыть ``async with uow:`` перед вызовами.
        """
        self._uow = uow

    async def get_state(self) -> PayoutFreeze:
        """Получить текущее состояние freeze-флага.

        После ``alembic upgrade head`` seed-row ``(id=1, is_frozen=FALSE)``
        гарантированно существует. Если же caller использует
        ``Base.metadata.create_all`` без seed-а (integration-тесты до
        seed-фикстуры) — fallback на ``PayoutFreeze.unfrozen()``.
        """
        session = self._uow.session
        stmt = select(PayoutFreezeORM).where(PayoutFreezeORM.id == _SINGLETON_ID)
        result = await session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return PayoutFreeze.unfrozen()
        return _orm_to_domain(orm)

    async def set_frozen(
        self,
        *,
        admin_id: int,
        at: datetime,
        reason: str,
    ) -> PayoutFreeze:
        """Переключить состояние в ``is_frozen=True``."""
        # Доменный фабричный метод валидирует атрибуты до SQL UPDATE-а
        # (admin_id > 0 / at TZ-aware / reason non-empty).
        new_state = PayoutFreeze.frozen(
            admin_id=admin_id,
            at=at,
            reason=reason,
        )
        session = self._uow.session
        stmt = (
            update(PayoutFreezeORM)
            .where(PayoutFreezeORM.id == _SINGLETON_ID)
            .values(
                is_frozen=True,
                frozen_by_admin_id=new_state.frozen_by_admin_id,
                frozen_at=new_state.frozen_at,
                reason=new_state.reason,
            )
        )
        await session.execute(stmt)
        return new_state

    async def set_unfrozen(self) -> PayoutFreeze:
        """Переключить состояние в ``is_frozen=False`` со сбросом всех атрибутов."""
        session = self._uow.session
        stmt = (
            update(PayoutFreezeORM)
            .where(PayoutFreezeORM.id == _SINGLETON_ID)
            .values(
                is_frozen=False,
                frozen_by_admin_id=None,
                frozen_at=None,
                reason=None,
            )
        )
        await session.execute(stmt)
        return PayoutFreeze.unfrozen()


def _orm_to_domain(orm: PayoutFreezeORM) -> PayoutFreeze:
    """Собрать ``PayoutFreeze``-VO из ORM-строки.

    SQLAlchemy + aiosqlite возвращает naïve-datetime для
    ``DateTime(timezone=True)``-колонок. Доменный VO ``PayoutFreeze``
    отказывает naïve-datetime в frozen-состоянии, поэтому нормализуем
    naïve как UTC. На запись use-case всегда передаёт UTC-моменты.
    """
    if orm.is_frozen:
        assert orm.frozen_by_admin_id is not None
        assert orm.frozen_at is not None
        assert orm.reason is not None
        return PayoutFreeze.frozen(
            admin_id=orm.frozen_by_admin_id,
            at=_ensure_utc(orm.frozen_at),
            reason=orm.reason,
        )
    return PayoutFreeze.unfrozen()


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
