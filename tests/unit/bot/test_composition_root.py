"""Тесты composition root.

Проверяем структуру `Container` (иммутабельный DTO с портами + Settings),
что `build_container()` собирает реальные адаптеры, и что
`build_dispatcher()` собирает aiogram-объект со стеком middleware-ов.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest
from aiogram import Dispatcher
from pydantic import SecretStr

from pipirik_wars.application.clan import (
    FreezeClan,
    JoinClan,
    MigrateClanChatId,
    RegisterClan,
)
from pipirik_wars.application.player import RegisterPlayer
from pipirik_wars.bot.main import Container, build_container, build_dispatcher
from pipirik_wars.domain.clan import IClanMembershipRepository, IClanRepository
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.infrastructure.balance import YamlBalanceLoader
from pipirik_wars.infrastructure.clock import RealClock
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.services import (
    SqlAlchemyAuditLogger,
    SqlAlchemyIdempotencyService,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.random import RealRandom
from pipirik_wars.infrastructure.rate_limit import (
    InMemoryTokenBucketRateLimiter,
    IRateLimiter,
)
from pipirik_wars.infrastructure.settings import (
    BootstrapSettings,
    BotSettings,
    DatabaseSettings,
    Settings,
)
from tests.fakes import (
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClanMembershipRepository,
    FakeClanRepository,
    FakeClock,
    FakeIdempotencyKey,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance


def _test_settings() -> Settings:
    return Settings(
        environment="test",
        db=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")),
        bot=BotSettings(token=SecretStr("test-token")),
        bootstrap=BootstrapSettings(),
    )


def _fake_limiter() -> IRateLimiter:
    return cast(IRateLimiter, MagicMock(spec=IRateLimiter))


def _container_with_fakes() -> Container:
    """Полный фейковый Container для unit-тестов composition-root-а."""
    uow = FakeUnitOfWork()
    audit = FakeAuditLogger()
    clock = FakeClock()
    players: IPlayerRepository = FakePlayerRepository()
    clans: IClanRepository = FakeClanRepository()
    members: IClanMembershipRepository = FakeClanMembershipRepository()
    return Container(
        clock=clock,
        random=FakeRandom(),
        uow=uow,
        idempotency=FakeIdempotencyKey(),
        audit=audit,
        balance=FakeBalanceConfig(build_valid_balance()),
        rate_limiter=_fake_limiter(),
        settings=_test_settings(),
        players=players,
        clans=clans,
        clan_members=members,
        register_player=RegisterPlayer(
            uow=uow,
            players=players,
            audit=audit,
            clock=clock,
        ),
        register_clan=RegisterClan(
            uow=uow,
            clans=clans,
            audit=audit,
            clock=clock,
        ),
        migrate_clan=MigrateClanChatId(
            uow=uow,
            clans=clans,
            audit=audit,
            clock=clock,
        ),
        join_clan=JoinClan(
            uow=uow,
            clans=clans,
            clan_members=members,
            players=players,
            audit=audit,
            clock=clock,
        ),
        freeze_clan=FreezeClan(
            uow=uow,
            clans=clans,
            audit=audit,
            clock=clock,
        ),
    )


class TestContainer:
    def test_container_holds_all_ports(self) -> None:
        c = _container_with_fakes()
        assert isinstance(c.clock, FakeClock)
        assert isinstance(c.random, FakeRandom)
        assert isinstance(c.uow, FakeUnitOfWork)
        assert isinstance(c.idempotency, FakeIdempotencyKey)
        assert isinstance(c.audit, FakeAuditLogger)
        assert isinstance(c.balance, FakeBalanceConfig)
        assert c.rate_limiter is not None
        assert c.settings.environment == "test"
        # Use-case-ы и репозитории (Спринт 1.1.D).
        assert isinstance(c.register_player, RegisterPlayer)
        assert isinstance(c.register_clan, RegisterClan)
        assert isinstance(c.migrate_clan, MigrateClanChatId)
        assert isinstance(c.join_clan, JoinClan)
        assert isinstance(c.freeze_clan, FreezeClan)

    def test_container_is_frozen(self) -> None:
        c = _container_with_fakes()
        with pytest.raises((AttributeError, TypeError)):
            c.clock = FakeClock()


class TestBuildContainer:
    def test_build_container_returns_real_adapters(self) -> None:
        c = build_container(settings=_test_settings())
        assert isinstance(c.clock, RealClock)
        assert isinstance(c.random, RealRandom)
        assert isinstance(c.uow, SqlAlchemyUnitOfWork)
        assert isinstance(c.idempotency, SqlAlchemyIdempotencyService)
        assert isinstance(c.audit, SqlAlchemyAuditLogger)
        assert isinstance(c.balance, YamlBalanceLoader)
        assert isinstance(c.rate_limiter, InMemoryTokenBucketRateLimiter)
        assert c.settings.environment == "test"
        # Реальные SQLAlchemy-репозитории (Спринт 1.1.D).
        assert isinstance(c.players, SqlAlchemyPlayerRepository)
        assert isinstance(c.clans, SqlAlchemyClanRepository)
        assert isinstance(c.clan_members, SqlAlchemyClanMembershipRepository)


class TestBuildDispatcher:
    """Один тест — один build_dispatcher.

    aiogram-роутеры — singleton-ы на уровне модуля; при повторном
    вызове `dispatcher.include_router(...)` они бросают
    `RuntimeError: Router is already attached`. Поэтому проверяем
    структуру через **один** общий test, а не дробим.
    """

    def test_build_dispatcher_assembles_full_stack(self) -> None:
        c = _container_with_fakes()
        dp = build_dispatcher(c)
        assert isinstance(dp, Dispatcher)
        # Каждый из observer-ов должен иметь 4 middleware-а:
        # error / auth / locale / throttle.
        for observer in (dp.message, dp.callback_query, dp.my_chat_member):
            assert len(list(observer.middleware)) == 4
        # Минимум 2 router-а: `start` и `registration`.
        assert any(r.name == "start" for r in dp.sub_routers)
        assert any(r.name == "registration" for r in dp.sub_routers)
        # Use-case-ы прокинуты в workflow-data для aiogram DI.
        assert dp["register_player"] is c.register_player
        assert dp["register_clan"] is c.register_clan
        assert dp["migrate_clan"] is c.migrate_clan
        assert dp["join_clan"] is c.join_clan
        assert dp["freeze_clan"] is c.freeze_clan
