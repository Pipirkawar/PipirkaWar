"""Тесты composition root.

В Спринте 0.1 проверяем только структуру `Container` (иммутабельный
DTO с пятью портами) и что `build_container()/main()` пока бросают
`NotImplementedError` с понятным message.
"""

from __future__ import annotations

import pytest

from pipirik_wars.bot.main import Container, build_container, main
from tests.fakes import (
    FakeAuditLogger,
    FakeClock,
    FakeIdempotencyKey,
    FakeRandom,
    FakeUnitOfWork,
)


class TestContainer:
    def test_container_holds_all_five_ports(self) -> None:
        c = Container(
            clock=FakeClock(),
            random=FakeRandom(),
            uow=FakeUnitOfWork(),
            idempotency=FakeIdempotencyKey(),
            audit=FakeAuditLogger(),
        )
        assert isinstance(c.clock, FakeClock)
        assert isinstance(c.random, FakeRandom)
        assert isinstance(c.uow, FakeUnitOfWork)
        assert isinstance(c.idempotency, FakeIdempotencyKey)
        assert isinstance(c.audit, FakeAuditLogger)

    def test_container_is_frozen(self) -> None:
        c = Container(
            clock=FakeClock(),
            random=FakeRandom(),
            uow=FakeUnitOfWork(),
            idempotency=FakeIdempotencyKey(),
            audit=FakeAuditLogger(),
        )
        with pytest.raises((AttributeError, TypeError)):
            c.clock = FakeClock()


class TestEntryPoints:
    def test_build_container_not_implemented_yet(self) -> None:
        with pytest.raises(NotImplementedError, match="0\\.2"):
            build_container()

    def test_main_not_implemented_yet(self) -> None:
        with pytest.raises(NotImplementedError, match="1\\.1"):
            main()
