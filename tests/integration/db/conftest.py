"""Фикстуры integration-тестов БД-адаптеров.

Используется in-memory SQLite (через aiosqlite) с применением тех же
ORM-моделей (`Base.metadata`). Production будет на Postgres/asyncpg —
DDL покрывается портабельным подмножеством типов (см.
`infrastructure/db/models/security.py`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy import insert
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
    BossFightORM,
    BossParticipantORM,
    ClanMemberORM,
    ClanORM,
    DailyActiveORM,
    DailyHeadAssignmentORM,
    DungeonRunORM,
    ForestRunORM,
    IdempotencyKeyORM,
    ItemORM,
    MountainRunORM,
    OracleInvocationORM,
    PaymentORM,
    PrizePoolBalanceORM,
    PvpDuelORM,
    PvpDuelRoundORM,
    PvpGlobalLobbyORM,
    PvpMassDuelChoiceORM,
    PvpMassDuelDamageEntryORM,
    PvpMassDuelORM,
    ReferralORM,
    RouletteSpinORM,
    ScrollORM,
    SignupQueueORM,
    UserORM,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

_PRIZE_POOL_SEED_AT = datetime(2026, 5, 10, 0, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Спринт 4.1-B / B.3 — `prize_pool_balance` инициализируется
        # initial-seed-ом в Alembic-миграции `0027`. `Base.metadata.create_all`
        # этого seed-а не делает, поэтому вручную дублируем 3-row-seed
        # для integration-тестов, опирающихся на инвариант «всегда 3 строки
        # с balance=0 на момент start-а теста».
        await conn.execute(
            insert(PrizePoolBalanceORM),
            [
                {
                    "currency": currency,
                    "balance_native": 0,
                    "updated_at": _PRIZE_POOL_SEED_AT,
                }
                for currency in ("stars", "ton_nano", "usdt_decimal")
            ],
        )
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
