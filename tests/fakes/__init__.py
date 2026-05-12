"""Тестовые fake-реализации портов.

Не «mocks» с runtime-настройкой методов, а полноценные in-memory
объекты с предсказуемым поведением. Это намеренно — мокирование
поведения через MagicMock делает тесты хрупкими и плохо ловит
рефакторинг интерфейсов.
"""

from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_audit_query import FakeAdminAuditQuery
from tests.fakes.admin_authz import (
    FakeAdminAuthzAllowAll,
    FakeAdminAuthzDenyAll,
    FakeAdminAuthzMatrix,
)
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.anticheat_admin_alerter import (
    AnticheatAdminAlertEvent,
    FakeAnticheatAdminAlerter,
)
from tests.fakes.anticheat_repo import FakeAnticheatRepository
from tests.fakes.audit import FakeAuditLogger
from tests.fakes.balance import FakeBalanceConfig
from tests.fakes.boss_fight_repo import (
    FakeBossFightRepository,
    FakeBossParticipantRepository,
)
from tests.fakes.broadcast import (
    FakeBroadcastSender,
    InlineBroadcastTaskSpawner,
    TaskGroupBroadcastTaskSpawner,
)
from tests.fakes.caravan_repo import (
    FakeCaravanParticipantRepository,
    FakeCaravanRepository,
)
from tests.fakes.clan_history import FakeClanMassDuelHistoryQuery
from tests.fakes.clan_quotes import FakeClanQuoteTemplateProvider
from tests.fakes.clan_repo import FakeClanMembershipRepository, FakeClanRepository
from tests.fakes.clock import FakeClock
from tests.fakes.daily_head import (
    FakeDailyActivityRepository,
    FakeDailyHeadRepository,
)
from tests.fakes.dau import (
    DauAlertEvent,
    FakeDauCounter,
    FakeDauLimit,
    FakeDauThresholdAlerter,
)
from tests.fakes.delayed_job_scheduler import (
    FakeDelayedJobScheduler,
    ScheduledCaravanLobbyCloseJob,
    ScheduledFinish,
    ScheduledLobbyJob,
    ScheduledRoundAfkJob,
)
from tests.fakes.duel_log_templates import FakeDuelLogTemplateProvider
from tests.fakes.duel_repo import FakeDuelRepository
from tests.fakes.dungeon_run_repo import FakeDungeonRunRepository
from tests.fakes.fee_estimator import FakeFeeEstimator
from tests.fakes.forest_run_repo import FakeForestRunRepository
from tests.fakes.global_lobby_repo import FakeGlobalLobbyRepository
from tests.fakes.idempotency import FakeIdempotencyKey
from tests.fakes.lock_repo import FakeActivityLockRepository
from tests.fakes.mass_duel_repo import FakeMassDuelRepository
from tests.fakes.message_bundle import FakeMessageBundle
from tests.fakes.mountain_run_repo import FakeMountainRunRepository
from tests.fakes.oracle import (
    FakeOracleHistoryRepository,
    FakeOracleTemplateProvider,
)
from tests.fakes.payment_ledger import FakePaymentLedger
from tests.fakes.payout_freeze_repo import FakePayoutFreezeRepository
from tests.fakes.payout_limit_checker import FakePayoutLimitChecker
from tests.fakes.player_locale_resolver import FakePlayerLocaleResolver
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.prize_lot_repo import FakePrizeLotRepository
from tests.fakes.prize_pool_repo import (
    FakePrizePoolApplyIncrementCall,
    FakePrizePoolRepository,
)
from tests.fakes.random import FakeRandom
from tests.fakes.referral import FakeReferralRepository
from tests.fakes.roulette_spin_repo import FakeRouletteSpinRepository
from tests.fakes.signup_queue import FakeSignupQueueRepository
from tests.fakes.tg_stars_verifier import FakeTgStarsPayloadVerifier
from tests.fakes.top_clans import FakeClanTopQuery
from tests.fakes.top_players import FakeTopPlayersQuery
from tests.fakes.totp_verifier import FakeTotpVerifier
from tests.fakes.uow import FakeUnitOfWork

__all__ = [
    "AnticheatAdminAlertEvent",
    "DauAlertEvent",
    "FakeActivityLockRepository",
    "FakeAdminAuditLogger",
    "FakeAdminAuditQuery",
    "FakeAdminAuthzAllowAll",
    "FakeAdminAuthzDenyAll",
    "FakeAdminAuthzMatrix",
    "FakeAdminRepository",
    "FakeAnticheatAdminAlerter",
    "FakeAnticheatRepository",
    "FakeAuditLogger",
    "FakeBalanceConfig",
    "FakeBossFightRepository",
    "FakeBossParticipantRepository",
    "FakeBroadcastSender",
    "FakeCaravanParticipantRepository",
    "FakeCaravanRepository",
    "FakeClanMassDuelHistoryQuery",
    "FakeClanMembershipRepository",
    "FakeClanQuoteTemplateProvider",
    "FakeClanRepository",
    "FakeClanTopQuery",
    "FakeClock",
    "FakeDailyActivityRepository",
    "FakeDailyHeadRepository",
    "FakeDauCounter",
    "FakeDauLimit",
    "FakeDauThresholdAlerter",
    "FakeDelayedJobScheduler",
    "FakeDuelLogTemplateProvider",
    "FakeDuelRepository",
    "FakeDungeonRunRepository",
    "FakeFeeEstimator",
    "FakeForestRunRepository",
    "FakeGlobalLobbyRepository",
    "FakeIdempotencyKey",
    "FakeMassDuelRepository",
    "FakeMessageBundle",
    "FakeMountainRunRepository",
    "FakeOracleHistoryRepository",
    "FakeOracleTemplateProvider",
    "FakePaymentLedger",
    "FakePayoutFreezeRepository",
    "FakePayoutLimitChecker",
    "FakePlayerLocaleResolver",
    "FakePlayerRepository",
    "FakePrizeLotRepository",
    "FakePrizePoolApplyIncrementCall",
    "FakePrizePoolRepository",
    "FakeRandom",
    "FakeReferralRepository",
    "FakeRouletteSpinRepository",
    "FakeSignupQueueRepository",
    "FakeTgStarsPayloadVerifier",
    "FakeTopPlayersQuery",
    "FakeTotpVerifier",
    "FakeUnitOfWork",
    "InlineBroadcastTaskSpawner",
    "ScheduledCaravanLobbyCloseJob",
    "ScheduledFinish",
    "ScheduledLobbyJob",
    "ScheduledRoundAfkJob",
    "TaskGroupBroadcastTaskSpawner",
]
