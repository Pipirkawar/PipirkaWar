"""Тесты composition root.

Проверяем структуру `Container` (иммутабельный DTO с портами + Settings)
и что `build_container()` собирает реальные адаптеры. `main()` пока
NotImplementedError — entry point появится в Спринте 1.1.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from pipirik_wars.bot.main import Container, build_container, main
from pipirik_wars.infrastructure.balance import YamlBalanceLoader
from pipirik_wars.infrastructure.clock import RealClock
from pipirik_wars.infrastructure.db.services import (
    SqlAlchemyAuditLogger,
    SqlAlchemyIdempotencyService,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.random import RealRandom
from pipirik_wars.infrastructure.settings import (
    BootstrapSettings,
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
        bootstrap=BootstrapSettings(),
    )


class TestContainer:
    def test_container_holds_all_ports(self) -> None:
        c = Container(
            clock=FakeClock(),
            random=FakeRandom(),
            uow=FakeUnitOfWork(),
            idempotency=FakeIdempotencyKey(),
            audit=FakeAuditLogger(),
            balance=FakeBalanceConfig(build_valid_balance()),
            settings=_test_settings(),
        )
        assert isinstance(c.clock, FakeClock)
        assert isinstance(c.random, FakeRandom)
        assert isinstance(c.uow, FakeUnitOfWork)
        assert isinstance(c.idempotency, FakeIdempotencyKey)
        assert isinstance(c.audit, FakeAuditLogger)
        assert isinstance(c.balance, FakeBalanceConfig)
        assert c.settings.environment == "test"

    def test_container_is_frozen(self) -> None:
        c = Container(
            clock=FakeClock(),
            random=FakeRandom(),
            uow=FakeUnitOfWork(),
            idempotency=FakeIdempotencyKey(),
            audit=FakeAuditLogger(),
            balance=FakeBalanceConfig(build_valid_balance()),
            settings=_test_settings(),
        )
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
        assert c.settings.environment == "test"


class TestEntryPoints:
    def test_main_not_implemented_yet(self) -> None:
        with pytest.raises(NotImplementedError, match="1\\.1"):
            main()
