"""Тестовые fake-реализации портов.

Не «mocks» с runtime-настройкой методов, а полноценные in-memory
объекты с предсказуемым поведением. Это намеренно — мокирование
поведения через MagicMock делает тесты хрупкими и плохо ловит
рефакторинг интерфейсов.
"""

from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.anticheat_admin_alerter import (
    AnticheatAdminAlertEvent,
    FakeAnticheatAdminAlerter,
)
from tests.fakes.anticheat_repo import FakeAnticheatRepository
from tests.fakes.audit import FakeAuditLogger
from tests.fakes.balance import FakeBalanceConfig
from tests.fakes.clan_history import FakeClanMassDuelHistoryQuery
from tests.fakes.clan_repo import FakeClanMembershipRepository, FakeClanRepository
from tests.fakes.clock import FakeClock
from tests.fakes.dau import (
    DauAlertEvent,
    FakeDauCounter,
    FakeDauLimit,
    FakeDauThresholdAlerter,
)
from tests.fakes.delayed_job_scheduler import (
    FakeDelayedJobScheduler,
    ScheduledFinish,
    ScheduledLobbyJob,
    ScheduledRoundAfkJob,
)
from tests.fakes.duel_log_templates import FakeDuelLogTemplateProvider
from tests.fakes.duel_repo import FakeDuelRepository
from tests.fakes.forest_run_repo import FakeForestRunRepository
from tests.fakes.global_lobby_repo import FakeGlobalLobbyRepository
from tests.fakes.idempotency import FakeIdempotencyKey
from tests.fakes.lock_repo import FakeActivityLockRepository
from tests.fakes.mass_duel_repo import FakeMassDuelRepository
from tests.fakes.message_bundle import FakeMessageBundle
from tests.fakes.oracle import (
    FakeOracleHistoryRepository,
    FakeOracleTemplateProvider,
)
from tests.fakes.player_locale_resolver import FakePlayerLocaleResolver
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.random import FakeRandom
from tests.fakes.signup_queue import FakeSignupQueueRepository
from tests.fakes.top_clans import FakeClanTopQuery
from tests.fakes.top_players import FakeTopPlayersQuery
from tests.fakes.uow import FakeUnitOfWork

__all__ = [
    "AnticheatAdminAlertEvent",
    "DauAlertEvent",
    "FakeActivityLockRepository",
    "FakeAdminRepository",
    "FakeAnticheatAdminAlerter",
    "FakeAnticheatRepository",
    "FakeAuditLogger",
    "FakeBalanceConfig",
    "FakeClanMassDuelHistoryQuery",
    "FakeClanMembershipRepository",
    "FakeClanRepository",
    "FakeClanTopQuery",
    "FakeClock",
    "FakeDauCounter",
    "FakeDauLimit",
    "FakeDauThresholdAlerter",
    "FakeDelayedJobScheduler",
    "FakeDuelLogTemplateProvider",
    "FakeDuelRepository",
    "FakeForestRunRepository",
    "FakeGlobalLobbyRepository",
    "FakeIdempotencyKey",
    "FakeMassDuelRepository",
    "FakeMessageBundle",
    "FakeOracleHistoryRepository",
    "FakeOracleTemplateProvider",
    "FakePlayerLocaleResolver",
    "FakePlayerRepository",
    "FakeRandom",
    "FakeSignupQueueRepository",
    "FakeTopPlayersQuery",
    "FakeUnitOfWork",
    "ScheduledFinish",
    "ScheduledLobbyJob",
    "ScheduledRoundAfkJob",
]
