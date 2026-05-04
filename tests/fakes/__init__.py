"""Тестовые fake-реализации портов.

Не «mocks» с runtime-настройкой методов, а полноценные in-memory
объекты с предсказуемым поведением. Это намеренно — мокирование
поведения через MagicMock делает тесты хрупкими и плохо ловит
рефакторинг интерфейсов.
"""

from tests.fakes.audit import FakeAuditLogger
from tests.fakes.balance import FakeBalanceConfig
from tests.fakes.clan_repo import FakeClanMembershipRepository, FakeClanRepository
from tests.fakes.clock import FakeClock
from tests.fakes.idempotency import FakeIdempotencyKey
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.random import FakeRandom
from tests.fakes.uow import FakeUnitOfWork

__all__ = [
    "FakeAuditLogger",
    "FakeBalanceConfig",
    "FakeClanMembershipRepository",
    "FakeClanRepository",
    "FakeClock",
    "FakeIdempotencyKey",
    "FakePlayerRepository",
    "FakeRandom",
    "FakeUnitOfWork",
]
