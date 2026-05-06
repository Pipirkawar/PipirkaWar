"""Composition root для Telegram-бота.

ГДД §0 / development_plan.md Спринт 0.1.4: вся сборка зависимостей —
ровно в этом модуле. Никаких сервис-локаторов / глобальных DI-контейнеров —
явный конструктор `Container` собирает всё, что нужно use-case-ам, и
пробрасывает в bot-handlers через `Dispatcher` data.

Спринт 0.2: `build_container()` собирает реальные адаптеры
(`SqlAlchemyUnitOfWork`, `RealClock`, `RealRandom`,
`SqlAlchemyIdempotencyService`, `SqlAlchemyAuditLogger`).
Спринт 0.2.10: добавлен `YamlBalanceLoader` (порт `IBalanceConfig`).
Спринт 1.1.C: добавлен `InMemoryTokenBucketRateLimiter` (порт
`IRateLimiter`) — нужен `ThrottleMiddleware`. `build_dispatcher()`
собирает aiogram `Dispatcher` со стеком middleware-ов и роутерами;
`run()` — реальный entry point поллинга.
Спринт 1.1.D: добавлены SQLAlchemy-репозитории (`players / clans /
clan_members`) и use-case-ы (`RegisterPlayer / RegisterClan /
MigrateClanChatId / JoinClan / FreezeClan`). Use-case-ы прокидываются
в handler-ы через `dispatcher["..."] = ...` workflow-data.
Спринт 1.1.E: добавлены `SqlAlchemyAdminRepository`, use-case-ы
`GetProfile` (read-only карточка) и `ReloadBalance` (admin-only
hot-reload `balance.yaml`). `YamlBalanceLoader` прокидывается под
двумя ролями: `IBalanceConfig` (read-side) и `IBalanceReloader`
(write-side, ISP).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pipirik_wars.application.anticheat import LiftAnticheatBan
from pipirik_wars.application.balance import ReloadBalance
from pipirik_wars.application.clan import (
    FreezeClan,
    JoinClan,
    MigrateClanChatId,
    RegisterClan,
)
from pipirik_wars.application.daily_head import (
    IClanQuoteTemplateProvider,
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
from pipirik_wars.application.forest import (
    ApplyForestNameDrop,
    FinishForestRun,
    IForestFinishNotifier,
    StartForestRun,
)
from pipirik_wars.application.i18n import IMessageBundle, IPlayerLocaleResolver
from pipirik_wars.application.oracle import (
    InvokeOracle,
    IOracleTemplateProvider,
)
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
    IClanMassDuelHistoryQuery,
    IDuelLogTemplateProvider,
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
)
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.application.signup_queue import PromoteFromQueue
from pipirik_wars.application.top import (
    GetTopClans,
    GetTopPlayers,
    IClanTopQuery,
    ITopPlayersQuery,
)
from pipirik_wars.bot.handlers import register_routers
from pipirik_wars.bot.middlewares import register_middlewares
from pipirik_wars.bot.notifications import TelegramForestFinishNotifier
from pipirik_wars.domain.admin import IAdminRepository
from pipirik_wars.domain.anticheat import IAnticheatAdminAlerter, IAnticheatRepository
from pipirik_wars.domain.balance import IBalanceConfig, IBalanceReloader
from pipirik_wars.domain.clan import IClanMembershipRepository, IClanRepository
from pipirik_wars.domain.daily_head import (
    DailyHeadService,
    IDailyActivityRepository,
    IDailyHeadRepository,
)
from pipirik_wars.domain.dau import IDauCounter, IDauLimit, IDauThresholdAlerter
from pipirik_wars.domain.forest import IForestRunRepository
from pipirik_wars.domain.oracle import IOracleHistoryRepository
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.progression import ILengthGranter
from pipirik_wars.domain.pvp import IDuelRepository, IMassDuelRepository
from pipirik_wars.domain.pvp.lobby import IGlobalLobbyRepository
from pipirik_wars.domain.referral import IReferralRepository
from pipirik_wars.domain.security import IActivityLockRepository
from pipirik_wars.domain.shared.ports import (
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IIdempotencyKey,
    IRandom,
    IUnitOfWork,
)
from pipirik_wars.domain.signup_queue import ISignupQueueRepository
from pipirik_wars.infrastructure.anticheat import StructlogAnticheatAdminAlerter
from pipirik_wars.infrastructure.balance import YamlBalanceLoader
from pipirik_wars.infrastructure.cache import ClanTopCache, TopPlayersCache
from pipirik_wars.infrastructure.clock import RealClock
from pipirik_wars.infrastructure.dau import (
    InMemoryDauCounter,
    InMemoryDauLimit,
    StructlogDauThresholdAlerter,
)
from pipirik_wars.infrastructure.db.engine import build_engine, build_sessionmaker
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyActivityLockRepository,
    SqlAlchemyAdminRepository,
    SqlAlchemyAnticheatRepository,
    SqlAlchemyClanMassDuelHistoryQuery,
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
    SqlAlchemyDailyActivityRepository,
    SqlAlchemyDailyHeadRepository,
    SqlAlchemyDuelRepository,
    SqlAlchemyForestRunRepository,
    SqlAlchemyGlobalLobbyRepository,
    SqlAlchemyMassDuelRepository,
    SqlAlchemyOracleHistoryRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemyReferralRepository,
    SqlAlchemySignupQueueRepository,
)
from pipirik_wars.infrastructure.db.services import (
    SqlAlchemyAuditLogger,
    SqlAlchemyIdempotencyService,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.i18n import (
    FluentMessageBundle,
    PlayerLocaleResolverDB,
)
from pipirik_wars.infrastructure.random import RealRandom
from pipirik_wars.infrastructure.rate_limit import (
    InMemoryTokenBucketRateLimiter,
    IRateLimiter,
)
from pipirik_wars.infrastructure.scheduler import APSchedulerDelayedJobScheduler
from pipirik_wars.infrastructure.settings import Settings
from pipirik_wars.infrastructure.templates import (
    JsonClanQuoteTemplateProvider,
    JsonDuelLogTemplateProvider,
    JsonForestLogTemplateProvider,
    JsonOracleTemplateProvider,
)

# Путь к балансовому файлу по умолчанию (относительно cwd процесса).
# Деплой кладёт `config/balance.yaml` рядом с бинарём; локально
# pytest/`make ci` стартуют из корня репо, где он и лежит.
_DEFAULT_BALANCE_YAML = Path("config/balance.yaml")

# Каталог JSON-шаблонов (`oracle_<locale>.json`, Спринт 1.4.B). Файлы
# едут вместе с деплоем рядом с балансом — поэтому путь по умолчанию
# указывает на тот же `config/`.
_DEFAULT_TEMPLATES_DIR = Path("config/templates")

# Каталог `.ftl`-файлов локализации (Спринт 1.5.A). По умолчанию —
# `locales/` в корне репо/деплоя; на тестах путь подменяется через DI.
_DEFAULT_LOCALES_DIR = Path("locales")


@dataclass(frozen=True, slots=True)
class Container:
    """Контейнер инфраструктурных зависимостей и use-case-ов."""

    clock: IClock
    random: IRandom
    uow: IUnitOfWork
    idempotency: IIdempotencyKey
    audit: IAuditLogger
    balance: IBalanceConfig
    balance_reloader: IBalanceReloader
    rate_limiter: IRateLimiter
    settings: Settings

    # Репозитории (Спринт 1.1.D + 1.1.E + 1.2.C + 1.3.B)
    players: IPlayerRepository
    clans: IClanRepository
    clan_members: IClanMembershipRepository
    admins: IAdminRepository
    signup_queue: ISignupQueueRepository
    activity_locks: IActivityLockRepository
    forest_runs: IForestRunRepository
    oracle_history: IOracleHistoryRepository
    duels: IDuelRepository
    mass_duels: IMassDuelRepository
    global_lobby: IGlobalLobbyRepository
    referrals: IReferralRepository
    anticheat: IAnticheatRepository
    anticheat_admin_alerter: IAnticheatAdminAlerter

    # Шаблоны (Спринт 1.4.B / 1.5.G / 2.1.H)
    oracle_templates: IOracleTemplateProvider
    duel_log_templates: IDuelLogTemplateProvider

    # i18n (Спринт 1.5.A → 1.5.B → 1.5.F): локализованные
    # сообщения для handler-ов + резолвер языка игрока для middleware
    # и фоновых jobs.
    bundle: IMessageBundle
    player_locale_resolver: IPlayerLocaleResolver

    # Запросы (Спринт 1.4.C / 2.2.A)
    top_players_query: ITopPlayersQuery
    top_clans_query: IClanTopQuery
    clan_mass_duel_history_query: IClanMassDuelHistoryQuery

    # Планировщик отложенных задач (Спринт 1.3.C)
    delayed_jobs: IDelayedJobScheduler

    # DAU Gate (Спринт 1.2.B / 1.2.D)
    dau_counter: IDauCounter
    dau_limit: IDauLimit
    dau_threshold_alerter: IDauThresholdAlerter

    # Use-case-ы (Спринт 1.1.D + 1.1.E + 1.2.B + 1.2.C + 1.3.B)
    register_player: RegisterPlayer
    register_clan: RegisterClan
    migrate_clan: MigrateClanChatId
    join_clan: JoinClan
    freeze_clan: FreezeClan
    get_profile: GetProfile
    reload_balance: ReloadBalance
    set_player_locale: SetPlayerLocale
    get_dau_stats: GetDauStats
    set_max_dau: SetMaxDau
    promote_from_queue: PromoteFromQueue
    check_dau_threshold: CheckDauThreshold
    start_forest_run: StartForestRun
    finish_forest_run: FinishForestRun
    apply_forest_name_drop: ApplyForestNameDrop
    upgrade_thickness: UpgradeThickness
    invoke_oracle: InvokeOracle
    get_top_players: GetTopPlayers
    get_top_clans: GetTopClans
    get_clan_attack_history: GetClanAttackHistory
    add_length: ILengthGranter
    lift_anticheat_ban: LiftAnticheatBan

    # PvP 1×1 (Спринт 2.1.E)
    challenge_duel: ChallengeDuel
    accept_duel: AcceptDuel
    cancel_duel: CancelDuel
    submit_move: SubmitMove
    resolve_afk_round: ResolveAfkRound

    # PvP global lobby (Спринт 2.1.F.2)
    enqueue_global_duel: EnqueueGlobalDuel
    match_from_lobby: MatchFromLobby
    escalate_chat_to_global: EscalateChatToGlobal
    expire_lobby_entry: ExpireLobbyEntry

    # Mass-PvP клан×клан (Спринт 2.2.E)
    start_mass_duel: StartMassDuel
    submit_mass_move: SubmitMassMove
    resolve_mass_duel: ResolveMassDuel
    force_resolve_mass_duel: ForceResolveMassDuel
    cancel_mass_duel: CancelMassDuel

    # Daily Head «Глава клана дня» (Спринт 2.3)
    daily_heads: IDailyHeadRepository
    daily_activity: IDailyActivityRepository
    daily_head_service: DailyHeadService
    request_daily_head: RequestDailyHead
    run_daily_head_cron: RunDailyHeadCron
    record_player_activity: RecordPlayerActivity
    clan_quote_provider: IClanQuoteTemplateProvider
    schedule_daily_head_cron_jobs: ScheduleDailyHeadCronJobs

    # Реферальная система (Спринт 2.4.D)
    register_referral: RegisterReferral
    grant_referral_signup_bonus: GrantReferralSignupBonus
    grant_referral_thickness_milestone: GrantReferralThicknessMilestone


def build_container(  # noqa: PLR0915 — composition root, плоский DI-список оправдан
    settings: Settings | None = None,
    *,
    balance_yaml_path: Path | None = None,
    templates_dir: Path | None = None,
    locales_dir: Path | None = None,
    bot: Bot | None = None,
) -> Container:
    """Собрать контейнер для production-запуска.

    Production: настройки из env (через `pydantic-settings`).
    Tests: можно передать заранее собранный
    `Settings(db=DatabaseSettings(url=...))`.

    `balance_yaml_path` — переопределение пути к `balance.yaml`
    (по умолчанию ``config/balance.yaml``). Loader **lazy** — файл
    читается только при первом `container.balance.get()`.

    `bot` — опциональный aiogram-`Bot` для Sprint 1.3.D. Если передан —
    `delayed_jobs` получит `TelegramForestFinishNotifier`, и после
    `FinishForestRun.execute(...)` игроку придёт «вернулся из леса»
    (ГДД §8.2). Без `bot` (в unit-тестах и admin-flow) notifier = `None`,
    финиш работает как было раньше — сообщение не отправляется.

    NB: `create_async_engine()` lazy — реальное подключение к БД
    произойдёт только при первом запросе.
    """
    settings = settings or Settings()
    engine = build_engine(settings.db)
    session_maker = build_sessionmaker(engine)
    uow = SqlAlchemyUnitOfWork(session_maker)
    balance = YamlBalanceLoader(balance_yaml_path or _DEFAULT_BALANCE_YAML)
    clock = RealClock()
    audit = SqlAlchemyAuditLogger(uow=uow)
    rate_limiter = InMemoryTokenBucketRateLimiter(
        capacity=settings.bot.default_throttle_capacity,
        refill_per_second=settings.bot.default_throttle_per_second,
        clock=clock,
    )
    players = SqlAlchemyPlayerRepository(uow=uow)
    clans = SqlAlchemyClanRepository(uow=uow)
    clan_members = SqlAlchemyClanMembershipRepository(uow=uow)
    admins = SqlAlchemyAdminRepository(uow=uow)
    signup_queue = SqlAlchemySignupQueueRepository(uow=uow)
    activity_locks = SqlAlchemyActivityLockRepository(uow=uow)
    forest_runs = SqlAlchemyForestRunRepository(uow=uow, balance=balance)
    oracle_history = SqlAlchemyOracleHistoryRepository(uow=uow)
    duels = SqlAlchemyDuelRepository(uow=uow)
    mass_duels = SqlAlchemyMassDuelRepository(uow=uow)
    global_lobby = SqlAlchemyGlobalLobbyRepository(uow=uow)
    referrals = SqlAlchemyReferralRepository(uow=uow)
    anticheat = SqlAlchemyAnticheatRepository(uow=uow)
    anticheat_admin_alerter = StructlogAnticheatAdminAlerter()
    oracle_templates = JsonOracleTemplateProvider(
        templates_dir=templates_dir or _DEFAULT_TEMPLATES_DIR,
    )
    forest_log_templates = JsonForestLogTemplateProvider(
        templates_dir=templates_dir or _DEFAULT_TEMPLATES_DIR,
    )
    duel_log_templates = JsonDuelLogTemplateProvider(
        templates_dir=templates_dir or _DEFAULT_TEMPLATES_DIR,
    )
    clan_quote_provider = JsonClanQuoteTemplateProvider(
        templates_dir=templates_dir or _DEFAULT_TEMPLATES_DIR,
    )
    bundle = FluentMessageBundle(locales_dir=locales_dir or _DEFAULT_LOCALES_DIR)
    player_locale_resolver = PlayerLocaleResolverDB(uow=uow)
    top_players_query = TopPlayersCache(
        uow=uow,
        players=players,
        balance=balance,
        clock=clock,
        ttl_seconds=60,
    )
    top_clans_query = ClanTopCache(
        uow=uow,
        clans=clans,
        clock=clock,
        ttl_seconds=60,
    )
    clan_mass_duel_history_query = SqlAlchemyClanMassDuelHistoryQuery(uow=uow)
    dau_counter = InMemoryDauCounter(clock=clock)
    dau_limit = InMemoryDauLimit(initial=settings.bot.max_dau)
    dau_threshold_alerter = StructlogDauThresholdAlerter()
    idempotency = SqlAlchemyIdempotencyService(uow=uow)
    check_dau_threshold = CheckDauThreshold(
        uow=uow,
        dau_counter=dau_counter,
        dau_limit=dau_limit,
        idempotency=idempotency,
        audit=audit,
        alerter=dau_threshold_alerter,
        clock=clock,
    )
    register_player = RegisterPlayer(
        uow=uow,
        players=players,
        signup_queue=signup_queue,
        dau_counter=dau_counter,
        dau_limit=dau_limit,
        audit=audit,
        clock=clock,
        check_threshold=check_dau_threshold,
    )
    register_clan = RegisterClan(
        uow=uow,
        clans=clans,
        audit=audit,
        clock=clock,
    )
    migrate_clan = MigrateClanChatId(
        uow=uow,
        clans=clans,
        audit=audit,
        clock=clock,
    )
    join_clan = JoinClan(
        uow=uow,
        clans=clans,
        clan_members=clan_members,
        players=players,
        audit=audit,
        clock=clock,
    )
    freeze_clan = FreezeClan(
        uow=uow,
        clans=clans,
        audit=audit,
        clock=clock,
    )
    get_profile = GetProfile(
        uow=uow,
        players=players,
        balance=balance,
    )
    reload_balance = ReloadBalance(
        uow=uow,
        admins=admins,
        balance=balance,
        reloader=balance,
        audit=audit,
        clock=clock,
    )
    get_dau_stats = GetDauStats(counter=dau_counter, limit=dau_limit)
    set_max_dau = SetMaxDau(
        uow=uow,
        admins=admins,
        limit=dau_limit,
        audit=audit,
        clock=clock,
    )
    promote_from_queue = PromoteFromQueue(
        uow=uow,
        players=players,
        signup_queue=signup_queue,
        dau_counter=dau_counter,
        dau_limit=dau_limit,
        audit=audit,
        clock=clock,
        check_threshold=check_dau_threshold,
    )
    activity_lock_service = ActivityLockService(
        repository=activity_locks,
        clock=clock,
    )
    # AddLength — единая точка прибавки длины (Спринт 1.6.D / 1.6.F).
    # Конструируем рано, чтобы переиспользовать в use-case-ах FinishForestRun
    # / InvokeOracle / ... как `ILengthGranter`.
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
    forest_notifier: IForestFinishNotifier | None = None
    if bot is not None:
        forest_notifier = TelegramForestFinishNotifier(
            bot=bot,
            players=players,
            balance=balance,
            uow=uow,
            bundle=bundle,
            log_templates=forest_log_templates,
            random=RealRandom(),
            locale_resolver=player_locale_resolver,
        )
    # Late-bound фабрики для PvP-lobby job-ов: scheduler нужен раньше,
    # чем `escalate_chat_to_global` / `expire_lobby_entry`, поэтому передаём
    # лямбды-замыкания, которые резолвятся при срабатывании job-а — после
    # того, как `build_container` уже вернулся и Container собран.
    delayed_jobs = APSchedulerDelayedJobScheduler(
        scheduler=AsyncIOScheduler(),
        finish_factory=lambda: finish_forest_run,
        notifier=forest_notifier,
        escalate_factory=lambda: escalate_chat_to_global,
        expire_factory=lambda: expire_lobby_entry,
        afk_resolution_factory=lambda: resolve_afk_round,
        mass_duel_afk_factory=lambda: force_resolve_mass_duel,
        daily_head_cron_factory=lambda: run_daily_head_cron,
        daily_reschedule_factory=lambda: schedule_daily_head_cron_jobs,
    )
    start_forest_run = StartForestRun(
        uow=uow,
        players=players,
        runs=forest_runs,
        locks=activity_lock_service,
        balance=balance,
        random=RealRandom(),
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    apply_forest_name_drop = ApplyForestNameDrop(
        uow=uow,
        players=players,
        runs=forest_runs,
        audit=audit,
        clock=clock,
    )
    upgrade_thickness = UpgradeThickness(
        uow=uow,
        players=players,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    invoke_oracle = InvokeOracle(
        uow=uow,
        players=players,
        history=oracle_history,
        templates=oracle_templates,
        balance=balance,
        random=RealRandom(),
        length_granter=add_length,
        clock=clock,
    )
    get_top_players = GetTopPlayers(query=top_players_query)
    get_top_clans = GetTopClans(query=top_clans_query)
    get_clan_attack_history = GetClanAttackHistory(query=clan_mass_duel_history_query)
    set_player_locale = SetPlayerLocale(
        uow=uow,
        players=players,
        audit=audit,
        clock=clock,
    )
    # /anticheat_unban (Спринт 1.6.G) — admin-команда снятия soft-ban-а.
    lift_anticheat_ban = LiftAnticheatBan(
        uow=uow,
        admins=admins,
        players=players,
        audit=audit,
        clock=clock,
    )
    # PvP 1×1 use-cases (Спринт 2.1.D, ГДД §7.1)
    # Спринт 2.1.F.2: в ChallengeDuel/AcceptDuel/CancelDuel дополнительно
    # пробрасываем scheduler + lobby (эскалация / TTL / очистка лобби).
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
        random=RealRandom(),
        audit=audit,
        clock=clock,
        balance=balance,
        scheduler=delayed_jobs,
    )
    # PvP global lobby use-cases (Спринт 2.1.F.2, ГДД §7.1).
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
        clan_members=clan_members,
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
        random=RealRandom(),
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
        random=RealRandom(),
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
    # Daily Head «Глава клана дня» (Спринт 2.3.C). Доменный сервис
    # `DailyHeadService` чистый — фактические side-effects (запись в
    # `daily_heads`, +len через `add_length`, audit `DAILY_HEAD_ASSIGN`)
    # выполняют use-case-ы.
    daily_heads = SqlAlchemyDailyHeadRepository(uow=uow)
    daily_activity = SqlAlchemyDailyActivityRepository(uow=uow, clock=clock)
    # `DailyHeadService` принимает `BalanceConfig`-снапшот (а не loader-port),
    # потому что доменный сервис должен быть чистым — `IBalanceConfig` живёт в
    # domain.balance.ports, но снимок берём один раз на старте процесса.
    # Hot-reload `daily_head`-секции потребует перезапуска бота — это
    # сознательный trade-off (раздел 2.3 редко крутится).
    daily_head_service = DailyHeadService(
        balance=balance.get(),
        clock=clock,
        random=RealRandom(),
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
    register_referral = RegisterReferral(
        uow=uow,
        players=players,
        referrals=referrals,
        clock=clock,
    )
    grant_referral_signup_bonus = GrantReferralSignupBonus(
        uow=uow,
        players=players,
        referrals=referrals,
        length_granter=add_length,
        balance=balance,
        clock=clock,
    )
    grant_referral_thickness_milestone = GrantReferralThicknessMilestone(
        uow=uow,
        players=players,
        referrals=referrals,
        length_granter=add_length,
        balance=balance,
    )
    return Container(
        clock=clock,
        random=RealRandom(),
        uow=uow,
        idempotency=idempotency,
        audit=audit,
        balance=balance,
        balance_reloader=balance,
        rate_limiter=rate_limiter,
        settings=settings,
        players=players,
        clans=clans,
        clan_members=clan_members,
        admins=admins,
        signup_queue=signup_queue,
        activity_locks=activity_locks,
        forest_runs=forest_runs,
        oracle_history=oracle_history,
        duels=duels,
        mass_duels=mass_duels,
        global_lobby=global_lobby,
        referrals=referrals,
        anticheat=anticheat,
        anticheat_admin_alerter=anticheat_admin_alerter,
        oracle_templates=oracle_templates,
        duel_log_templates=duel_log_templates,
        bundle=bundle,
        player_locale_resolver=player_locale_resolver,
        top_players_query=top_players_query,
        top_clans_query=top_clans_query,
        clan_mass_duel_history_query=clan_mass_duel_history_query,
        delayed_jobs=delayed_jobs,
        dau_counter=dau_counter,
        dau_limit=dau_limit,
        dau_threshold_alerter=dau_threshold_alerter,
        register_player=register_player,
        register_clan=register_clan,
        migrate_clan=migrate_clan,
        join_clan=join_clan,
        freeze_clan=freeze_clan,
        get_profile=get_profile,
        reload_balance=reload_balance,
        set_player_locale=set_player_locale,
        get_dau_stats=get_dau_stats,
        set_max_dau=set_max_dau,
        promote_from_queue=promote_from_queue,
        check_dau_threshold=check_dau_threshold,
        start_forest_run=start_forest_run,
        finish_forest_run=finish_forest_run,
        apply_forest_name_drop=apply_forest_name_drop,
        upgrade_thickness=upgrade_thickness,
        invoke_oracle=invoke_oracle,
        get_top_players=get_top_players,
        get_top_clans=get_top_clans,
        get_clan_attack_history=get_clan_attack_history,
        add_length=add_length,
        lift_anticheat_ban=lift_anticheat_ban,
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
        clan_quote_provider=clan_quote_provider,
        schedule_daily_head_cron_jobs=schedule_daily_head_cron_jobs,
        register_referral=register_referral,
        grant_referral_signup_bonus=grant_referral_signup_bonus,
        grant_referral_thickness_milestone=grant_referral_thickness_milestone,
    )


def build_dispatcher(container: Container) -> Dispatcher:  # noqa: PLR0915 — composition root, плоский DI-список оправдан
    """Собрать aiogram `Dispatcher` со стеком middleware-ов и роутерами.

    Use-case-ы регистрируются в `dispatcher` workflow-data — aiogram
    автоматически пробросит их в handler-ы по имени параметра.
    """
    dispatcher = Dispatcher()
    register_middlewares(
        dispatcher,
        limiter=container.rate_limiter,
        record_player_activity=container.record_player_activity,
        player_locale_resolver=container.player_locale_resolver,
    )
    register_routers(dispatcher)
    # Workflow-data DI: aiogram сам пробросит их в handler-ы по имени.
    dispatcher["register_player"] = container.register_player
    dispatcher["register_clan"] = container.register_clan
    dispatcher["migrate_clan"] = container.migrate_clan
    dispatcher["join_clan"] = container.join_clan
    dispatcher["freeze_clan"] = container.freeze_clan
    dispatcher["get_profile"] = container.get_profile
    dispatcher["reload_balance"] = container.reload_balance
    dispatcher["get_dau_stats"] = container.get_dau_stats
    dispatcher["set_max_dau"] = container.set_max_dau
    dispatcher["signup_queue"] = container.signup_queue
    dispatcher["promote_from_queue"] = container.promote_from_queue
    dispatcher["start_forest_run"] = container.start_forest_run
    dispatcher["finish_forest_run"] = container.finish_forest_run
    dispatcher["apply_forest_name_drop"] = container.apply_forest_name_drop
    dispatcher["upgrade_thickness"] = container.upgrade_thickness
    dispatcher["invoke_oracle"] = container.invoke_oracle
    dispatcher["get_top_players"] = container.get_top_players
    dispatcher["get_top_clans"] = container.get_top_clans
    dispatcher["balance"] = container.balance
    dispatcher["clock"] = container.clock
    dispatcher["bundle"] = container.bundle
    dispatcher["set_player_locale"] = container.set_player_locale
    dispatcher["lift_anticheat_ban"] = container.lift_anticheat_ban
    # PvP 1×1 (Спринт 2.1.E) — use-cases + репо/резолвер для handler-ов.
    dispatcher["challenge_duel"] = container.challenge_duel
    dispatcher["accept_duel"] = container.accept_duel
    dispatcher["cancel_duel"] = container.cancel_duel
    dispatcher["submit_move"] = container.submit_move
    dispatcher["resolve_afk_round"] = container.resolve_afk_round
    # PvP global lobby (Спринт 2.1.F.2) — use-cases для handler-ов F.3.
    dispatcher["enqueue_global_duel"] = container.enqueue_global_duel
    dispatcher["match_from_lobby"] = container.match_from_lobby
    dispatcher["players"] = container.players
    dispatcher["player_locale_resolver"] = container.player_locale_resolver
    # PvP round-flavour + share (Спринт 2.1.H) — провайдер JSON-каталога
    # раунд-логов, RNG для выбора шаблона, `duels` для share-handler-а
    # (нужно подгрузить дуэль по `duel_id` из callback_data).
    dispatcher["duel_log_templates"] = container.duel_log_templates
    dispatcher["pvp_random"] = container.random
    dispatcher["duels"] = container.duels
    # Share-кнопка под результатом /forest (Спринт 2.4.D-b) — handler
    # подгружает `ForestRun` по `run_id` из callback_data `ref-share:forest:{id}`.
    dispatcher["forest_runs"] = container.forest_runs
    # Mass-PvP клан×клан (Спринт 2.2.F) — use-cases + clans для handler-ов.
    dispatcher["start_mass_duel"] = container.start_mass_duel
    dispatcher["submit_mass_move"] = container.submit_mass_move
    dispatcher["resolve_mass_duel"] = container.resolve_mass_duel
    dispatcher["clans"] = container.clans
    # Журнал клановых атак (Спринт 2.2.G) — read-side use-case для handler-а.
    dispatcher["get_clan_attack_history"] = container.get_clan_attack_history
    # Daily Head (Спринт 2.3.C) — button-trigger use-case для handler-а 2.3.E.
    # `run_daily_head_cron` пробрасывается в шедулер (2.3.F), но также
    # доступен в dispatcher для админ-команд / диагностики.
    dispatcher["request_daily_head"] = container.request_daily_head
    dispatcher["run_daily_head_cron"] = container.run_daily_head_cron
    dispatcher["record_player_activity"] = container.record_player_activity
    dispatcher["clan_quote_provider"] = container.clan_quote_provider
    # Реферальная система (Спринт 2.4.D) — use-cases для /start ref_<id>
    # и /upgrade_thickness handler-ов.
    dispatcher["register_referral"] = container.register_referral
    dispatcher["grant_referral_signup_bonus"] = container.grant_referral_signup_bonus
    dispatcher["grant_referral_thickness_milestone"] = container.grant_referral_thickness_milestone
    return dispatcher


# Какие апдейты слушать через long-polling.
# `chat_member` нужен для acceptance 1.1.5 (auto-join). Без него
# Telegram не доставляет события про не-бот-пользователей.
_ALLOWED_UPDATES = (
    "message",
    "callback_query",
    "my_chat_member",
    "chat_member",
)


async def run(
    settings: Settings | None = None,
    *,
    balance_yaml_path: Path | None = None,
) -> None:
    """Точка входа production-поллинга.

    Создаёт `Bot` (HTML parse_mode по умолчанию), `Dispatcher` со всем
    стеком middleware-ов и роутерами, запускает long-polling. Завершается
    корректно через `await bot.session.close()`.
    """
    # `Settings()` выносим на этот уровень — `Bot` нужен для notifier-а
    # внутри `build_container`, поэтому сначала settings → bot → container.
    settings = settings or Settings()
    bot = Bot(
        token=settings.bot.token.get_secret_value(),
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    container = build_container(
        settings,
        balance_yaml_path=balance_yaml_path,
        bot=bot,
    )
    dispatcher = build_dispatcher(container)
    scheduler = container.delayed_jobs
    if isinstance(scheduler, APSchedulerDelayedJobScheduler):
        scheduler.start()
        # Bootstrap: пере-зарегистрировать сегодняшние per-clan
        # daily-head-cron-job-ы (in-memory job-store APScheduler пуст
        # при рестарте). Также включаем ежедневный cron 00:01 МСК,
        # который сам перепланирует на новые сутки (Спринт 2.3.F.2).
        await container.schedule_daily_head_cron_jobs.execute()
        scheduler.schedule_daily_head_reschedule_cron()
    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=list(_ALLOWED_UPDATES),
        )
    finally:
        if isinstance(scheduler, APSchedulerDelayedJobScheduler):
            scheduler.shutdown(wait=False)
        await bot.session.close()


def main() -> None:  # pragma: no cover
    """Sync wrapper над `run()`. Используется как ``python -m``-entry."""
    asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    main()
