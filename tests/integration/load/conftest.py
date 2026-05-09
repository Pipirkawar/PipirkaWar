"""Фикстуры для нагрузочных тестов (Спринт 1.4.D / ПД 1.4.7).

Отдельный движок и `session_maker`, которые **намеренно** не делят
сессию между задачами (`asyncio.gather`). Каждая корутина получает
собственный `SqlAlchemyUnitOfWork` от того же `session_maker` — это
имитирует прод-кейс: 100 игроков жмут `/forest` одновременно, бот
обрабатывает их параллельно.

Используем **файловый** SQLite (`tmp_path`-фикстура), чтобы у каждой
сессии было собственное соединение со своей транзакцией. In-memory
`:memory:` через `StaticPool` дал бы одну общую транзакцию на все
сессии — это бы маскировало логические race-ошибки.

Под нагрузкой SQLite сериализует пишущие транзакции через файловый
лок; aiosqlite ретраит при `SQLITE_BUSY` сам, поэтому увеличиваем
`timeout`.

`poolclass=NullPool` — в нагрузочных тестах 100 параллельных корутин
конкурируют за connection, а дефолтный `AsyncAdaptedQueuePool`
(`pool_size=5 + max_overflow=10 = 15` connections) на медленных
CI-раннерах выдаёт `QueuePool limit reached, connection timed out`
раньше, чем aiosqlite успевает обработать BUSY-lock-ретраи. NullPool
выдаёт по одному соединению на каждую сессию (без shared pool) —
SQLite-уровневый file lock + aiosqlite-`timeout=30s` остаётся
единственным узким местом, что и есть «честный» сценарий нагрузки.
Это стандартная SQLAlchemy-рекомендация для async + concurrent
тестов, не меняет семантику теста («100 truly parallel corutines»).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from pipirik_wars.infrastructure.db.base import Base
from pipirik_wars.infrastructure.db.models import (  # noqa: F401  (регистрация моделей)
    ActivityLockORM,
    AdminORM,
    AuditLogORM,
    ClanMemberORM,
    ClanORM,
    ForestRunORM,
    IdempotencyKeyORM,
    OracleInvocationORM,
    SignupQueueORM,
    UserORM,
)


@pytest_asyncio.fixture
async def shared_engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """Файловая SQLite-БД на время теста; каждая сессия — своё соединение."""
    db_path = tmp_path / "load.db"
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
        connect_args={"timeout": 30.0},
        poolclass=NullPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def shared_session_maker(
    shared_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=shared_engine,
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )
