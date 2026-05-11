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
import secrets
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
    IBroadcastSender,
    IBroadcastTaskSpawner,
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
    IBossFightFinishNotifier,
    IBossLobbyCloseNotifier,
    IBossRoundTickNotifier,
    JoinBossLobby,
    LeaveBossLobby,
    RunBossRound,
    SummonBoss,
)
from pipirik_wars.application.caravans import (
    CancelCaravan,
    CloseCaravanLobby,
    CreateCaravan,
    FinishCaravanBattle,
    ICaravanBattleFinishNotifier,
    ICaravanLobbyCloseNotifier,
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
from pipirik_wars.application.dungeon import (
    FinishDungeonRun,
    IDungeonFinishNotifier,
    StartDungeonRun,
)
from pipirik_wars.application.forest import (
    ApplyForestNameDrop,
    FinishForestRun,
    IForestFinishNotifier,
    StartForestRun,
)
from pipirik_wars.application.i18n import IMessageBundle, IPlayerLocaleResolver
from pipirik_wars.application.inventory import EnchantItem, GetInventory
from pipirik_wars.application.monetization import (
    GeneratePrizeLots,
    RecordDonation,
    SpinPaidRoulette,
)
from pipirik_wars.application.mountains import (
    FinishMountainRun,
    IMountainFinishNotifier,
    StartMountainRun,
)
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
    IWeeklyClanReferralSummaryNotifier,
    RegisterReferral,
    RunWeeklyClanReferralSummary,
)
from pipirik_wars.application.roulette import SpinFreeRoulette
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.application.signup_queue import PromoteFromQueue
from pipirik_wars.application.top import (
    GetTopClans,
    GetTopPlayers,
    IClanTopQuery,
    ITopPlayersQuery,
)
from pipirik_wars.bot.handlers import register_routers
from pipirik_wars.bot.middlewares import AdminGuard, register_middlewares
from pipirik_wars.bot.notifications import (
    TelegramBossFightFinishNotifier,
    TelegramBossLobbyCloseNotifier,
    TelegramBossRoundTickNotifier,
    TelegramCaravanBattleFinishNotifier,
    TelegramCaravanLobbyCloseNotifier,
    TelegramDungeonFinishNotifier,
    TelegramForestFinishNotifier,
    TelegramMountainFinishNotifier,
    TelegramWeeklyClanReferralSummaryNotifier,
)
from pipirik_wars.domain.admin import (
    IAdminAuditLogger,
    IAdminAuditQuery,
    IAdminAuthorizationPolicy,
    IAdminConfirmStore,
    IAdminRepository,
    ITotpSecretGenerator,
    ITotpVerifier,
    RoleBasedAdminAuthorizationPolicy,
)
from pipirik_wars.domain.anticheat import IAnticheatAdminAlerter, IAnticheatRepository
from pipirik_wars.domain.balance import IBalanceConfig, IBalanceReloader
from pipirik_wars.domain.bosses import (
    IBossFightRepository,
    IBossParticipantRepository,
)
from pipirik_wars.domain.caravan import (
    ICaravanParticipantRepository,
    ICaravanRepository,
)
from pipirik_wars.domain.clan import IClanMembershipRepository, IClanRepository
from pipirik_wars.domain.daily_head import (
    DailyHeadService,
    IDailyActivityRepository,
    IDailyHeadRepository,
)
from pipirik_wars.domain.dau import IDauCounter, IDauLimit, IDauThresholdAlerter
from pipirik_wars.domain.dungeon import IDungeonRunRepository
from pipirik_wars.domain.forest import IForestRunRepository
from pipirik_wars.domain.inventory import (
    IEnchantHistoryReader,
    IItemRepository,
    IScrollRepository,
)
from pipirik_wars.domain.monetization import IPaymentLedger, IPrizePoolRepository
from pipirik_wars.domain.mountains import IMountainRunRepository
from pipirik_wars.domain.oracle import IOracleHistoryRepository
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.progression import ILengthGranter
from pipirik_wars.domain.pvp import IDuelRepository, IMassDuelRepository
from pipirik_wars.domain.pvp.lobby import IGlobalLobbyRepository
from pipirik_wars.domain.referral import IReferralRepository
from pipirik_wars.domain.roulette import IRouletteSpinRepository
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
from pipirik_wars.infrastructure.admin import (
    InMemoryAdminConfirmStore,
    PyOtpTotpSecretGenerator,
    PyOtpTotpVerifier,
)
from pipirik_wars.infrastructure.anticheat import StructlogAnticheatAdminAlerter
from pipirik_wars.infrastructure.balance import YamlBalanceLoader
from pipirik_wars.infrastructure.balance.writer import YamlBalanceWriter
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
    SqlAlchemyBossFightRepository,
    SqlAlchemyBossParticipantRepository,
    SqlAlchemyCaravanParticipantRepository,
    SqlAlchemyCaravanRepository,
    SqlAlchemyClanMassDuelHistoryQuery,
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
    SqlAlchemyOracleHistoryRepository,
    SqlAlchemyPaymentLedger,
    SqlAlchemyPlayerRepository,
    SqlAlchemyPrizeLotRepository,
    SqlAlchemyPrizePoolRepository,
    SqlAlchemyReferralRepository,
    SqlAlchemyRouletteSpinRepository,
    SqlAlchemyScrollRepository,
    SqlAlchemySignupQueueRepository,
)
from pipirik_wars.infrastructure.db.services import (
    SqlAlchemyAdminAuditLogger,
    SqlAlchemyAdminAuditQuery,
    SqlAlchemyAuditLogger,
    SqlAlchemyIdempotencyService,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.fees import InMemoryFeeEstimator
from pipirik_wars.infrastructure.i18n import (
    FluentMessageBundle,
    PlayerLocaleResolverDB,
)
from pipirik_wars.infrastructure.random import RealRandom, SeededRandom
from pipirik_wars.infrastructure.rate_limit import (
    InMemoryTokenBucketRateLimiter,
    IRateLimiter,
)
from pipirik_wars.infrastructure.scheduler import APSchedulerDelayedJobScheduler
from pipirik_wars.infrastructure.settings import Settings
from pipirik_wars.infrastructure.telegram.broadcast import (
    AiogramBroadcastSender,
    AsyncIOBroadcastTaskSpawner,
    NoopBroadcastSender,
)
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

# Длина URL-safe токена `RequestAdminConfirm` (Спринт 2.5-A.3, ГДД §18.6).
# 16 байт ≈ 22-символьный URL-safe токен — достаточно стойкий для одноразовой
# 60-секундной аутентификации, и при этом помещается в одну строку чата.
_ADMIN_CONFIRM_TOKEN_BYTES = 16


def _default_admin_token_factory() -> str:
    """Production-фабрика одноразовых токенов для `RequestAdminConfirm`."""
    return secrets.token_urlsafe(_ADMIN_CONFIRM_TOKEN_BYTES)


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
    mountain_runs: IMountainRunRepository
    dungeon_runs: IDungeonRunRepository
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
    # PvE-походы (Спринт 3.1-B, ГДД §8). Bot-handler-ы /mountains и
    # /dungeon — в Спринте 3.1-E. Сейчас use-case-ы и репозитории
    # доступны через Container, но в dispatcher не пробрасываются.
    start_mountain_run: StartMountainRun
    finish_mountain_run: FinishMountainRun
    start_dungeon_run: StartDungeonRun
    finish_dungeon_run: FinishDungeonRun
    # Караваны (Спринт 3.2, ГДД §9). 3.2-B — use-case-ы + persistence;
    # bot-handler-ы /caravan_create, /caravan_join, /caravan_leave — 3.2-D.
    caravans: ICaravanRepository
    caravan_participants: ICaravanParticipantRepository
    create_caravan: CreateCaravan
    join_caravan_lobby: JoinCaravanLobby
    leave_caravan_lobby: LeaveCaravanLobby
    cancel_caravan: CancelCaravan
    close_caravan_lobby: CloseCaravanLobby
    # Рейд-боссы (Спринт 3.3, ГДД §10). 3.3-B — use-case-ы + persistence;
    # 3.3-C — боевая механика (`RunBossRound` / `FinishBossFight`) +
    # scroll-drops; bot-handler `/boss` — 3.3-D. До тех пор use-case-ы
    # доступны через Container, но в dispatcher не пробрасываются.
    boss_fights: IBossFightRepository
    boss_participants: IBossParticipantRepository
    summon_boss: SummonBoss
    join_boss_lobby: JoinBossLobby
    leave_boss_lobby: LeaveBossLobby
    cancel_boss_fight: CancelBossFight
    close_boss_lobby: CloseBossLobby
    run_boss_round: RunBossRound
    finish_boss_fight: FinishBossFight
    # Инвентарь и заточка (Спринт 3.4, ГДД §2.6 + §2.8). 3.4-A/B/C — домен
    # + persistence + use-case заточки + audit + trip-wire. 3.4-D —
    # /inventory + /enchant + presenter-ы + handler-ы. Репо и use-case-ы
    # пробрасываются в dispatcher в build_dispatcher (3.4-D спринт).
    items: IItemRepository
    scrolls: IScrollRepository
    enchant_history: IEnchantHistoryReader
    enchant_item: EnchantItem
    get_inventory: GetInventory
    # Free-to-play рулетка (Спринт 3.5-B/C/D, ГДД §12.4). 3.5-B —
    # `IRouletteSpinRepository` + персистентный append-only лог `roulette_spins`.
    # 3.5-C — use-case `SpinFreeRoulette` (10-step flow с гейтами,
    # cost-deduction, outcome-pick, награждением). 3.5-D — bot-handler
    # `/roulette_free` (личка-only) + spin-callback. `spin_free_roulette`
    # пробрасывается в dispatcher через workflow-data в build_dispatcher.
    roulette_spins: IRouletteSpinRepository
    spin_free_roulette: SpinFreeRoulette
    # Платная рулетка (Спринт 4.1-A, ГДД §12.5). A.5 — `payment_ledger`
    # (`SqlAlchemyPaymentLedger`, append-only ledger в `payments`-таблице
    # с idempotency по `(player_id, idempotency_key)`-индексу). A.6 —
    # use-case `SpinPaidRoulette` (платный 10-step flow: idempotency,
    # player load, thickness gate, charge, payment-audit, n-spin pick,
    # spin-record, spin-audit, length-grant on LENGTH, idempotency-mark)
    # + handler `/roulette_paid` с TG Stars invoice + pre_checkout +
    # successful_payment-callback.
    payment_ledger: IPaymentLedger
    spin_paid_roulette: SpinPaidRoulette
    # Призовой пул (Спринт 4.1-B, ГДД §12.6). B.3 — `prize_pool_repo`
    # (`SqlAlchemyPrizePoolRepository`, атомарный UPDATE по ряду в
    # `prize_pool_balance`-таблице + initial-seed-ряды на каждую
    # валюту). B.5 — use-case `RecordDonation` (10% с `IPaymentLedger.charge`-
    # а идет в пул + audit-запись `PRIZE_POOL_INCREMENT` в той же UoW).
    # Интегрирован в `SpinPaidRoulette` (Step 5b в 10-step flow-е).
    prize_pool_repo: IPrizePoolRepository
    record_donation: RecordDonation
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

    # Реферальная система (Спринт 2.4.D + 2.4.E)
    register_referral: RegisterReferral
    grant_referral_signup_bonus: GrantReferralSignupBonus
    grant_referral_thickness_milestone: GrantReferralThicknessMilestone
    run_weekly_clan_referral_summary: RunWeeklyClanReferralSummary

    # Расширенный админ-интерфейс (Спринт 2.5-A + 2.5-B).
    # `admin_audit` — write-side для use-case-ов admin-команд (отдельная
    # таблица `admin_audit_log`, не общий `audit_log`).
    # `admin_confirm_store` — singleton in-memory TTL-store ожидающих
    # TOTP-токенов; переживать рестарт смысла нет (60-секундные токены
    # сгорают сразу после рестарта). `totp_verifier` — обёртка над
    # `pyotp.TOTP.verify()`. Подробнее — `infrastructure/admin/__init__.py`.
    admin_audit: IAdminAuditLogger
    admin_audit_query: IAdminAuditQuery
    admin_confirm_store: IAdminConfirmStore
    totp_verifier: ITotpVerifier
    totp_secret_generator: ITotpSecretGenerator
    admin_authz: IAdminAuthorizationPolicy
    find_players: FindPlayers
    get_player_card: GetPlayerCard
    freeze_player: FreezePlayer
    unfreeze_player: UnfreezePlayer
    ban_player: BanPlayer
    request_admin_confirm: RequestAdminConfirm
    verify_admin_confirm: VerifyAdminConfirm
    grant_length: GrantLength
    grant_thickness: GrantThickness
    get_balance_value: GetBalanceValue
    set_balance_value: SetBalanceValue
    # Спринт 2.5-D.5: read-side observability — `/audit`-листинг.
    get_admin_audit_trail: GetAdminAuditTrail
    # Спринт 2.5-D.1: read-side карточка клана — `/clan`.
    get_clan_card: GetClanCard
    # Спринт 2.5-D.2: ручная заморозка/разморозка клана админом.
    freeze_clan_admin: FreezeClanAdmin
    unfreeze_clan_admin: UnfreezeClanAdmin
    # Спринт 2.5-D.3: read-only история daily-head назначений клана.
    get_clan_daily_head_history: GetClanDailyHeadHistory
    # Спринт 2.5-D.4: `/announce` — broadcast с TOTP-confirm.
    broadcast_announcement: BroadcastAnnouncement
    run_broadcast_announcement: RunBroadcastAnnouncement
    broadcast_sender: IBroadcastSender
    broadcast_task_spawner: IBroadcastTaskSpawner
    # Спринт 2.5-D.6: self-service выдача TOTP-секрета (`/admin_setup_totp`).
    setup_admin_totp: SetupAdminTotp


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
    # Отдельный rate-limiter под антифрод реферальной системы (Спринт 2.4.F).
    # Bucket: capacity=N, refill = N / 3600 в секунду (т.е. ≈ N новых в час).
    referral_rate_limiter = InMemoryTokenBucketRateLimiter(
        capacity=settings.bot.referral_rate_limit_capacity,
        refill_per_second=(settings.bot.referral_rate_limit_refill_per_hour / 3600.0),
        clock=clock,
    )
    players = SqlAlchemyPlayerRepository(uow=uow)
    clans = SqlAlchemyClanRepository(uow=uow)
    clan_members = SqlAlchemyClanMembershipRepository(uow=uow)
    admins = SqlAlchemyAdminRepository(uow=uow)
    signup_queue = SqlAlchemySignupQueueRepository(uow=uow)
    activity_locks = SqlAlchemyActivityLockRepository(uow=uow)
    forest_runs = SqlAlchemyForestRunRepository(uow=uow, balance=balance)
    mountain_runs = SqlAlchemyMountainRunRepository(uow=uow, balance=balance)
    dungeon_runs = SqlAlchemyDungeonRunRepository(uow=uow, balance=balance)
    # Спринт 3.2-B: караван (ГДД §9). Bot-handler-ы /caravan_create,
    # /caravan_join, /caravan_leave — 3.2-D. До тех пор use-case-ы
    # доступны через Container; APScheduler-job
    # `caravan_lobby_close` ходит через `close_caravan_lobby_factory`.
    caravans = SqlAlchemyCaravanRepository(uow=uow)
    caravan_participants = SqlAlchemyCaravanParticipantRepository(uow=uow)
    # Спринт 3.3-B: рейд-боссы (ГДД §10). Bot-handler `/boss` — 3.3-D.
    # До тех пор use-case-ы доступны через Container; APScheduler-job
    # `boss_lobby_close` ходит через `boss_lobby_close_factory`.
    boss_fights = SqlAlchemyBossFightRepository(uow=uow)
    boss_participants = SqlAlchemyBossParticipantRepository(uow=uow)
    # Спринт 3.4-B/C: инвентарь (ГДД §2.6) + заточка (§2.8).
    # `items` — реализация `IItemRepository`, `scrolls` —
    # `IScrollRepository` (UPSERT-стэки), `enchant_history` —
    # `IEnchantHistoryReader` (read-only скан audit-лога для trip-wire-а).
    # Bot-handler-ы /inventory + /enchant их пробрасывают через dispatcher
    # workflow-data (3.4-D).
    items = SqlAlchemyItemRepository(uow=uow, balance=balance)
    scrolls = SqlAlchemyScrollRepository(uow=uow)
    enchant_history = SqlAlchemyEnchantHistoryReader(uow=uow)
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
    # Расширенный админ-интерфейс (Спринт 2.5-A + 2.5-B + 2.5-D) — admin-audit
    # и RBAC-политика. Определяем раньше use-case-ов, которые их
    # инжектят (`ReloadBalance`/`SetMaxDau`/`LiftAnticheatBan` в D.7,
    # плюс все D.8-use-case-ы ниже).
    admin_audit = SqlAlchemyAdminAuditLogger(uow=uow)
    admin_authz: IAdminAuthorizationPolicy = RoleBasedAdminAuthorizationPolicy()
    reload_balance = ReloadBalance(
        uow=uow,
        admins=admins,
        balance=balance,
        reloader=balance,
        audit=audit,
        admin_audit=admin_audit,
        authz=admin_authz,
        clock=clock,
    )
    get_dau_stats = GetDauStats(counter=dau_counter, limit=dau_limit)
    set_max_dau = SetMaxDau(
        uow=uow,
        admins=admins,
        limit=dau_limit,
        audit=audit,
        admin_audit=admin_audit,
        authz=admin_authz,
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
    weekly_referral_summary_notifier: IWeeklyClanReferralSummaryNotifier | None = None
    mountain_notifier: IMountainFinishNotifier | None = None
    dungeon_notifier: IDungeonFinishNotifier | None = None
    caravan_lobby_close_notifier: ICaravanLobbyCloseNotifier | None = None
    caravan_battle_finish_notifier: ICaravanBattleFinishNotifier | None = None
    boss_lobby_close_notifier: IBossLobbyCloseNotifier | None = None
    boss_round_tick_notifier: IBossRoundTickNotifier | None = None
    boss_fight_finish_notifier: IBossFightFinishNotifier | None = None
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
        weekly_referral_summary_notifier = TelegramWeeklyClanReferralSummaryNotifier(
            bot=bot,
            bundle=bundle,
            balance=balance,
        )
        # Спринт 3.1-E: PvE-нотификаторы. Доставка best-effort,
        # локаль из `users.locale_override` через `player_locale_resolver`,
        # фолбэк на EN.
        mountain_notifier = TelegramMountainFinishNotifier(
            bot=bot,
            balance=balance,
            bundle=bundle,
            locale_resolver=player_locale_resolver,
        )
        dungeon_notifier = TelegramDungeonFinishNotifier(
            bot=bot,
            balance=balance,
            bundle=bundle,
            locale_resolver=player_locale_resolver,
        )
        # Спринт 3.2-D D.6: caravan-нотификаторы старта/финиша боя.
        # Шлют посты в чаты `sender_clan.chat_id` / `receiver_clan.chat_id`
        # после `LOBBY → IN_BATTLE` (lobby_close) и `IN_BATTLE → FINISHED`
        # (battle_finish). Доставка best-effort, локаль лидера резолвится
        # через `player_locale_resolver` с фолбэком на EN.
        caravan_lobby_close_notifier = TelegramCaravanLobbyCloseNotifier(
            bot=bot,
            bundle=bundle,
            balance=balance,
            clans=clans,
            players=players,
            participants=caravan_participants,
            locale_resolver=player_locale_resolver,
        )
        caravan_battle_finish_notifier = TelegramCaravanBattleFinishNotifier(
            bot=bot,
            bundle=bundle,
            balance=balance,
            clans=clans,
            players=players,
            participants=caravan_participants,
            locale_resolver=player_locale_resolver,
        )
        # Спринт 3.3-D D.7+D.8: boss-нотификаторы старта боя / round-tick /
        # финиша. Шлются в личный чат каждого рейдера (включая саммонера).
        # Доставка best-effort, локаль из `users.locale_override` через
        # `player_locale_resolver` с фолбэком на EN.
        boss_lobby_close_notifier = TelegramBossLobbyCloseNotifier(
            bot=bot,
            bundle=bundle,
            balance=balance,
            players=players,
            participants=boss_participants,
            locale_resolver=player_locale_resolver,
        )
        boss_round_tick_notifier = TelegramBossRoundTickNotifier(
            bot=bot,
            bundle=bundle,
            balance=balance,
            players=players,
            participants=boss_participants,
            locale_resolver=player_locale_resolver,
        )
        boss_fight_finish_notifier = TelegramBossFightFinishNotifier(
            bot=bot,
            bundle=bundle,
            balance=balance,
            players=players,
            participants=boss_participants,
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
        weekly_referral_summary_factory=lambda: run_weekly_clan_referral_summary,
        weekly_referral_summary_notifier=weekly_referral_summary_notifier,
        # Спринт 3.1-E: late-bound фабрики finish-PvE-job-ов.
        # Их создаём ниже (после этого вызова), поэтому лямбды
        # резолвятся в момент срабатывания job-а.
        mountain_finish_factory=lambda: finish_mountain_run,
        mountain_notifier=mountain_notifier,
        dungeon_finish_factory=lambda: finish_dungeon_run,
        dungeon_notifier=dungeon_notifier,
        # Спринт 3.2-B: late-bound фабрика `caravan_lobby_close`.
        # `close_caravan_lobby` создаётся ниже (после delayed_jobs).
        caravan_lobby_close_factory=lambda: close_caravan_lobby,
        # Спринт 3.2-C: late-bound фабрика `caravan_battle_finish`.
        # `finish_caravan_battle` создаётся ниже (после delayed_jobs).
        caravan_battle_finish_factory=lambda: finish_caravan_battle,
        # Спринт 3.2-D D.6: caravan-нотификаторы (best-effort, могут быть
        # `None` в unit-тестах APScheduler-а или когда `bot is None`).
        caravan_lobby_close_notifier=caravan_lobby_close_notifier,
        caravan_battle_finish_notifier=caravan_battle_finish_notifier,
        # Спринт 3.3-B / 3.3-C / 3.3-D: late-bound фабрики boss-job-ов.
        # `close_boss_lobby` (3.3-B), `run_boss_round` / `finish_boss_fight`
        # (3.3-C) создаются ниже (после delayed_jobs); лямбды резолвятся
        # в момент срабатывания job-а — после того как Container собран.
        boss_lobby_close_factory=lambda: close_boss_lobby,
        boss_round_tick_factory=lambda: run_boss_round,
        boss_fight_finish_factory=lambda: finish_boss_fight,
        # Спринт 3.3-D D.7+D.8: boss-нотификаторы (best-effort, могут
        # быть `None` в unit-тестах APScheduler-а или когда `bot is None`).
        boss_lobby_close_notifier=boss_lobby_close_notifier,
        boss_round_tick_notifier=boss_round_tick_notifier,
        boss_fight_finish_notifier=boss_fight_finish_notifier,
        clans=clans,
        # 4.1-C / C.7.b: late-bound фабрика `GeneratePrizeLots` (use-case
        # собирается ниже по файлу после `record_donation`; лямбда
        # резолвится в момент срабатывания cron-каллбэка).
        prize_lot_generator_factory=lambda: generate_prize_lots,
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
    # PvE-походы гор и данжона (Спринт 3.1-B, ГДД §8). Bot-handler-ы
    # /mountains и /dungeon — 3.1-E. До тех пор `_run_mountain_finish_job` /
    # `_run_dungeon_finish_job` в `APSchedulerDelayedJobScheduler` пишут
    # warning «factory not wired» и тихо выходят (см. `aps.py`).
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
        random=RealRandom(),
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
        random=RealRandom(),
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    # Спринт 3.2-B: караван use-case-ы (ГДД §9). `close_caravan_lobby`
    # вызывается двумя путями: APScheduler-job-ом из `delayed_jobs`
    # (через `caravan_lobby_close_factory`-замыкание) и bot-handler-ом
    # `/caravan_start` (3.2-D). Use-case идемпотентен — оба пути
    # безопасны при race-condition (см. `was_already_closed=True`).
    create_caravan = CreateCaravan(
        uow=uow,
        clans=clans,
        clan_members=clan_members,
        players=players,
        caravans=caravans,
        caravan_participants=caravan_participants,
        locks=activity_lock_service,
        balance=balance,
        random=RealRandom(),
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    join_caravan_lobby = JoinCaravanLobby(
        uow=uow,
        caravans=caravans,
        caravan_participants=caravan_participants,
        clan_members=clan_members,
        players=players,
        locks=activity_lock_service,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    leave_caravan_lobby = LeaveCaravanLobby(
        uow=uow,
        caravans=caravans,
        caravan_participants=caravan_participants,
        players=players,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
    )
    # Спринт 3.2-D, D.1+D.3: лидер отменяет караван из лобби.
    # Идемпотентен на повторный вызов в `CANCELLED`-статусе.
    cancel_caravan = CancelCaravan(
        uow=uow,
        caravans=caravans,
        caravan_participants=caravan_participants,
        players=players,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    close_caravan_lobby = CloseCaravanLobby(
        uow=uow,
        caravans=caravans,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    # Спринт 3.2-C: `FinishCaravanBattle` запускается APScheduler-job-ом
    # из `delayed_jobs` через `caravan_battle_finish_factory`-замыкание
    # ниже. `random_factory=SeededRandom` обеспечивает детерминизм
    # resolve-боя по `caravan.random_seed`.
    finish_caravan_battle = FinishCaravanBattle(
        uow=uow,
        caravans=caravans,
        caravan_participants=caravan_participants,
        clan_memberships=clan_members,
        players=players,
        length_granter=add_length,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
        balance=balance.get().caravans,
        random_factory=SeededRandom,
    )
    # Спринт 3.3-B: рейд-босс use-case-ы (ГДД §10). `close_boss_lobby`
    # вызывается двумя путями: APScheduler-job-ом из `delayed_jobs`
    # (через `boss_lobby_close_factory`-замыкание выше) и саммонером
    # вручную через `/boss_start` (3.3-D). Use-case идемпотентен —
    # оба пути безопасны при race-condition (`was_already_closed=True`).
    summon_boss = SummonBoss(
        uow=uow,
        players=players,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        locks=activity_lock_service,
        balance=balance,
        random=RealRandom(),
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
    )
    join_boss_lobby = JoinBossLobby(
        uow=uow,
        players=players,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        locks=activity_lock_service,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    leave_boss_lobby = LeaveBossLobby(
        uow=uow,
        players=players,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
    )
    close_boss_lobby = CloseBossLobby(
        uow=uow,
        boss_fights=boss_fights,
        audit=audit,
        clock=clock,
    )
    # Спринт 3.3-C: боевая механика рейд-боссов (ГДД §10.5–§10.6).
    # `RunBossRound` запускается APScheduler-job-ом `boss_round_tick`
    # (фабрика — в 3.3-D). `FinishBossFight` запускается двумя путями:
    # safety-net-job-ом `boss_fight_finish` (фабрика — в 3.3-D) и
    # напрямую `RunBossRound`-ом сразу после раунда, который закрыл бой.
    # `random_factory=SeededRandom` обеспечивает детерминизм resolve-боя
    # по `boss_fight.random_seed`.
    run_boss_round = RunBossRound(
        uow=uow,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
        balance=balance.get().bosses,
        random_factory=SeededRandom,
    )
    finish_boss_fight = FinishBossFight(
        uow=uow,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        players=players,
        length_granter=add_length,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
        balance=balance.get().bosses,
        random_factory=SeededRandom,
    )
    # Спринт 3.4-C: use-case заточки (`EnchantItem`) + read-only
    # инвентарь (`GetInventory`). `EnchantItem` требует уже открытый
    # `IUnitOfWork`-контекст у вызывающего (бот-handler `/enchant`
    # открывает `async with uow:` перед вызовом — контракт «one
    # transaction per HTTP/Telegram update»).
    enchant_item = EnchantItem(
        uow=uow,
        item_repo=items,
        scroll_repo=scrolls,
        balance=balance,
        random=RealRandom(),
        audit=audit,
        idempotency=idempotency,
        clock=clock,
        enchant_history=enchant_history,
    )
    get_inventory = GetInventory(item_repo=items, scroll_repo=scrolls, balance=balance)
    # Спринт 3.5-B/C/D: free-to-play рулетка. `roulette_spins` —
    # append-only persistence; `spin_free_roulette` — use-case с
    # 10-step flow (idempotency-check, player load, gate-ы, cost-deduction,
    # outcome-pick, record, audit, reward-grant, idempotency-mark).
    # `RealRandom()` детерминирует выбор бакета через `IRandom.random()`.
    roulette_spins = SqlAlchemyRouletteSpinRepository(uow=uow)
    # Спринт 4.1-C / C.6.b: прокинуть `IPrizeLotRepository` в use-case-ы спинов.
    # Пикер крипто-приза выбирает из `list_active(currency=STARS)`; пустой
    # результат перевыронит `CRYPTO_LOT` в `LENGTH`. Резервирование лота +
    # audit `PRIZE_LOT_RESERVED` придут в C.6.c.
    prize_lot_repo = SqlAlchemyPrizeLotRepository(uow=uow)
    spin_free_roulette = SpinFreeRoulette(
        uow=uow,
        players=players,
        roulette_spins=roulette_spins,
        prize_lots=prize_lot_repo,
        length_granter=add_length,
        balance=balance,
        audit=audit,
        idempotency=idempotency,
        random=RealRandom(),
        clock=clock,
    )
    # Спринт 4.1-A: платная рулетка за Telegram Stars. `payment_ledger` —
    # append-only ledger в `payments`-таблице с idempotency по
    # `(player_id, idempotency_key)`-индексу (миграция 0026).
    # `spin_paid_roulette` — use-case с 10-step flow (idempotency-check,
    # player load, thickness gate, charge, payment-audit, n-spin pick,
    # spin-record, spin-audit, length-grant on LENGTH, idempotency-mark).
    # `RealRandom()` детерминирует выбор бакета и outcome-kind через
    # `IRandom.random()`. Bot-handler `/roulette_paid` подключён в
    # `register_routers` отдельным router-ом.
    payment_ledger = SqlAlchemyPaymentLedger(uow=uow)
    # Спринт 4.1-B: призовой пул. `SqlAlchemyPrizePoolRepository` —
    # атомарный UPDATE по ряду `prize_pool_balance(currency)` в той же
    # UoW, что и `IPaymentLedger.charge` («потерянного доната» нет).
    # `RecordDonation` — use-case 10% инкремента пула + audit-запись
    # `PRIZE_POOL_INCREMENT` (Alembic 0028 расширил whitelist `audit_log.
    # source` этим значением). Прокинут в `SpinPaidRoulette` — Step 5b
    # 10-step flow-а вызывает `record_donation.execute(...)` с тем же
    # `idempotency_key`, что и у платежа.
    prize_pool_repo = SqlAlchemyPrizePoolRepository(uow=uow)
    record_donation = RecordDonation(
        prize_pool_repository=prize_pool_repo,
        audit_logger=audit,
        clock=clock,
    )
    # 4.1-C / C.7.a + C.7.b: cron `GeneratePrizeLots` 1×/час per currency.
    # `InMemoryFeeEstimator` — stateless константная реализация
    # (STARS=0, TON_NANO=10_000_000=0.01 TON, USDT_DECIMAL=200_000=0.2 USDT);
    # на 4.1-D подменится `TonRpcFeeEstimator` (P95 за 7 дней). Передаётся в
    # `APSchedulerDelayedJobScheduler` через late-bound лямбду
    # `prize_lot_generator_factory=lambda: generate_prize_lots` (инициали-
    # зация scheduler-а выше по файлу — резолвится при срабатывании cron-а).
    fee_estimator = InMemoryFeeEstimator()
    generate_prize_lots = GeneratePrizeLots(
        uow=uow,
        prize_pool_repository=prize_pool_repo,
        prize_lot_repository=prize_lot_repo,
        fee_estimator=fee_estimator,
        audit_logger=audit,
        idempotency=idempotency,
        clock=clock,
    )
    spin_paid_roulette = SpinPaidRoulette(
        uow=uow,
        players=players,
        roulette_spins=roulette_spins,
        prize_lots=prize_lot_repo,
        payments=payment_ledger,
        length_granter=add_length,
        balance=balance,
        audit=audit,
        idempotency=idempotency,
        random=RealRandom(),
        clock=clock,
        record_donation=record_donation,
    )
    # Спринт 3.3-D D.1: саммонер отменяет рейд из лобби. Идемпотентен
    # на повторный вызов в `CANCELLED`-статусе.
    cancel_boss_fight = CancelBossFight(
        uow=uow,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        players=players,
        locks=activity_lock_service,
        audit=audit,
        clock=clock,
        scheduler=delayed_jobs,
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
        clans=clans,
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
    # /anticheat_unban (Спринт 1.6.G → 2.5-D.7) — admin-команда снятия
    # soft-ban-а. RBAC через ensure_admin_authorized + admin_audit (D.7).
    lift_anticheat_ban = LiftAnticheatBan(
        uow=uow,
        admins=admins,
        players=players,
        audit=audit,
        admin_audit=admin_audit,
        authz=admin_authz,
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
        rate_limiter=referral_rate_limiter,
        audit=audit,
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
    run_weekly_clan_referral_summary = RunWeeklyClanReferralSummary(
        uow=uow,
        clans=clans,
        players=players,
        referrals=referrals,
        clock=clock,
    )
    # ── Расширенный админ-интерфейс (Спринт 2.5-B + 2.5-D) ──
    # NOTE: `admin_audit` и `admin_authz` уже инициализированы выше
    # (перед reload_balance/set_max_dau/lift_anticheat_ban) — здесь
    # добавляем только оставшиеся (read-side query, confirm-store, TOTP).
    admin_audit_query = SqlAlchemyAdminAuditQuery(uow=uow)
    admin_confirm_store = InMemoryAdminConfirmStore()
    totp_verifier = PyOtpTotpVerifier()
    totp_secret_generator = PyOtpTotpSecretGenerator()
    find_players = FindPlayers(
        uow=uow,
        admins=admins,
        players=players,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    get_player_card = GetPlayerCard(
        uow=uow,
        admins=admins,
        players=players,
        clans=clans,
        clan_members=clan_members,
        forest_runs=forest_runs,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    freeze_player = FreezePlayer(
        uow=uow,
        admins=admins,
        players=players,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    unfreeze_player = UnfreezePlayer(
        uow=uow,
        admins=admins,
        players=players,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    ban_player = BanPlayer(
        uow=uow,
        admins=admins,
        players=players,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    request_admin_confirm = RequestAdminConfirm(
        uow=uow,
        admins=admins,
        store=admin_confirm_store,
        audit=admin_audit,
        clock=clock,
        token_factory=_default_admin_token_factory,
        authz=admin_authz,
    )
    verify_admin_confirm = VerifyAdminConfirm(
        uow=uow,
        admins=admins,
        store=admin_confirm_store,
        totp=totp_verifier,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    grant_length = GrantLength(
        uow=uow,
        admins=admins,
        players=players,
        length_granter=add_length,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    grant_thickness = GrantThickness(
        uow=uow,
        admins=admins,
        players=players,
        balance=balance,
        idempotency=idempotency,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    get_balance_value = GetBalanceValue(
        uow=uow,
        admins=admins,
        balance=balance,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    balance_writer = YamlBalanceWriter(
        path=balance_yaml_path or _DEFAULT_BALANCE_YAML,
        loader=balance,
    )
    set_balance_value = SetBalanceValue(
        uow=uow,
        admins=admins,
        balance=balance,
        writer=balance_writer,
        idempotency=idempotency,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    get_admin_audit_trail = GetAdminAuditTrail(
        uow=uow,
        admins=admins,
        query=admin_audit_query,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    get_clan_card = GetClanCard(
        uow=uow,
        admins=admins,
        players=players,
        clans=clans,
        clan_members=clan_members,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    freeze_clan_admin = FreezeClanAdmin(
        uow=uow,
        admins=admins,
        clans=clans,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    unfreeze_clan_admin = UnfreezeClanAdmin(
        uow=uow,
        admins=admins,
        clans=clans,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    get_clan_daily_head_history = GetClanDailyHeadHistory(
        uow=uow,
        admins=admins,
        clans=clans,
        players=players,
        daily_heads=daily_heads,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    # Спринт 2.5-D.4: `/announce` — broadcast с TOTP-confirm.
    broadcast_announcement = BroadcastAnnouncement(
        uow=uow,
        admins=admins,
        players=players,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    broadcast_sender: IBroadcastSender = (
        AiogramBroadcastSender(bot=bot) if bot is not None else NoopBroadcastSender()
    )
    broadcast_task_spawner: IBroadcastTaskSpawner = AsyncIOBroadcastTaskSpawner()
    run_broadcast_announcement = RunBroadcastAnnouncement(
        uow=uow,
        admins=admins,
        players=players,
        sender=broadcast_sender,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    # Спринт 2.5-D.6: out-of-band bootstrap-пароль для `/admin_setup_totp`.
    # `None` ⇒ команда отказывает (fail-closed); use-case дальше сравнивает
    # пароль через `hmac.compare_digest()` constant-time-сравнением.
    bootstrap_admin_password = (
        settings.bootstrap.admin_password.get_secret_value()
        if settings.bootstrap.admin_password is not None
        else None
    )
    setup_admin_totp = SetupAdminTotp(
        uow=uow,
        admins=admins,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
        secret_generator=totp_secret_generator,
        bootstrap_password=bootstrap_admin_password,
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
        mountain_runs=mountain_runs,
        dungeon_runs=dungeon_runs,
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
        start_mountain_run=start_mountain_run,
        finish_mountain_run=finish_mountain_run,
        start_dungeon_run=start_dungeon_run,
        finish_dungeon_run=finish_dungeon_run,
        caravans=caravans,
        caravan_participants=caravan_participants,
        create_caravan=create_caravan,
        join_caravan_lobby=join_caravan_lobby,
        leave_caravan_lobby=leave_caravan_lobby,
        cancel_caravan=cancel_caravan,
        close_caravan_lobby=close_caravan_lobby,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        summon_boss=summon_boss,
        join_boss_lobby=join_boss_lobby,
        leave_boss_lobby=leave_boss_lobby,
        cancel_boss_fight=cancel_boss_fight,
        close_boss_lobby=close_boss_lobby,
        run_boss_round=run_boss_round,
        finish_boss_fight=finish_boss_fight,
        items=items,
        scrolls=scrolls,
        enchant_history=enchant_history,
        enchant_item=enchant_item,
        get_inventory=get_inventory,
        roulette_spins=roulette_spins,
        spin_free_roulette=spin_free_roulette,
        payment_ledger=payment_ledger,
        spin_paid_roulette=spin_paid_roulette,
        prize_pool_repo=prize_pool_repo,
        record_donation=record_donation,
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
        run_weekly_clan_referral_summary=run_weekly_clan_referral_summary,
        admin_audit=admin_audit,
        admin_audit_query=admin_audit_query,
        admin_confirm_store=admin_confirm_store,
        totp_verifier=totp_verifier,
        totp_secret_generator=totp_secret_generator,
        admin_authz=admin_authz,
        find_players=find_players,
        get_player_card=get_player_card,
        freeze_player=freeze_player,
        unfreeze_player=unfreeze_player,
        ban_player=ban_player,
        request_admin_confirm=request_admin_confirm,
        verify_admin_confirm=verify_admin_confirm,
        grant_length=grant_length,
        grant_thickness=grant_thickness,
        get_balance_value=get_balance_value,
        set_balance_value=set_balance_value,
        get_admin_audit_trail=get_admin_audit_trail,
        get_clan_card=get_clan_card,
        freeze_clan_admin=freeze_clan_admin,
        unfreeze_clan_admin=unfreeze_clan_admin,
        get_clan_daily_head_history=get_clan_daily_head_history,
        broadcast_announcement=broadcast_announcement,
        run_broadcast_announcement=run_broadcast_announcement,
        broadcast_sender=broadcast_sender,
        broadcast_task_spawner=broadcast_task_spawner,
        setup_admin_totp=setup_admin_totp,
    )


def build_dispatcher(container: Container) -> Dispatcher:  # noqa: PLR0915 — composition root, плоский DI-список оправдан
    """Собрать aiogram `Dispatcher` со стеком middleware-ов и роутерами.

    Use-case-ы регистрируются в `dispatcher` workflow-data — aiogram
    автоматически пробросит их в handler-ы по имени параметра.
    """
    dispatcher = Dispatcher()
    # Спринт 2.5-A.2: AdminGuard кладёт `data["admin"] = Admin | None`
    # для будущих admin-handler-ов (2.5-B/C/D). Сам по себе апдейт не
    # отбрасывает — «тихий игнор чужих» делается на уровне router-а.
    admin_guard = AdminGuard(uow=container.uow, admins=container.admins)
    register_middlewares(
        dispatcher,
        limiter=container.rate_limiter,
        record_player_activity=container.record_player_activity,
        player_locale_resolver=container.player_locale_resolver,
        admin_guard=admin_guard,
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
    # Расширенный админ-интерфейс (Спринт 2.5-B) — use-cases для
    # `admin_support_router`. Все шесть use-case-ов проверяют
    # `admin.is_active` сами (defense-in-depth), но плюс есть
    # router-уровневый `IsAdminFilter`, который тихо отфильтровывает
    # не-админов на уровне dispatch (ГДД §18.6.4).
    dispatcher["find_players"] = container.find_players
    dispatcher["get_player_card"] = container.get_player_card
    dispatcher["freeze_player"] = container.freeze_player
    dispatcher["unfreeze_player"] = container.unfreeze_player
    dispatcher["ban_player"] = container.ban_player
    dispatcher["request_admin_confirm"] = container.request_admin_confirm
    dispatcher["verify_admin_confirm"] = container.verify_admin_confirm
    # Спринт 2.5-C — команды экономики.
    dispatcher["grant_length"] = container.grant_length
    dispatcher["grant_thickness"] = container.grant_thickness
    dispatcher["get_balance_value"] = container.get_balance_value
    dispatcher["set_balance_value"] = container.set_balance_value
    # Спринт 2.5-D.5 — read-side observability `/audit`.
    dispatcher["get_admin_audit_trail"] = container.get_admin_audit_trail
    # Спринт 2.5-D.1 — read-side карточка клана `/clan`.
    dispatcher["get_clan_card"] = container.get_clan_card
    # Спринт 2.5-D.2 — `/freeze_clan`, `/unfreeze_clan` (admin-side).
    dispatcher["freeze_clan_admin"] = container.freeze_clan_admin
    dispatcher["unfreeze_clan_admin"] = container.unfreeze_clan_admin
    # Спринт 2.5-D.3 — `/clan_daily_head_history` (read-only).
    dispatcher["get_clan_daily_head_history"] = container.get_clan_daily_head_history
    # Спринт 2.5-D.4 — `/announce` (broadcast с TOTP-confirm).
    dispatcher["broadcast_announcement"] = container.broadcast_announcement
    dispatcher["run_broadcast_announcement"] = container.run_broadcast_announcement
    dispatcher["broadcast_task_spawner"] = container.broadcast_task_spawner
    # Спринт 2.5-D.6 — `/admin_setup_totp` (self-service выдача TOTP-секрета).
    dispatcher["setup_admin_totp"] = container.setup_admin_totp
    # Спринт 3.2-D — bot-handler `/caravan` (личка-only) + inline-кнопки
    # лобби. D.3a/b — `caravan:cancel:<id>` (use-case `CancelCaravan`).
    # D.3c — `caravan:show_lobby:<id>` (read-side: грузит караван +
    # участников + лидера + клан-получатель, перерисовывает сообщение
    # с join/leave/cancel-клавиатурой). `join_*` / `leave` use-case-ы
    # подключатся к dispatcher по мере добавления callback-веток в
    # последующих под-коммитах D.3 (D.3d/e/f).
    dispatcher["create_caravan"] = container.create_caravan
    dispatcher["cancel_caravan"] = container.cancel_caravan
    dispatcher["join_caravan_lobby"] = container.join_caravan_lobby
    dispatcher["leave_caravan_lobby"] = container.leave_caravan_lobby
    dispatcher["caravans"] = container.caravans
    dispatcher["caravan_participants"] = container.caravan_participants
    dispatcher["clan_members"] = container.clan_members
    # Спринт 3.3-D — bot-handler `/boss` (личка-only) + inline-кнопки
    # лобби. Команда `/boss` запускает `SummonBoss`. Callback-роутер
    # `boss:show_lobby|join|leave|cancel:<id>` делает read-side render
    # лобби (`boss_fights` + `boss_participants` + `players`) и зовёт
    # соответствующий use-case.
    dispatcher["summon_boss"] = container.summon_boss
    dispatcher["join_boss_lobby"] = container.join_boss_lobby
    dispatcher["leave_boss_lobby"] = container.leave_boss_lobby
    dispatcher["cancel_boss_fight"] = container.cancel_boss_fight
    dispatcher["boss_fights"] = container.boss_fights
    dispatcher["boss_participants"] = container.boss_participants
    # Спринт 3.4-D — bot-handler-ы `/inventory` (личка-only карточка
    # инвентаря) + `/enchant <item_id> <scroll_id>` (warning-карточка
    # + confirm/cancel callback-и). `enchant_item` требует уже открытый
    # `IUnitOfWork`-контекст — confirm-callback открывает `async with uow:`
    # перед вызовом, `uow` проброшен через workflow-data.
    dispatcher["get_inventory"] = container.get_inventory
    dispatcher["enchant_item"] = container.enchant_item
    dispatcher["uow"] = container.uow
    # Спринт 3.5-D — bot-handler `/roulette_free` (личка-only) +
    # spin-callback `roulette_free:spin`. Использует `get_profile` для
    # pre-spin gate-чека и `spin_free_roulette` для самой прокрутки.
    dispatcher["spin_free_roulette"] = container.spin_free_roulette
    # Спринт 4.1-A — bot-handler `/roulette_paid` (личка-only) +
    # buy-callback `roulette_paid:buy_*` + `pre_checkout_query` +
    # `successful_payment`. Использует `get_profile` для pre-spin
    # gate-чека (`balance.roulette.paid.min_thickness_level`) и
    # `spin_paid_roulette` для самой прокрутки после подтверждения
    # платежа Telegram-ом.
    dispatcher["spin_paid_roulette"] = container.spin_paid_roulette
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
        # Глобальный weekly cron «итоги недели по рефералам клана»
        # (вс. 18:00 UTC, Спринт 2.4.E).
        await scheduler.schedule_weekly_clan_referral_summary_cron()
        # 4.1-C / C.7.b: hourly cron `GeneratePrizeLots` per currency
        # (3 инстанса IntervalTrigger(hours=1) — STARS / TON_NANO / USDT_DECIMAL).
        scheduler.schedule_prize_lot_generator_cron()
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
