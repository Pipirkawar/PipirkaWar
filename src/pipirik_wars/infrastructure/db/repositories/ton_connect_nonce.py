"""Реализация ``INonceStore`` поверх таблицы ``ton_connect_nonces`` (Спринт 4.1-F, F.6.b).

Контракт порта — см. ``pipirik_wars.domain.monetization.ports.INonceStore``.

Производственный server-side nonce-store для TON Connect 2.0 verify-
flow-а: persistent (переживает рестарты), atomic-CAS-consume (защита от
race-condition при одновременных phase-2-attempt-ах одного и того же
nonce-а).

Подходы:

* ``issue_nonce(*, scope, nonce, expires_at)`` — INSERT новой строки
  с ``issued_at = clock.now()``, ``consumed_at = NULL``. На повторный
  INSERT того же ``nonce`` (PK-конфликт) — поднимаем ``ValueError``
  (контракт ``INonceStore``: вызывающий use-case обязан генерировать
  уникальные nonce-ы; повтор — bug-сигнал, не штатный путь).
* ``consume_nonce(*, scope, nonce, now)`` — атомарный
  ``UPDATE ... WHERE consumed_at IS NULL AND expires_at > :now
  RETURNING 1``-pattern, реализованный через SQLAlchemy ``update(...).
  where(...)`` и проверку ``result.rowcount > 0``. Однопроходный
  UPDATE-statement даёт CAS-семантику: два параллельных вызова
  с одним и тем же ``(scope, nonce)`` гарантированно вернут один
  ``True`` и один ``False`` (Postgres-уровень RC-изоляции + row-lock
  на UPDATE; SQLite — single-writer-семантика гарантирует
  сериализуемость).

DI-инварианты:

* ``uow: SqlAlchemyUnitOfWork`` — caller обязан открыть ``async with
  uow:`` перед вызовами (контракт всех ``SqlAlchemy*Repository``).
* ``clock: IClock`` — источник ``issued_at``-времени (порт
  ``INonceStore`` не передаёт ``issued_at`` в ``issue_nonce``; чтобы
  не звать ``datetime.now()`` напрямую и сохранить тестируемость,
  инжектируем ``IClock`` как в ``SqlAlchemyDailyActivityRepository``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CursorResult, update
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.monetization.ports import INonceStore
from pipirik_wars.domain.shared.ports import IClock
from pipirik_wars.infrastructure.db.models import TonConnectNonceORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class SqlAlchemyNonceStore(INonceStore):
    """SQLAlchemy-реализация ``INonceStore`` поверх ``ton_connect_nonces``."""

    __slots__ = ("_clock", "_uow")

    def __init__(self, *, uow: SqlAlchemyUnitOfWork, clock: IClock) -> None:
        """DI-конструктор.

        Args:
            uow: Unit-of-Work, поверх которого репозиторий работает.
                Caller обязан открыть ``async with uow:`` перед вызовами.
            clock: Источник ``issued_at``-времени.
        """
        self._uow = uow
        self._clock = clock

    async def issue_nonce(
        self,
        *,
        scope: str,
        nonce: str,
        expires_at: datetime,
    ) -> None:
        """См. ``INonceStore.issue_nonce``.

        Записывает строку ``(nonce, scope, issued_at=clock.now(),
        consumed_at=NULL, expires_at)``. На повторный INSERT того же
        ``nonce`` поднимает ``ValueError`` (PK-конфликт через
        ``IntegrityError`` → wrapped в ``ValueError`` с контекстом).
        """
        session = self._uow.session
        issued_at = self._clock.now()
        orm = TonConnectNonceORM(
            nonce=nonce,
            scope=scope,
            issued_at=issued_at,
            consumed_at=None,
            expires_at=expires_at,
        )
        session.add(orm)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError(
                f"SqlAlchemyNonceStore: nonce already issued for scope={scope!r} "
                "(use-case must generate unique nonces)",
            ) from exc

    async def consume_nonce(
        self,
        *,
        scope: str,
        nonce: str,
        now: datetime,
    ) -> bool:
        """См. ``INonceStore.consume_nonce``.

        Атомарный CAS через ``UPDATE ... WHERE consumed_at IS NULL AND
        expires_at > :now``: SQLAlchemy сгенерирует один UPDATE-statement,
        который сервер БД исполнит атомарно (Postgres row-lock; SQLite
        single-writer). ``rowcount > 0`` ⇔ строка прошла CAS-условие
        и теперь помечена ``consumed_at = :now``.
        """
        session = self._uow.session
        stmt = (
            update(TonConnectNonceORM)
            .where(
                TonConnectNonceORM.nonce == nonce,
                TonConnectNonceORM.scope == scope,
                TonConnectNonceORM.consumed_at.is_(None),
                TonConnectNonceORM.expires_at > now,
            )
            .values(consumed_at=now)
        )
        result = await session.execute(stmt)
        # ``UPDATE``-statement через ``session.execute(...)`` всегда возвращает
        # ``CursorResult`` (для DML-операций SQLAlchemy конкретизирует
        # generic-``Result``-протокол), но mypy --strict не сужает тип сам;
        # явное приведение нужно, чтобы достучаться до ``.rowcount``.
        assert isinstance(result, CursorResult)
        return result.rowcount > 0
