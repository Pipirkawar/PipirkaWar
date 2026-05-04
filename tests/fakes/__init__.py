"""Тестовые fake-реализации портов.

Не «mocks» с runtime-настройкой методов, а полноценные in-memory
объекты с предсказуемым поведением. Это намеренно — мокирование
поведения через MagicMock делает тесты хрупкими и плохо ловит
рефакторинг интерфейсов.
"""

from tests.fakes.audit import FakeAuditLogger
from tests.fakes.clock import FakeClock
from tests.fakes.idempotency import FakeIdempotencyKey
from tests.fakes.random import FakeRandom
from tests.fakes.uow import FakeUnitOfWork

__all__ = [
    "FakeAuditLogger",
    "FakeClock",
    "FakeIdempotencyKey",
    "FakeRandom",
    "FakeUnitOfWork",
]
