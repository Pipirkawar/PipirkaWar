"""Фикстуры integration-тестов БД-адаптеров.

Используется in-memory SQLite (через aiosqlite) с применением тех же
ORM-моделей (`Base.metadata`). Production будет на Postgres/asyncpg —
DDL покрывается портабельным подмножеством типов (см.
`infrastructure/db/models/security.py`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pipirik_wars.infrastructure.db.base import Base
from pipirik_wars.infrastructure.db.models import (  # noqa: F401  (регистрация моделей)
    ActivityLockORM,
    AdminAuditLogORM,
    AdminORM,
    AuditLogORM,
    ClanMemberORM,
    ClanORM,
    DailyActiveORM,
    DailyHeadAssignmentORM,
    ForestRunORM,
    IdempotencyKeyORM,
    OracleInvocationORM,
    PvpDuelORM,
    PvpDuelRoundORM,
    PvpGlobalLobbyORM,
    PvpMassDuelChoiceORM,
    PvpMassDuelDamageEntryORM,
    PvpMassDuelORM,
    ReferralORM,
    SignupQueueORM,
    UserORM,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_maker(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )


@pytest_asyncio.fixture
async def uow(
    session_maker: async_sessionmaker[AsyncSession],
) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session_maker)
