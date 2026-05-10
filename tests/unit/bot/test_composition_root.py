"""Тесты composition root.

Проверяем структуру `Container` (иммутабельный DTO с портами + Settings),
что `build_container()` собирает реальные адаптеры, и что
`build_dispatcher()` собирает aiogram-объект со стеком middleware-ов.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from aiogram import Dispatcher
from pydantic import SecretStr

from pipirik_wars.application.admin import (
    BanPlayer,
    BroadcastAnnouncement,
    FindPlayers,
    FreezeClanAdmin,
    FreezePlayer,
    GetAdminAuditTrail,
    GetBalanceValue,
    GetClanCard,
    GetClanDailyHeadHistory,
    GetPlayerCard,
    GrantLength,
    GrantThickness,
    RequestAdminConfirm,
    RunBroadcastAnnouncement,
    SetBalanceValue,
    SetupAdminTotp,
    UnfreezeClanAdmin,
    UnfreezePlayer,
    VerifyAdminConfirm,
)
from pipirik_wars.application.anticheat import LiftAnticheatBan
from pipirik_wars.application.balance import ReloadBalance
from pipirik_wars.application.bosses import (
    CancelBossFight,
    CloseBossLobby,
    FinishBossFight,
    JoinBossLobby,
    LeaveBossLobby,
    RunBossRound,
    SummonBoss,
)
from pipirik_wars.application.caravans import (
    CancelCaravan,
    CloseCaravanLobby,
    CreateCaravan,
    JoinCaravanLobby,
    LeaveCaravanLobby,
)
from pipirik_wars.application.clan import (
    FreezeClan,
    JoinClan,
    MigrateClanChatId,
    RegisterClan,
)
from pipirik_wars.application.daily_head import (
    RecordPlayerActivity,
    RequestDailyHead,
    RunDailyHeadCron,
    ScheduleDailyHeadCronJobs,
)
from pipirik_wars.application.dau import (
    CheckDauThreshold,
    GetDauStats,
    SetMaxDau,
)
from pipirik_wars.application.dungeon import (
    FinishDungeonRun,
    StartDungeonRun,
)
from pipirik_wars.application.forest import (
    ApplyForestNameDrop,
    FinishForestRun,
    StartForestRun,
)
from pipirik_wars.application.i18n import IMessageBundle
from pipirik_wars.application.inventory import EnchantItem, GetInventory
from pipirik_wars.application.monetization import RecordDonation, SpinPaidRoulette
from pipirik_wars.application.mountains import (
    FinishMountainRun,
    StartMountainRun,
)
from pipirik_wars.application.oracle import InvokeOracle
from pipirik_wars.application.player import (
    GetProfile,
    RegisterPlayer,
    SetPlayerLocale,
)
from pipirik_wars.application.progression import AddLength, UpgradeThickness
from pipirik_wars.application.pvp import (
    AcceptDuel,
    CancelDuel,
    CancelMassDuel,
    ChallengeDuel,
    EnqueueGlobalDuel,
    EscalateChatToGlobal,
    ExpireLobbyEntry,
    ForceResolveMassDuel,
    GetClanAttackHistory,
    MatchFromLobby,
    ResolveAfkRound,
    ResolveMassDuel,
    StartMassDuel,
    SubmitMassMove,
    SubmitMove,
)
from pipirik_wars.application.referral import (
    GrantReferralSignupBonus,
    GrantReferralThicknessMilestone,
    RegisterReferral,
    RunWeeklyClanReferralSummary,
)
from pipirik_wars.application.roulette import SpinFreeRoulette
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.application.signup_queue import PromoteFromQueue
from pipirik_wars.application.top import GetTopClans, GetTopPlayers
from pipirik_wars.bot.main import Container, build_container, build_dispatcher
from pipirik_wars.domain.admin import IAdminConfirmStore, IAdminRepository, ITotpVerifier
from pipirik_wars.domain.clan import IClanMembershipRepository, IClanRepository
from pipirik_wars.domain.daily_head import DailyHeadService
from pipirik_wars.domain.dungeon import IDungeonRunRepository
from pipirik_wars.domain.enchantment.entities import Scroll, ScrollCategory
from pipirik_wars.domain.forest import IForestRunRepository
from pipirik_wars.domain.inventory import (
    IEnchantHistoryReader,
    IItemRepository,
    IScrollRepository,
    Item,
    ItemNotFoundError,
    ScrollStack,
)
from pipirik_wars.domain.monetization import IPaymentLedger, IPrizePoolRepository
from pipirik_wars.domain.mountains import IMountainRunRepository
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.pvp import IDuelRepository, IMassDuelRepository
from pipirik_wars.domain.roulette import IRouletteSpinRepository
from pipirik_wars.domain.security import IActivityLockRepository
from pipirik_wars.domain.shared.ports import IDelayedJobScheduler
from pipirik_wars.domain.signup_queue import ISignupQueueRepository
from pipirik_wars.infrastructure.admin import (
    InMemoryAdminConfirmStore,
    PyOtpTotpSecretGenerator,
    PyOtpTotpVerifier,
)
from pipirik_wars.infrastructure.anticheat import StructlogAnticheatAdminAlerter
from pipirik_wars.infrastructure.balance import YamlBalanceLoader
from pipirik_wars.infrastructure.balance.writer import YamlBalanceWriter
from pipirik_wars.infrastructure.clock import RealClock
from pipirik_wars.infrastructure.dau import (
    InMemoryDauCounter,
    InMemoryDauLimit,
    StructlogDauThresholdAlerter,
)
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyActivityLockRepository,
    SqlAlchemyAdminRepository,
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
    SqlAlchemyDailyActivityRepository,
    SqlAlchemyDailyHeadRepository,
    SqlAlchemyDuelRepository,
    SqlAlchemyDungeonRunRepository,
    SqlAlchemyEnchantHistoryReader,
    SqlAlchemyForestRunRepository,
    SqlAlchemyGlobalLobbyRepository,
    SqlAlchemyItemRepository,
    SqlAlchemyMassDuelRepository,
    SqlAlchemyMountainRunRepository,
    SqlAlchemyPaymentLedger,
    SqlAlchemyPlayerRepository,
    SqlAlchemyPrizePoolRepository,
    SqlAlchemyRouletteSpinRepository,
    SqlAlchemyScrollRepository,
    SqlAlchemySignupQueueRepository,
)
from pipirik_wars.infrastructure.db.services import (
    SqlAlchemyAdminAuditLogger,
    SqlAlchemyAuditLogger,
    SqlAlchemyIdempotencyService,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from pipirik_wars.infrastructure.random import RealRandom
from pipirik_wars.infrastructure.rate_limit import (
    InMemoryTokenBucketRateLimiter,
    IRateLimiter,
)
from pipirik_wars.infrastructure.scheduler import APSchedulerDelayedJobScheduler
from pipirik_wars.infrastructure.settings import (
    BootstrapSettings,
    BotSettings,
    DatabaseSettings,
    Settings,
)
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAdminAuditLogger,
    FakeAdminAuditQuery,
    FakeAdminAuthzAllowAll,
    FakeAdminRepository,
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeBroadcastSender,
    FakeCaravanParticipantRepository,
    FakeCaravanRepository,
    FakeClanMassDuelHistoryQuery,
    FakeClanMembershipRepository,
    FakeClanQuoteTemplateProvider,
    FakeClanRepository,
    FakeClanTopQuery,
    FakeClock,
    FakeDailyActivityRepository,
    FakeDailyHeadRepository,
    FakeDauThresholdAlerter,
    FakeDelayedJobScheduler,
    FakeDuelLogTemplateProvider,
    FakeDuelRepository,
    FakeDungeonRunRepository,
    FakeForestRunRepository,
    FakeGlobalLobbyRepository,
    FakeIdempotencyKey,
    FakeMassDuelRepository,
    FakeMessageBundle,
    FakeMountainRunRepository,
    FakeOracleHistoryRepository,
    FakeOracleTemplateProvider,
    FakePaymentLedger,
    FakePlayerLocaleResolver,
    FakePlayerRepository,
    FakePrizePoolRepository,
    FakeRandom,
    FakeReferralRepository,
    FakeRouletteSpinRepository,
    FakeSignupQueueRepository,
    FakeTopPlayersQuery,
    FakeTotpVerifier,
    FakeUnitOfWork,
    InlineBroadcastTaskSpawner,
)
from tests.unit.domain.balance.factories import build_valid_balance


class _StubItemRepository(IItemRepository):
    """In-memory `IItemRepository` для composition-root тестов.

    Не реализует логику бизнес-операций — только удовлетворяет protocol
    для инстанцирования `EnchantItem` / `GetInventory` use-case-ов.
    Полные фейки живут в `tests/unit/application/inventory/`.
    """

    __slots__ = ()

    async def get(self, *, player_id: int, item_id: str) -> Item:
        raise ItemNotFoundError(player_id=player_id, item_id=item_id)

    async def add(
        self,
        *,
        player_id: int,
        item_id: str,
        now: datetime,
    ) -> Item:
        raise NotImplementedError

    async def update_enchant_level(
        self,
        *,
        player_id: int,
        item_id: str,
        new_level: int,
    ) -> Item:
        raise NotImplementedError

    async def delete(self, *, player_id: int, item_id: str) -> None:
        raise NotImplementedError

    async def list_by_player(self, *, player_id: int) -> tuple[Item, ...]:
        return ()


class _StubScrollRepository(IScrollRepository):
    """In-memory `IScrollRepository` для composition-root тестов."""

    __slots__ = ()

    async def get(self, *, player_id: int, scroll_id: str) -> Scroll:
        return Scroll(category=ScrollCategory.WEAPON, blessed=False)

    async def add(
        self,
        *,
        player_id: int,
        scroll_id: str,
        qty: int,
        now: datetime,
    ) -> None:
        raise NotImplementedError

    async def consume(
        self,
        *,
        player_id: int,
        scroll_id: str,
        qty: int = 1,
    ) -> None:
        raise NotImplementedError

    async def list_by_player(self, *, player_id: int) -> tuple[ScrollStack, ...]:
        return ()


class _StubEnchantHistoryReader(IEnchantHistoryReader):
    """Стаб `IEnchantHistoryReader` для composition-root тестов."""

    __slots__ = ()

    async def get_recent_high_tier_outcomes(
        self,
        *,
        player_id: int,
        tier_min: int,
        tier_max: int,
        limit: int,
    ) -> tuple[bool, ...]:
        return ()


def _test_settings() -> Settings:
    return Settings(
        environment="test",
        db=DatabaseSettings(url=SecretStr("sqlite+aiosqlite:///:memory:")),
        bot=BotSettings(token=SecretStr("test-token")),
        bootstrap=BootstrapSettings(),
    )


def _fake_limiter() -> IRateLimiter:
    return cast(IRateLimiter, MagicMock(spec=IRateLimiter))


def _container_with_fakes() -> Container:  # noqa: PLR0915
    """Полный фейковый Container для unit-тестов composition-root-а."""
    uow = FakeUnitOfWork()
    audit = FakeAuditLogger()
    clock = FakeClock()
    players: IPlayerRepository = FakePlayerRepository()
    clans: IClanRepository = FakeClanRepository()
    members: IClanMembershipRepository = FakeClanMembershipRepository()
    admins: IAdminRepository = FakeAdminRepository()
    signup_queue: ISignupQueueRepository = FakeSignupQueueRepository()
    activity_locks: IActivityLockRepository = FakeActivityLockRepository()
    forest_runs: IForestRunRepository = FakeForestRunRepository()
    mountain_runs: IMountainRunRepository = FakeMountainRunRepository()
    dungeon_runs: IDungeonRunRepository = FakeDungeonRunRepository()
    duels: IDuelRepository = FakeDuelRepository()
    mass_duels: IMassDuelRepository = FakeMassDuelRepository()
    global_lobby = FakeGlobalLobbyRepository()
    referrals = FakeReferralRepository()
    balance = FakeBalanceConfig(build_valid_balance())
    dau_counter = InMemoryDauCounter(clock=clock)
    dau_limit = InMemoryDauLimit(initial=200)
    dau_threshold_alerter = FakeDauThresholdAlerter()
    idempotency = FakeIdempotencyKey()
    check_dau_threshold = CheckDauThreshold(
        uow=uow,
        dau_counter=dau_counter,
        dau_limit=dau_limit,
        idempotency=idempotency,
        audit=audit,
        alerter=dau_threshold_alerter,
        clock=clock,
    )
    rng = FakeRandom()
    delayed_jobs: IDelayedJobScheduler = FakeDelayedJobScheduler()
    activity_lock_service = ActivityLockService(
        repository=activity_locks,
        clock=clock,
    )
    apply_forest_name_drop = ApplyForestNameDrop(
        uow=uow,
        players=players,
        runs=forest_runs,
        audit=audit,
        clock=clock,
    )
    oracle_history = FakeOracleHistoryRepository()
    anticheat = FakeAnticheatRepository()
    anticheat_admin_alerter = FakeAnticheatAdminAlerter()
    oracle_templates = FakeOracleTemplateProvider()
    duel_log_templates = FakeDuelLogTemplateProvider()
    clan_quote_provider = FakeClanQuoteTemplateProvider()
    top_players_query = FakeTopPlayersQuery()
    top_clans_query = FakeClanTopQuery()
    clan_mass_duel_history_query = FakeClanMassDuelHistoryQuery()
    bundle: IMessageBundle = FakeMessageBundle()
    add_length = AddLength(
        uow=uow,
        players=players,
        anticheat=anticheat,
        audit=audit,
        balance=balance,
        clock=clock,
        idempotency=idempotency,
        admin_alerter=anticheat_admin_alerter,
    )
    finish_forest_run = FinishForestRun(
        uow=uow,
        players=players,
        runs=forest_runs,
        locks=activity_lock_service,
        length_granter=add_length,
        audit=audit,
        clock=clock,
    )
    finish_mountain_run = FinishMountainRun(
        uow=uow,
        players=players,
        runs=mountain_runs,
        locks=activity_lock_service,
        length_granter=add_length,
        audit=audit,
        clock=clock,
    )
    start_mountain_run = StartMountainRun(
        uow=uow,
        players=players,
        runs=mountain_runs,
        locks=activity_lock_service,
        balance=balance,
        random=rng,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    finish_dungeon_run = FinishDungeonRun(
        uow=uow,
        players=players,
        runs=dungeon_runs,
        locks=activity_lock_service,
        length_granter=add_length,
        audit=audit,
        clock=clock,
    )
    start_dungeon_run = StartDungeonRun(
        uow=uow,
        players=players,
        runs=dungeon_runs,
        locks=activity_lock_service,
        balance=balance,
        random=rng,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    challenge_duel = ChallengeDuel(
        uow=uow,
        players=players,
        duels=duels,
        locks=activity_lock_service,
        balance=balance,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
        lobby=global_lobby,
    )
    accept_duel = AcceptDuel(
        uow=uow,
        players=players,
        duels=duels,
        locks=activity_lock_service,
        balance=balance,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
        lobby=global_lobby,
    )
    cancel_duel = CancelDuel(
        uow=uow,
        players=players,
        duels=duels,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
        lobby=global_lobby,
    )
    submit_move = SubmitMove(
        uow=uow,
        players=players,
        duels=duels,
        locks=activity_lock_service,
        length_granter=add_length,
        audit=audit,
        clock=clock,
        balance=balance,
        scheduler=delayed_jobs,
    )
    resolve_afk_round = ResolveAfkRound(
        uow=uow,
        players=players,
        duels=duels,
        locks=activity_lock_service,
        length_granter=add_length,
        random=rng,
        audit=audit,
        clock=clock,
        balance=balance,
        scheduler=delayed_jobs,
    )
    enqueue_global_duel = EnqueueGlobalDuel(
        uow=uow,
        duels=duels,
        lobby=global_lobby,
        scheduler=delayed_jobs,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    match_from_lobby = MatchFromLobby(
        uow=uow,
        players=players,
        duels=duels,
        lobby=global_lobby,
        locks=activity_lock_service,
        scheduler=delayed_jobs,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    escalate_chat_to_global = EscalateChatToGlobal(
        uow=uow,
        duels=duels,
        lobby=global_lobby,
        scheduler=delayed_jobs,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    expire_lobby_entry = ExpireLobbyEntry(
        uow=uow,
        duels=duels,
        lobby=global_lobby,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
    )
    start_mass_duel = StartMassDuel(
        uow=uow,
        clans=clans,
        clan_members=members,
        players=players,
        duels=mass_duels,
        locks=activity_lock_service,
        balance=balance,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    submit_mass_move = SubmitMassMove(
        uow=uow,
        players=players,
        duels=mass_duels,
        clock=clock,
    )
    resolve_mass_duel = ResolveMassDuel(
        uow=uow,
        players=players,
        duels=mass_duels,
        locks=activity_lock_service,
        length_granter=add_length,
        random=rng,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    force_resolve_mass_duel = ForceResolveMassDuel(
        uow=uow,
        players=players,
        duels=mass_duels,
        locks=activity_lock_service,
        length_granter=add_length,
        random=rng,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    cancel_mass_duel = CancelMassDuel(
        uow=uow,
        duels=mass_duels,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    daily_heads = FakeDailyHeadRepository()
    daily_activity = FakeDailyActivityRepository()
    daily_head_service = DailyHeadService(
        balance=balance.get(),
        clock=clock,
        random=rng,
        heads=daily_heads,
        activity=daily_activity,
    )
    request_daily_head = RequestDailyHead(
        uow=uow,
        clans=clans,
        players=players,
        heads=daily_heads,
        daily_head_service=daily_head_service,
        length_granter=add_length,
        audit=audit,
        clock=clock,
    )
    run_daily_head_cron = RunDailyHeadCron(
        uow=uow,
        clans=clans,
        players=players,
        heads=daily_heads,
        daily_head_service=daily_head_service,
        length_granter=add_length,
        audit=audit,
        clock=clock,
    )
    record_player_activity = RecordPlayerActivity(
        uow=uow,
        players=players,
        daily_activity=daily_activity,
        clock=clock,
    )
    schedule_daily_head_cron_jobs = ScheduleDailyHeadCronJobs(
        uow=uow,
        clans=clans,
        scheduler=delayed_jobs,
        clock=clock,
    )
    admin_audit = FakeAdminAuditLogger()
    admin_confirm_store: IAdminConfirmStore = InMemoryAdminConfirmStore()
    totp_verifier: ITotpVerifier = FakeTotpVerifier()
    admin_authz = FakeAdminAuthzAllowAll()
    find_players_uc = FindPlayers(
        uow=uow,
        admins=admins,
        players=players,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    get_player_card_uc = GetPlayerCard(
        uow=uow,
        admins=admins,
        players=players,
        clans=clans,
        clan_members=members,
        forest_runs=forest_runs,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    freeze_player_uc = FreezePlayer(
        uow=uow,
        admins=admins,
        players=players,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    unfreeze_player_uc = UnfreezePlayer(
        uow=uow,
        admins=admins,
        players=players,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    ban_player_uc = BanPlayer(
        uow=uow,
        admins=admins,
        players=players,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    request_admin_confirm_uc = RequestAdminConfirm(
        uow=uow,
        admins=admins,
        store=admin_confirm_store,
        audit=admin_audit,
        clock=clock,
        token_factory=lambda: "test-token",
        authz=admin_authz,
    )
    verify_admin_confirm_uc = VerifyAdminConfirm(
        uow=uow,
        admins=admins,
        store=admin_confirm_store,
        totp=totp_verifier,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    grant_length_uc = GrantLength(
        uow=uow,
        admins=admins,
        players=players,
        length_granter=add_length,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    grant_thickness_uc = GrantThickness(
        uow=uow,
        admins=admins,
        players=players,
        balance=balance,
        idempotency=idempotency,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    get_balance_value_uc = GetBalanceValue(
        uow=uow,
        admins=admins,
        balance=balance,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    set_balance_value_uc = SetBalanceValue(
        uow=uow,
        admins=admins,
        balance=balance,
        writer=YamlBalanceWriter(
            path=Path("/tmp/__pw_test_balance.yaml"),
            loader=balance,
        ),
        idempotency=idempotency,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    admin_audit_query = FakeAdminAuditQuery()
    get_admin_audit_trail_uc = GetAdminAuditTrail(
        uow=uow,
        admins=admins,
        query=admin_audit_query,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    get_clan_card_uc = GetClanCard(
        uow=uow,
        admins=admins,
        players=players,
        clans=clans,
        clan_members=members,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    freeze_clan_admin_uc = FreezeClanAdmin(
        uow=uow,
        admins=admins,
        clans=clans,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    unfreeze_clan_admin_uc = UnfreezeClanAdmin(
        uow=uow,
        admins=admins,
        clans=clans,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    get_clan_daily_head_history_uc = GetClanDailyHeadHistory(
        uow=uow,
        admins=admins,
        clans=clans,
        players=players,
        daily_heads=daily_heads,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    broadcast_announcement_uc = BroadcastAnnouncement(
        uow=uow,
        admins=admins,
        players=players,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    broadcast_sender = FakeBroadcastSender()
    broadcast_task_spawner = InlineBroadcastTaskSpawner()
    run_broadcast_announcement_uc = RunBroadcastAnnouncement(
        uow=uow,
        admins=admins,
        players=players,
        sender=broadcast_sender,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    totp_secret_generator = PyOtpTotpSecretGenerator()
    setup_admin_totp_uc = SetupAdminTotp(
        uow=uow,
        admins=admins,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
        secret_generator=totp_secret_generator,
        bootstrap_password=None,
    )
    boss_participants_repo = FakeBossParticipantRepository()
    boss_fights_repo = FakeBossFightRepository(participants=boss_participants_repo)
    summon_boss_uc = SummonBoss(
        uow=uow,
        players=players,
        boss_fights=boss_fights_repo,
        boss_participants=boss_participants_repo,
        locks=activity_lock_service,
        balance=balance,
        random=rng,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    join_boss_lobby_uc = JoinBossLobby(
        uow=uow,
        players=players,
        boss_fights=boss_fights_repo,
        boss_participants=boss_participants_repo,
        locks=activity_lock_service,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    leave_boss_lobby_uc = LeaveBossLobby(
        uow=uow,
        players=players,
        boss_fights=boss_fights_repo,
        boss_participants=boss_participants_repo,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
    )
    close_boss_lobby_uc = CloseBossLobby(
        uow=uow,
        boss_fights=boss_fights_repo,
        audit=audit,
        clock=clock,
    )
    run_boss_round_uc = RunBossRound(
        uow=uow,
        boss_fights=boss_fights_repo,
        boss_participants=boss_participants_repo,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
        balance=balance.get().bosses,
        random_factory=lambda _seed: rng,
    )
    finish_boss_fight_uc = FinishBossFight(
        uow=uow,
        boss_fights=boss_fights_repo,
        boss_participants=boss_participants_repo,
        players=players,
        length_granter=add_length,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
        balance=balance.get().bosses,
        random_factory=lambda _seed: rng,
    )
    cancel_boss_fight_uc = CancelBossFight(
        uow=uow,
        boss_fights=boss_fights_repo,
        boss_participants=boss_participants_repo,
        players=players,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    caravans_repo = FakeCaravanRepository()
    caravan_participants_repo = FakeCaravanParticipantRepository()
    create_caravan_uc = CreateCaravan(
        uow=uow,
        clans=clans,
        clan_members=members,
        players=players,
        caravans=caravans_repo,
        caravan_participants=caravan_participants_repo,
        locks=activity_lock_service,
        balance=balance,
        random=rng,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    join_caravan_lobby_uc = JoinCaravanLobby(
        uow=uow,
        caravans=caravans_repo,
        caravan_participants=caravan_participants_repo,
        clan_members=members,
        players=players,
        locks=activity_lock_service,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    leave_caravan_lobby_uc = LeaveCaravanLobby(
        uow=uow,
        caravans=caravans_repo,
        caravan_participants=caravan_participants_repo,
        players=players,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
    )
    # Спринт 3.4-B/C/D: инвентарь (ГДД §2.6) + заточка (§2.8). Репо
    # и use-case-ы пробрасываются в dispatcher в build_dispatcher (3.4-D).
    items_repo: IItemRepository = _StubItemRepository()
    scrolls_repo: IScrollRepository = _StubScrollRepository()
    enchant_history_reader: IEnchantHistoryReader = _StubEnchantHistoryReader()
    enchant_item_uc = EnchantItem(
        uow=uow,
        item_repo=items_repo,
        scroll_repo=scrolls_repo,
        balance=balance,
        random=rng,
        audit=audit,
        idempotency=idempotency,
        clock=clock,
        enchant_history=enchant_history_reader,
    )
    get_inventory_uc = GetInventory(
        item_repo=items_repo,
        scroll_repo=scrolls_repo,
        balance=balance,
    )
    cancel_caravan_uc = CancelCaravan(
        uow=uow,
        caravans=caravans_repo,
        caravan_participants=caravan_participants_repo,
        players=players,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    # Спринт 3.5-B/C/D: free-to-play рулетка. `roulette_spins_repo` —
    # in-memory фейк; `spin_free_roulette_uc` — реальный use-case с
    # фейковыми зависимостями (проверяет инстанцируемость в Container).
    roulette_spins_repo: IRouletteSpinRepository = FakeRouletteSpinRepository()
    spin_free_roulette_uc = SpinFreeRoulette(
        uow=uow,
        players=players,
        roulette_spins=roulette_spins_repo,
        length_granter=add_length,
        balance=balance,
        audit=audit,
        idempotency=idempotency,
        random=rng,
        clock=clock,
    )
    # Спринт 4.1-A: платная рулетка. `FakePaymentLedger` — in-memory
    # ledger с idempotency-key dedup; `spin_paid_roulette_uc` — реальный
    # use-case с теми же фейковыми зависимостями (проверяет
    # инстанцируемость в Container).
    payment_ledger_repo: IPaymentLedger = FakePaymentLedger()
    # Спринт 4.1-B: призовой пул. `FakePrizePoolRepository` — in-memory
    # state + лог вызовов `apply_increment`. `record_donation_uc` —
    # реальный use-case на фейк-репозитории (пробрасывается в
    # `SpinPaidRoulette` Step 5b 10-step flow-а).
    prize_pool_repo_fake: IPrizePoolRepository = FakePrizePoolRepository()
    record_donation_uc = RecordDonation(
        prize_pool_repository=prize_pool_repo_fake,
        audit_logger=audit,
        clock=clock,
    )
    spin_paid_roulette_uc = SpinPaidRoulette(
        uow=uow,
        players=players,
        roulette_spins=roulette_spins_repo,
        payments=payment_ledger_repo,
        length_granter=add_length,
        balance=balance,
        audit=audit,
        idempotency=idempotency,
        random=rng,
        clock=clock,
        record_donation=record_donation_uc,
    )
    close_caravan_lobby_uc = CloseCaravanLobby(
        uow=uow,
        caravans=caravans_repo,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    return Container(
        clock=clock,
        random=rng,
        uow=uow,
        idempotency=idempotency,
        audit=audit,
        balance=balance,
        balance_reloader=balance,
        rate_limiter=_fake_limiter(),
        settings=_test_settings(),
        players=players,
        clans=clans,
        clan_members=members,
        admins=admins,
        signup_queue=signup_queue,
        activity_locks=activity_locks,
        forest_runs=forest_runs,
        mountain_runs=mountain_runs,
        dungeon_runs=dungeon_runs,
        duels=duels,
        mass_duels=mass_duels,
        global_lobby=global_lobby,
        referrals=referrals,
        delayed_jobs=delayed_jobs,
        register_player=RegisterPlayer(
            uow=uow,
            players=players,
            signup_queue=signup_queue,
            dau_counter=dau_counter,
            dau_limit=dau_limit,
            audit=audit,
            clock=clock,
            check_threshold=check_dau_threshold,
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
        get_profile=GetProfile(
            uow=uow,
            players=players,
            balance=balance,
        ),
        reload_balance=ReloadBalance(
            uow=uow,
            admins=admins,
            balance=balance,
            reloader=balance,
            audit=audit,
            admin_audit=admin_audit,
            authz=admin_authz,
            clock=clock,
        ),
        dau_counter=dau_counter,
        dau_limit=dau_limit,
        dau_threshold_alerter=dau_threshold_alerter,
        get_dau_stats=GetDauStats(counter=dau_counter, limit=dau_limit),
        set_max_dau=SetMaxDau(
            uow=uow,
            admins=admins,
            limit=dau_limit,
            audit=audit,
            admin_audit=admin_audit,
            authz=admin_authz,
            clock=clock,
        ),
        promote_from_queue=PromoteFromQueue(
            uow=uow,
            players=players,
            signup_queue=signup_queue,
            dau_counter=dau_counter,
            dau_limit=dau_limit,
            audit=audit,
            clock=clock,
            check_threshold=check_dau_threshold,
        ),
        check_dau_threshold=check_dau_threshold,
        start_forest_run=StartForestRun(
            uow=uow,
            players=players,
            runs=forest_runs,
            locks=activity_lock_service,
            balance=balance,
            random=rng,
            audit=audit,
            clock=clock,
            scheduler=delayed_jobs,
        ),
        finish_forest_run=finish_forest_run,
        apply_forest_name_drop=apply_forest_name_drop,
        start_mountain_run=start_mountain_run,
        finish_mountain_run=finish_mountain_run,
        start_dungeon_run=start_dungeon_run,
        finish_dungeon_run=finish_dungeon_run,
        upgrade_thickness=UpgradeThickness(
            uow=uow,
            players=players,
            balance=balance,
            audit=audit,
            clock=clock,
        ),
        oracle_history=oracle_history,
        anticheat=anticheat,
        anticheat_admin_alerter=anticheat_admin_alerter,
        oracle_templates=oracle_templates,
        duel_log_templates=duel_log_templates,
        clan_quote_provider=clan_quote_provider,
        invoke_oracle=InvokeOracle(
            uow=uow,
            players=players,
            history=oracle_history,
            templates=oracle_templates,
            balance=balance,
            random=rng,
            length_granter=add_length,
            clock=clock,
            clans=clans,
        ),
        top_players_query=top_players_query,
        top_clans_query=top_clans_query,
        clan_mass_duel_history_query=clan_mass_duel_history_query,
        get_top_players=GetTopPlayers(query=top_players_query),
        get_top_clans=GetTopClans(query=top_clans_query),
        get_clan_attack_history=GetClanAttackHistory(query=clan_mass_duel_history_query),
        bundle=bundle,
        player_locale_resolver=FakePlayerLocaleResolver(),
        set_player_locale=SetPlayerLocale(
            uow=uow,
            players=players,
            audit=audit,
            clock=clock,
        ),
        add_length=add_length,
        lift_anticheat_ban=LiftAnticheatBan(
            uow=uow,
            admins=admins,
            players=players,
            audit=audit,
            admin_audit=admin_audit,
            authz=admin_authz,
            clock=clock,
        ),
        challenge_duel=challenge_duel,
        accept_duel=accept_duel,
        cancel_duel=cancel_duel,
        submit_move=submit_move,
        resolve_afk_round=resolve_afk_round,
        enqueue_global_duel=enqueue_global_duel,
        match_from_lobby=match_from_lobby,
        escalate_chat_to_global=escalate_chat_to_global,
        expire_lobby_entry=expire_lobby_entry,
        start_mass_duel=start_mass_duel,
        submit_mass_move=submit_mass_move,
        resolve_mass_duel=resolve_mass_duel,
        force_resolve_mass_duel=force_resolve_mass_duel,
        cancel_mass_duel=cancel_mass_duel,
        daily_heads=daily_heads,
        daily_activity=daily_activity,
        daily_head_service=daily_head_service,
        request_daily_head=request_daily_head,
        run_daily_head_cron=run_daily_head_cron,
        record_player_activity=record_player_activity,
        schedule_daily_head_cron_jobs=schedule_daily_head_cron_jobs,
        register_referral=RegisterReferral(
            uow=uow,
            players=players,
            referrals=referrals,
            clock=clock,
            rate_limiter=_fake_limiter(),
            audit=audit,
        ),
        grant_referral_signup_bonus=GrantReferralSignupBonus(
            uow=uow,
            players=players,
            referrals=referrals,
            length_granter=add_length,
            balance=balance,
            clock=clock,
        ),
        grant_referral_thickness_milestone=GrantReferralThicknessMilestone(
            uow=uow,
            players=players,
            referrals=referrals,
            length_granter=add_length,
            balance=balance,
        ),
        run_weekly_clan_referral_summary=RunWeeklyClanReferralSummary(
            uow=uow,
            clans=clans,
            players=players,
            referrals=referrals,
            clock=clock,
        ),
        admin_audit=admin_audit,
        admin_audit_query=admin_audit_query,
        admin_confirm_store=admin_confirm_store,
        totp_verifier=totp_verifier,
        admin_authz=admin_authz,
        find_players=find_players_uc,
        get_player_card=get_player_card_uc,
        freeze_player=freeze_player_uc,
        unfreeze_player=unfreeze_player_uc,
        ban_player=ban_player_uc,
        request_admin_confirm=request_admin_confirm_uc,
        verify_admin_confirm=verify_admin_confirm_uc,
        grant_length=grant_length_uc,
        grant_thickness=grant_thickness_uc,
        get_balance_value=get_balance_value_uc,
        set_balance_value=set_balance_value_uc,
        get_admin_audit_trail=get_admin_audit_trail_uc,
        get_clan_card=get_clan_card_uc,
        freeze_clan_admin=freeze_clan_admin_uc,
        unfreeze_clan_admin=unfreeze_clan_admin_uc,
        get_clan_daily_head_history=get_clan_daily_head_history_uc,
        broadcast_announcement=broadcast_announcement_uc,
        run_broadcast_announcement=run_broadcast_announcement_uc,
        broadcast_sender=broadcast_sender,
        broadcast_task_spawner=broadcast_task_spawner,
        totp_secret_generator=totp_secret_generator,
        setup_admin_totp=setup_admin_totp_uc,
        caravans=caravans_repo,
        caravan_participants=caravan_participants_repo,
        create_caravan=create_caravan_uc,
        join_caravan_lobby=join_caravan_lobby_uc,
        leave_caravan_lobby=leave_caravan_lobby_uc,
        cancel_caravan=cancel_caravan_uc,
        close_caravan_lobby=close_caravan_lobby_uc,
        boss_fights=boss_fights_repo,
        boss_participants=boss_participants_repo,
        summon_boss=summon_boss_uc,
        join_boss_lobby=join_boss_lobby_uc,
        leave_boss_lobby=leave_boss_lobby_uc,
        cancel_boss_fight=cancel_boss_fight_uc,
        close_boss_lobby=close_boss_lobby_uc,
        run_boss_round=run_boss_round_uc,
        finish_boss_fight=finish_boss_fight_uc,
        items=items_repo,
        scrolls=scrolls_repo,
        enchant_history=enchant_history_reader,
        enchant_item=enchant_item_uc,
        get_inventory=get_inventory_uc,
        roulette_spins=roulette_spins_repo,
        spin_free_roulette=spin_free_roulette_uc,
        payment_ledger=payment_ledger_repo,
        spin_paid_roulette=spin_paid_roulette_uc,
        prize_pool_repo=prize_pool_repo_fake,
        record_donation=record_donation_uc,
    )


class TestContainer:
    def test_container_holds_all_ports(self) -> None:  # noqa: PLR0915
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
        # Use-case-ы и репозитории (Спринт 1.1.E).
        assert isinstance(c.admins, FakeAdminRepository)
        assert c.balance_reloader is c.balance
        assert isinstance(c.get_profile, GetProfile)
        assert isinstance(c.reload_balance, ReloadBalance)
        # DAU Gate (Спринт 1.2.B).
        assert isinstance(c.dau_counter, InMemoryDauCounter)
        assert isinstance(c.dau_limit, InMemoryDauLimit)
        assert isinstance(c.get_dau_stats, GetDauStats)
        assert isinstance(c.set_max_dau, SetMaxDau)
        # Signup queue + promote (Спринт 1.2.C).
        assert isinstance(c.signup_queue, FakeSignupQueueRepository)
        assert isinstance(c.promote_from_queue, PromoteFromQueue)
        # DAU threshold alert (Спринт 1.2.D).
        assert isinstance(c.dau_threshold_alerter, FakeDauThresholdAlerter)
        assert isinstance(c.check_dau_threshold, CheckDauThreshold)
        # Forest (Спринт 1.3.B).
        assert isinstance(c.activity_locks, FakeActivityLockRepository)
        assert isinstance(c.forest_runs, FakeForestRunRepository)
        assert isinstance(c.start_forest_run, StartForestRun)
        # Forest finish + scheduler (Спринт 1.3.C).
        assert isinstance(c.delayed_jobs, FakeDelayedJobScheduler)
        assert isinstance(c.finish_forest_run, FinishForestRun)
        # PvE-походы гор и данжона (Спринт 3.1-B).
        assert isinstance(c.mountain_runs, FakeMountainRunRepository)
        assert isinstance(c.start_mountain_run, StartMountainRun)
        assert isinstance(c.finish_mountain_run, FinishMountainRun)
        assert isinstance(c.dungeon_runs, FakeDungeonRunRepository)
        assert isinstance(c.start_dungeon_run, StartDungeonRun)
        assert isinstance(c.finish_dungeon_run, FinishDungeonRun)
        # Thickness upgrade (Спринт 1.4.A).
        assert isinstance(c.upgrade_thickness, UpgradeThickness)
        # i18n bundle (Спринт 1.5.A → 1.5.B).
        assert isinstance(c.bundle, FakeMessageBundle)
        # Anticheat add_length (Спринт 1.6.D).
        assert isinstance(c.anticheat_admin_alerter, FakeAnticheatAdminAlerter)
        assert isinstance(c.add_length, AddLength)
        # PvP 1×1 (Спринт 2.1.C → 2.1.E).
        assert isinstance(c.duels, FakeDuelRepository)
        assert isinstance(c.challenge_duel, ChallengeDuel)
        assert isinstance(c.accept_duel, AcceptDuel)
        assert isinstance(c.cancel_duel, CancelDuel)
        assert isinstance(c.submit_move, SubmitMove)
        assert isinstance(c.resolve_afk_round, ResolveAfkRound)
        # PvP global lobby (Спринт 2.1.F.2): use-cases + lobby-репо
        # в Container-е и выведены как отдельные поля.
        assert isinstance(c.global_lobby, FakeGlobalLobbyRepository)
        assert isinstance(c.enqueue_global_duel, EnqueueGlobalDuel)
        assert isinstance(c.match_from_lobby, MatchFromLobby)
        assert isinstance(c.escalate_chat_to_global, EscalateChatToGlobal)
        assert isinstance(c.expire_lobby_entry, ExpireLobbyEntry)

    def test_container_holds_mass_duel_use_cases(self) -> None:
        """Mass-PvP клан×клан (Спринт 2.2.E)."""
        c = _container_with_fakes()
        assert isinstance(c.mass_duels, FakeMassDuelRepository)
        assert isinstance(c.start_mass_duel, StartMassDuel)
        assert isinstance(c.submit_mass_move, SubmitMassMove)
        assert isinstance(c.resolve_mass_duel, ResolveMassDuel)
        assert isinstance(c.force_resolve_mass_duel, ForceResolveMassDuel)
        assert isinstance(c.cancel_mass_duel, CancelMassDuel)

    def test_container_holds_daily_head_use_cases(self) -> None:
        """Daily Head «Глава клана дня» (Спринт 2.3.C)."""
        c = _container_with_fakes()
        assert isinstance(c.daily_heads, FakeDailyHeadRepository)
        assert isinstance(c.daily_activity, FakeDailyActivityRepository)
        assert isinstance(c.daily_head_service, DailyHeadService)
        assert isinstance(c.request_daily_head, RequestDailyHead)
        assert isinstance(c.run_daily_head_cron, RunDailyHeadCron)

    def test_container_holds_referral_use_cases(self) -> None:
        """Реферальная система (Спринт 2.4.D + 2.4.E)."""
        c = _container_with_fakes()
        assert isinstance(c.register_referral, RegisterReferral)
        assert isinstance(c.grant_referral_signup_bonus, GrantReferralSignupBonus)
        assert isinstance(c.grant_referral_thickness_milestone, GrantReferralThicknessMilestone)
        assert isinstance(c.run_weekly_clan_referral_summary, RunWeeklyClanReferralSummary)

    def test_container_holds_inventory_use_cases(self) -> None:
        """Инвентарь и заточка (Спринт 3.4-B/C/D, ГДД §2.6 + §2.8)."""
        c = _container_with_fakes()
        assert isinstance(c.items, _StubItemRepository)
        assert isinstance(c.scrolls, _StubScrollRepository)
        assert isinstance(c.enchant_history, _StubEnchantHistoryReader)
        assert isinstance(c.enchant_item, EnchantItem)
        assert isinstance(c.get_inventory, GetInventory)

    def test_container_holds_roulette_use_cases(self) -> None:
        """Free-to-play рулетка (Спринт 3.5-B/C/D, ГДД §12.4)."""
        c = _container_with_fakes()
        assert isinstance(c.roulette_spins, FakeRouletteSpinRepository)
        assert isinstance(c.spin_free_roulette, SpinFreeRoulette)

    def test_container_holds_paid_roulette_use_cases(self) -> None:
        """Платная рулетка (Спринт 4.1-A, ГДД §12.5) + призовой пул (4.1-B, ГДД §12.6)."""
        c = _container_with_fakes()
        assert isinstance(c.payment_ledger, FakePaymentLedger)
        assert isinstance(c.spin_paid_roulette, SpinPaidRoulette)
        assert isinstance(c.prize_pool_repo, FakePrizePoolRepository)
        assert isinstance(c.record_donation, RecordDonation)

    def test_container_holds_admin_support_use_cases(self) -> None:
        """Расширенный админ-интерфейс (Спринт 2.5-A.3 + 2.5-B)."""
        c = _container_with_fakes()
        # Инфраструктурные адаптеры.
        assert isinstance(c.admin_audit, FakeAdminAuditLogger)
        assert isinstance(c.admin_confirm_store, InMemoryAdminConfirmStore)
        assert isinstance(c.totp_verifier, FakeTotpVerifier)
        # Use-case-ы B.1-B.5.
        assert isinstance(c.find_players, FindPlayers)
        assert isinstance(c.get_player_card, GetPlayerCard)
        assert isinstance(c.freeze_player, FreezePlayer)
        assert isinstance(c.unfreeze_player, UnfreezePlayer)
        assert isinstance(c.ban_player, BanPlayer)
        assert isinstance(c.request_admin_confirm, RequestAdminConfirm)
        assert isinstance(c.verify_admin_confirm, VerifyAdminConfirm)

    def test_container_is_frozen(self) -> None:
        c = _container_with_fakes()
        with pytest.raises((AttributeError, TypeError)):
            c.clock = FakeClock()


class TestBuildContainer:
    def test_build_container_returns_real_adapters(self) -> None:  # noqa: PLR0915
        c = build_container(settings=_test_settings())
        assert isinstance(c.clock, RealClock)
        assert isinstance(c.random, RealRandom)
        assert isinstance(c.uow, SqlAlchemyUnitOfWork)
        assert isinstance(c.idempotency, SqlAlchemyIdempotencyService)
        assert isinstance(c.audit, SqlAlchemyAuditLogger)
        assert isinstance(c.balance, YamlBalanceLoader)
        assert isinstance(c.rate_limiter, InMemoryTokenBucketRateLimiter)
        assert c.settings.environment == "test"
        # Реальные SQLAlchemy-репозитории (Спринт 1.1.D + 1.1.E).
        assert isinstance(c.players, SqlAlchemyPlayerRepository)
        assert isinstance(c.clans, SqlAlchemyClanRepository)
        assert isinstance(c.clan_members, SqlAlchemyClanMembershipRepository)
        assert isinstance(c.admins, SqlAlchemyAdminRepository)
        # `YamlBalanceLoader` реализует и `IBalanceConfig`, и
        # `IBalanceReloader`; в DI это один и тот же объект.
        assert c.balance_reloader is c.balance
        assert isinstance(c.get_profile, GetProfile)
        assert isinstance(c.reload_balance, ReloadBalance)
        # DAU Gate (Спринт 1.2.B): in-memory counter + limit.
        assert isinstance(c.dau_counter, InMemoryDauCounter)
        assert isinstance(c.dau_limit, InMemoryDauLimit)
        assert isinstance(c.get_dau_stats, GetDauStats)
        assert isinstance(c.set_max_dau, SetMaxDau)
        # Signup queue + promote (Спринт 1.2.C).
        assert isinstance(c.signup_queue, SqlAlchemySignupQueueRepository)
        assert isinstance(c.promote_from_queue, PromoteFromQueue)
        # DAU threshold alert (Спринт 1.2.D).
        assert isinstance(c.dau_threshold_alerter, StructlogDauThresholdAlerter)
        assert isinstance(c.check_dau_threshold, CheckDauThreshold)
        # Forest (Спринт 1.3.B): реальные SQLAlchemy-репозитории.
        assert isinstance(c.activity_locks, SqlAlchemyActivityLockRepository)
        assert isinstance(c.forest_runs, SqlAlchemyForestRunRepository)
        assert isinstance(c.start_forest_run, StartForestRun)
        # PvP 1×1 (Спринт 2.1.C → 2.1.E): реальный duel-репозиторий + use-cases.
        assert isinstance(c.duels, SqlAlchemyDuelRepository)
        assert isinstance(c.challenge_duel, ChallengeDuel)
        assert isinstance(c.accept_duel, AcceptDuel)
        assert isinstance(c.cancel_duel, CancelDuel)
        assert isinstance(c.submit_move, SubmitMove)
        assert isinstance(c.resolve_afk_round, ResolveAfkRound)
        # PvP global lobby (Спринт 2.1.F.2): реальный lobby-репо + 4 use-cases.
        assert isinstance(c.global_lobby, SqlAlchemyGlobalLobbyRepository)
        assert isinstance(c.enqueue_global_duel, EnqueueGlobalDuel)
        assert isinstance(c.match_from_lobby, MatchFromLobby)
        assert isinstance(c.escalate_chat_to_global, EscalateChatToGlobal)
        assert isinstance(c.expire_lobby_entry, ExpireLobbyEntry)
        # Mass-PvP клан×клан (Спринт 2.2.E): реальный mass-duel-репо + 5 use-cases.
        assert isinstance(c.mass_duels, SqlAlchemyMassDuelRepository)
        assert isinstance(c.start_mass_duel, StartMassDuel)
        assert isinstance(c.submit_mass_move, SubmitMassMove)
        assert isinstance(c.resolve_mass_duel, ResolveMassDuel)
        assert isinstance(c.force_resolve_mass_duel, ForceResolveMassDuel)
        assert isinstance(c.cancel_mass_duel, CancelMassDuel)
        # Daily Head «Глава клана дня» (Спринт 2.3.C): реальные репо + сервис + 2 use-cases.
        assert isinstance(c.daily_heads, SqlAlchemyDailyHeadRepository)
        assert isinstance(c.daily_activity, SqlAlchemyDailyActivityRepository)
        assert isinstance(c.daily_head_service, DailyHeadService)
        assert isinstance(c.request_daily_head, RequestDailyHead)
        assert isinstance(c.run_daily_head_cron, RunDailyHeadCron)
        # Forest finish + scheduler (Спринт 1.3.C).
        assert isinstance(c.delayed_jobs, APSchedulerDelayedJobScheduler)
        assert isinstance(c.finish_forest_run, FinishForestRun)
        # PvE-походы гор и данжона (Спринт 3.1-B): реальные SQL-репозитории.
        assert isinstance(c.mountain_runs, SqlAlchemyMountainRunRepository)
        assert isinstance(c.start_mountain_run, StartMountainRun)
        assert isinstance(c.finish_mountain_run, FinishMountainRun)
        assert isinstance(c.dungeon_runs, SqlAlchemyDungeonRunRepository)
        assert isinstance(c.start_dungeon_run, StartDungeonRun)
        assert isinstance(c.finish_dungeon_run, FinishDungeonRun)
        # Thickness upgrade (Спринт 1.4.A).
        assert isinstance(c.upgrade_thickness, UpgradeThickness)
        # i18n bundle (Спринт 1.5.A → 1.5.B): реальный FluentMessageBundle.
        assert isinstance(c.bundle, FluentMessageBundle)
        # Anticheat add_length (Спринт 1.6.D).
        assert isinstance(c.anticheat_admin_alerter, StructlogAnticheatAdminAlerter)
        assert isinstance(c.add_length, AddLength)
        # Расширенный админ-интерфейс (Спринт 2.5-A + 2.5-B): реальные
        # адаптеры — `SqlAlchemyAdminAuditLogger`, in-memory store и
        # `PyOtpTotpVerifier`.
        assert isinstance(c.admin_audit, SqlAlchemyAdminAuditLogger)
        assert isinstance(c.admin_confirm_store, InMemoryAdminConfirmStore)
        assert isinstance(c.totp_verifier, PyOtpTotpVerifier)
        assert isinstance(c.find_players, FindPlayers)
        assert isinstance(c.get_player_card, GetPlayerCard)
        assert isinstance(c.freeze_player, FreezePlayer)
        assert isinstance(c.unfreeze_player, UnfreezePlayer)
        assert isinstance(c.ban_player, BanPlayer)
        assert isinstance(c.request_admin_confirm, RequestAdminConfirm)
        assert isinstance(c.verify_admin_confirm, VerifyAdminConfirm)
        # Инвентарь и заточка (Спринт 3.4-B/C/D): реальные
        # SQLAlchemy-репозитории + use-case-ы.
        assert isinstance(c.items, SqlAlchemyItemRepository)
        assert isinstance(c.scrolls, SqlAlchemyScrollRepository)
        assert isinstance(c.enchant_history, SqlAlchemyEnchantHistoryReader)
        assert isinstance(c.enchant_item, EnchantItem)
        assert isinstance(c.get_inventory, GetInventory)
        # Free-to-play рулетка (Спринт 3.5-B/C/D): реальный
        # SQLAlchemy-репозиторий + use-case `SpinFreeRoulette`.
        assert isinstance(c.roulette_spins, SqlAlchemyRouletteSpinRepository)
        assert isinstance(c.spin_free_roulette, SpinFreeRoulette)
        # Платная рулетка (Спринт 4.1-A): реальный SQLAlchemy-ledger +
        # use-case `SpinPaidRoulette`. + Призовой пул (Спринт 4.1-B):
        # реальный `SqlAlchemyPrizePoolRepository` + use-case `RecordDonation`.
        assert isinstance(c.payment_ledger, SqlAlchemyPaymentLedger)
        assert isinstance(c.spin_paid_roulette, SpinPaidRoulette)
        assert isinstance(c.prize_pool_repo, SqlAlchemyPrizePoolRepository)
        assert isinstance(c.record_donation, RecordDonation)


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
        # `dp.callback_query` и `dp.my_chat_member` имеют 5 middleware-ов:
        # error / auth / admin_guard / locale / throttle (Спринт 2.5-A.2:
        # AdminGuard прибавился между auth и locale).
        for observer in (dp.callback_query, dp.my_chat_member):
            assert len(list(observer.middleware)) == 5
        # `dp.message` дополнительно содержит DailyActivityMiddleware
        # (Спринт 2.3.F.1) — итого 6.
        assert len(list(dp.message.middleware)) == 6
        # Минимум 4 router-а: `start`, `profile`, `admin`, `registration`.
        assert any(r.name == "start" for r in dp.sub_routers)
        assert any(r.name == "registration" for r in dp.sub_routers)
        assert any(r.name == "profile" for r in dp.sub_routers)
        assert any(r.name == "admin" for r in dp.sub_routers)
        # Use-case-ы прокинуты в workflow-data для aiogram DI.
        assert dp["register_player"] is c.register_player
        assert dp["register_clan"] is c.register_clan
        assert dp["migrate_clan"] is c.migrate_clan
        assert dp["join_clan"] is c.join_clan
        assert dp["freeze_clan"] is c.freeze_clan
        assert dp["get_profile"] is c.get_profile
        assert dp["reload_balance"] is c.reload_balance
        assert dp["get_dau_stats"] is c.get_dau_stats
        assert dp["set_max_dau"] is c.set_max_dau
        assert dp["signup_queue"] is c.signup_queue
        assert dp["start_forest_run"] is c.start_forest_run
        assert dp["finish_forest_run"] is c.finish_forest_run
        assert dp["promote_from_queue"] is c.promote_from_queue
        assert dp["upgrade_thickness"] is c.upgrade_thickness
        assert dp["balance"] is c.balance
        # Sprint 1.4.A: новый router `upgrade`.
        assert any(r.name == "upgrade" for r in dp.sub_routers)
        # Sprint 1.5.B: bundle прокинут в workflow-data для handler-ов.
        assert dp["bundle"] is c.bundle
        # Sprint 2.1.E: новый router `duel` + use-case-ы PvP в workflow-data.
        assert any(r.name == "duel" for r in dp.sub_routers)
        assert dp["challenge_duel"] is c.challenge_duel
        assert dp["accept_duel"] is c.accept_duel
        assert dp["cancel_duel"] is c.cancel_duel
        assert dp["submit_move"] is c.submit_move
        assert dp["resolve_afk_round"] is c.resolve_afk_round
        # Sprint 2.1.F.2: PvP-lobby use-cases в workflow-data для handler-ов F.3.
        assert dp["enqueue_global_duel"] is c.enqueue_global_duel
        assert dp["match_from_lobby"] is c.match_from_lobby
        # Sprint 2.3.C: Daily Head use-cases в workflow-data для handler-а 2.3.E.
        assert dp["request_daily_head"] is c.request_daily_head
        assert dp["run_daily_head_cron"] is c.run_daily_head_cron
        # Sprint 2.5-B: admin_support router + use-cases в workflow-data.
        assert any(r.name == "admin_support" for r in dp.sub_routers)
        assert dp["find_players"] is c.find_players
        assert dp["get_player_card"] is c.get_player_card
        assert dp["freeze_player"] is c.freeze_player
        assert dp["unfreeze_player"] is c.unfreeze_player
        assert dp["ban_player"] is c.ban_player
        assert dp["request_admin_confirm"] is c.request_admin_confirm
        assert dp["verify_admin_confirm"] is c.verify_admin_confirm
        # Sprint 3.4-D: инвентарь + заточка use-case-ы + uow в workflow-data
        # для handler-ов `/inventory` и `/enchant`.
        assert dp["get_inventory"] is c.get_inventory
        assert dp["enchant_item"] is c.enchant_item
        assert dp["uow"] is c.uow
