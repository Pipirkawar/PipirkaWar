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

from pipirik_wars.bot.main import Container, build_container, build_dispatcher
from pipirik_wars.infrastructure.balance import YamlBalanceLoader
from pipirik_wars.infrastructure.clock import RealClock
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
    FakeClock,
    FakeIdempotencyKey,
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
    return Container(
        clock=FakeClock(),
        random=FakeRandom(),
        uow=FakeUnitOfWork(),
        idempotency=FakeIdempotencyKey(),
        audit=FakeAuditLogger(),
        balance=FakeBalanceConfig(build_valid_balance()),
        rate_limiter=_fake_limiter(),
        settings=_test_settings(),
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


class TestBuildDispatcher:
    def test_build_dispatcher_registers_middlewares_and_routers(self) -> None:
        dp = build_dispatcher(_container_with_fakes())
        assert isinstance(dp, Dispatcher)
        # Каждый из observer-ов должен иметь 4 middleware-а:
        # error / auth / locale / throttle.
        for observer in (dp.message, dp.callback_query, dp.my_chat_member):
            assert len(list(observer.middleware)) == 4
        # Хотя бы один router зарегистрирован — это `start`.
        assert len(dp.sub_routers) >= 1
        assert any(r.name == "start" for r in dp.sub_routers)
