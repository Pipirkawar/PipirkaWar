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
import contextlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from prometheus_client import CollectorRegistry
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
from pipirik_wars.application.announcements import (
    PublishLeaderboard,
    PublishWeeklyDigest,
)
from pipirik_wars.application.announcements.stats_query import (
    IAnnouncementStatsQuery,
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
from pipirik_wars.application.forest.log_templates import IForestLogTemplateProvider
from pipirik_wars.application.i18n import (
    SUPPORTED_LOCALES,
    IMessageBundle,
    IPlayerLocaleResolver,
)
from pipirik_wars.application.inventory import EnchantItem, GetInventory
from pipirik_wars.application.monetization import (
    ClaimPrize,
    EvaluatePayoutLimit,
    ExpireReservedPrizeLots,
    FreezePayouts,
    GeneratePrizeLots,
    GetPrizePoolStatus,
    LinkWallet,
    RecordDonation,
    RefundLot,
    RequestLinkWalletProof,
    RequestLinkWalletProofConfig,
    SpinPaidRoulette,
    UnfreezePayouts,
)
from pipirik_wars.application.mountains import (
    FinishMountainRun,
    IMountainFinishNotifier,
    StartMountainRun,
)
from pipirik_wars.application.observability import (
    IBusinessMetrics,
    NullBusinessMetrics,
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
from pipirik_wars.domain.announcements.ports import IAnnouncementPublisher
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
from pipirik_wars.domain.monetization import (
    INonceStore,
    IPaymentLedger,
    IPayoutFreezeRepository,
    IPayoutLimitChecker,
    IPrizeLotRepository,
    IPrizePoolRepository,
    ITgStarsPayloadVerifier,
    ITonConnectVerifier,
    ITonPayoutAdapter,
    IWalletRepository,
)
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
from pipirik_wars.infrastructure.ai import (
    AiDuelLogTemplateProvider,
    AiForestLogTemplateProvider,
    AiOracleTemplateProvider,
    OpenAiTextGenerator,
)
from pipirik_wars.infrastructure.announcements import (
    AiogramAnnouncementPublisher,
    SqlAlchemyAnnouncementStatsQuery,
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
    SqlAlchemyNonceStore,
    SqlAlchemyOracleHistoryRepository,
    SqlAlchemyPaymentLedger,
    SqlAlchemyPayoutFreezeRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemyPrizeLotRepository,
    SqlAlchemyPrizePoolRepository,
    SqlAlchemyReferralRepository,
    SqlAlchemyRouletteSpinRepository,
    SqlAlchemyScrollRepository,
    SqlAlchemySignupQueueRepository,
    SqlAlchemyWalletRepository,
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
from pipirik_wars.infrastructure.observability import (
    PrometheusBusinessMetrics,
    RedisMetrics,
    build_metrics_app,
)
from pipirik_wars.infrastructure.payments.tg_stars import HmacTgStarsPayloadVerifier
from pipirik_wars.infrastructure.payments.tg_stars.settings import TgStarsSettings
from pipirik_wars.infrastructure.payments.ton_connect import (
    InMemoryNonceStore,
    SandboxTonConnectVerifier,
)
from pipirik_wars.infrastructure.payments.ton_connect.production import (
    TonConnectProductionConfig,
    TonConnectProductionVerifier,
)
from pipirik_wars.infrastructure.payments.ton_rpc import (
    Ed25519MessageSigner,
    JettonUsdtProvider,
    TonRpcAdapter,
    TonRpcHttpClient,
)
from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings
from pipirik_wars.infrastructure.random import RealRandom, SeededRandom
from pipirik_wars.infrastructure.rate_limit import (
    InMemoryTokenBucketRateLimiter,
    IRateLimiter,
)
from pipirik_wars.infrastructure.redis import (
    RedisActivityLockRepository,
    RedisDauCounter,
    RedisGlobalLobbyRepository,
    build_redis_client,
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


logger = logging.getLogger(__name__)


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

    # Обсервабельность (Спринт 4.1-J, шаг J.2): Prometheus-`CollectorRegistry`,
    # в который RedisMetrics регистрирует свои counter/histogram-ы. Собирается
    # в composition-root **только** при `needs_redis=True` — при default-sql-
    # конфигурации Redis-операций нет и observability-endpoint не поднимается.
    # `None` → web-runner в `run()` пропускается.
    metrics_registry: CollectorRegistry | None

    # Спринт 4.1-N: бизнес-метрики (DAU/караваны/рейды/призовой пул).
    # Регистрируются в тот же `metrics_registry`, что и `RedisMetrics`, —
    # один `/metrics`-endpoint на оба класса. При `needs_redis=False`
    # (default-sql-конфигурация) field = `NullBusinessMetrics()` no-op;
    # реальный Prometheus-адаптер создаётся только при
    # `needs_redis=True` (cleanly связано с поднятием HTTP `/metrics`).
    business_metrics: IBusinessMetrics

    # Шаблоны (Спринт 1.4.B / 1.5.G / 2.1.H)
    oracle_templates: IOracleTemplateProvider
    duel_log_templates: IDuelLogTemplateProvider

    # AI-template-провайдеры (Спринт 4.1-M, опц.). Обратные ссылки на
    # AI-обёртки нужны для фонового refresh-таска в `run()`. При `AI_ENABLED=False`
    # все три поля = `None`, и use-case-ы работают со static-провайдерами
    # напрямую. При `AI_ENABLED=True` AI-провайдеры оборачивают static-провайдеры
    # как fallback, и именно эти обёртки попадают в use-case-ы.
    ai_oracle_provider: AiOracleTemplateProvider | None
    ai_forest_provider: AiForestLogTemplateProvider | None
    ai_duel_provider: AiDuelLogTemplateProvider | None

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
    # Призовые лоты + крипто-выплаты (Спринт 4.1-C + 4.1-D). 4.1-C —
    # `prize_lot_repo` (`SqlAlchemyPrizeLotRepository`), use-case-ы
    # `GeneratePrizeLots` (cron 1×/час) + reservation в спинах. 4.1-D —
    # `wallet_repo` (`SqlAlchemyWalletRepository`), use-case-ы `LinkWallet`
    # / `ClaimPrize` / `ExpireReservedPrizeLots`, `ton_payout_adapter`
    # (`TonRpcAdapter` поверх `TonRpcHttpClient` + `Ed25519MessageSigner` +
    # `JettonUsdtProvider`), `tg_stars_verifier` (`HmacTgStarsPayloadVerifier`),
    # `ton_connect_verifier` (`SandboxTonConnectVerifier` stub до 4.1-E).
    prize_lot_repo: IPrizeLotRepository
    wallet_repo: IWalletRepository
    payout_freeze_repo: IPayoutFreezeRepository
    payout_limit_checker: IPayoutLimitChecker
    ton_payout_adapter: ITonPayoutAdapter
    ton_connect_verifier: ITonConnectVerifier
    # Спринт 4.1-F (шаг F.4.b): server-side nonce-store для
    # TON Connect 2.0 anti-replay. До F.6.b/F.7 — in-memory; затем
    # `SqlAlchemyNonceStore` (production).
    nonce_store: INonceStore
    tg_stars_verifier: ITgStarsPayloadVerifier
    generate_prize_lots: GeneratePrizeLots
    # Спринт 4.1-F (шаг F.7): phase-1 use-case TON Connect 2.0-flow-а.
    # Выдаёт server-issued nonce + canonical-domain игроку, чтобы тот
    # передал в TonConnect-app для подписи. Phase-2 — `link_wallet` ниже.
    request_link_wallet_proof: RequestLinkWalletProof
    link_wallet: LinkWallet
    claim_prize: ClaimPrize
    get_prize_pool_status: GetPrizePoolStatus
    refund_lot: RefundLot
    freeze_payouts: FreezePayouts
    unfreeze_payouts: UnfreezePayouts
    expire_reserved_prize_lots: ExpireReservedPrizeLots
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

    # Канал-анонсы (Спринт 4.9)
    announcement_publisher: IAnnouncementPublisher | None
    announcement_stats_query: IAnnouncementStatsQuery | None
    publish_weekly_digest: PublishWeeklyDigest | None
    publish_leaderboard: PublishLeaderboard | None


def build_container(  # noqa: PLR0912,PLR0915 — composition root, плоский DI-список оправдан
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
    # Спринт 4.1-G/H: config-flag-режимы Redis-бэкендов. Один
    # `build_redis_client(settings.redis)` создаётся ровно один раз
    # (long-lived `ConnectionPool` singleton) и переиспользуется всеми
    # Redis-репозиториями. Если ни один Redis-бэкенд не включён — клиент
    # не создаётся (`needs_redis is False`), чтобы default-sql-конфигурация
    # не открывала лишний TCP-resolver.
    needs_redis = (
        settings.bot.activity_lock_backend == "redis"
        or settings.bot.lobby_backend == "redis"
        or settings.bot.dau_backend == "redis"
    )
    redis_client = build_redis_client(settings.redis) if needs_redis else None
    # Спринт 4.1-J (шаг J.2): Prometheus-метрики Redis-операций. RedisMetrics
    # инстанциируется ровно один раз и переиспользуется всеми тремя Redis-
    # репозиториями (одна counter+histogram-пара на весь процесс). При
    # default-sql-конфигурации (`needs_redis is False`) registry/metrics =
    # None — репозитории, которые в этом случае не создаются, метрики тоже
    # не получают; default-sql-репозитории Prometheus-инструментацией не
    # покрыты (см. 4.1-J скоуп — метрики только на Redis-бэкенды).
    metrics_registry: CollectorRegistry | None = CollectorRegistry() if needs_redis else None
    redis_metrics = RedisMetrics(registry=metrics_registry) if needs_redis else None
    # Спринт 4.1-N: PrometheusBusinessMetrics регистрируется в тот же
    # `metrics_registry`-инстанс (общий `/metrics`-endpoint). При default-
    # sql-конфигурации (`needs_redis=False`) HTTP-endpoint не поднимается,
    # поэтому бизнес-метрики тоже null-object — это позволяет use-case-ам
    # звать `self._business_metrics.inc_X()` без условных проверок.
    business_metrics: IBusinessMetrics
    if needs_redis:
        assert metrics_registry is not None
        business_metrics = PrometheusBusinessMetrics(registry=metrics_registry)
    else:
        business_metrics = NullBusinessMetrics()
    # Спринт 4.1-G (шаг G.4): config-flag-режим бэкенда `IActivityLockRepository`.
    # `sql` (default) — `SqlAlchemyActivityLockRepository` поверх таблицы
    # `activity_locks` (текущая, до 4.1-G, имплементация: INSERT ... ON CONFLICT
    # DO NOTHING). `redis` — `RedisActivityLockRepository` поверх
    # `redis.asyncio.Redis` (атомарный SET NX PX + DEL + GET/PTTL); требует
    # поднятого Redis-инстанса по `settings.redis.url`. Default `sql` для
    # backward-compatibility на момент 4.1-G-merge-а; Redis включается явным
    # env-флагом `BOT_ACTIVITY_LOCK_BACKEND=redis`.
    activity_locks: IActivityLockRepository
    if settings.bot.activity_lock_backend == "redis":
        # `needs_redis` гарантирует not-None; ассерт сужает mypy-типы.
        assert redis_client is not None
        activity_locks = RedisActivityLockRepository(
            client=redis_client,
            clock=clock,
            metrics=redis_metrics,
        )
    else:
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
    # Спринт 4.1-H (шаг H.2): config-flag-режим бэкенда
    # `IGlobalLobbyRepository`. `sql` (default) —
    # `SqlAlchemyGlobalLobbyRepository` поверх таблицы `pvp_global_lobby`
    # (FIFO ON CONFLICT DO NOTHING + SELECT FOR UPDATE SKIP LOCKED).
    # `redis` — `RedisGlobalLobbyRepository` поверх `redis.asyncio.Redis`
    # (LIST `lobby:queue` + HASH `lobby:enqueued_at` + 3 атомарных Lua-
    # скрипта). Default `sql` — backward-compat на момент 4.1-H-merge-а;
    # Redis включается явным env-флагом `BOT_LOBBY_BACKEND=redis`.
    global_lobby: IGlobalLobbyRepository
    if settings.bot.lobby_backend == "redis":
        # `needs_redis` гарантирует not-None; ассерт сужает mypy-типы.
        assert redis_client is not None
        global_lobby = RedisGlobalLobbyRepository(
            client=redis_client,
            metrics=redis_metrics,
        )
    else:
        global_lobby = SqlAlchemyGlobalLobbyRepository(uow=uow)
    referrals = SqlAlchemyReferralRepository(uow=uow)
    anticheat = SqlAlchemyAnticheatRepository(uow=uow)
    anticheat_admin_alerter = StructlogAnticheatAdminAlerter()
    json_oracle_templates = JsonOracleTemplateProvider(
        templates_dir=templates_dir or _DEFAULT_TEMPLATES_DIR,
    )
    json_forest_log_templates = JsonForestLogTemplateProvider(
        templates_dir=templates_dir or _DEFAULT_TEMPLATES_DIR,
    )
    json_duel_log_templates = JsonDuelLogTemplateProvider(
        templates_dir=templates_dir or _DEFAULT_TEMPLATES_DIR,
    )
    # Спринт 4.1-M (задача 4.1.13, опц.): ИИ-обёртки поверх static-
    # провайдеров. При `AI_ENABLED=False` (default) AI-обёртки не
    # собираются — use-case-ы получают static-провайдеры напрямую. При
    # `AI_ENABLED=True` + валидный `AI_API_KEY`: lazy-импорт `openai`,
    # создание `OpenAiTextGenerator`, обёртывание всех 3 static-провайдеров
    # в AI-обёртки (AI-провайдер использует static как fallback). Реальный
    # refresh кэша запускается фоновым таском в `run()` (Спринт 4.1-M).
    oracle_templates: IOracleTemplateProvider
    forest_log_templates: IForestLogTemplateProvider
    duel_log_templates: IDuelLogTemplateProvider
    ai_oracle_provider: AiOracleTemplateProvider | None = None
    ai_forest_provider: AiForestLogTemplateProvider | None = None
    ai_duel_provider: AiDuelLogTemplateProvider | None = None
    if settings.ai.enabled and settings.ai.api_key is not None:
        # Lazy-импорт `openai`: SDK — optional dependency. Если пакет
        # не установлен — явный ImportError в логе и fallback на static.
        try:
            from openai import AsyncOpenAI  # type: ignore[import-not-found]  # noqa: PLC0415
        except ImportError:
            logger.warning(
                "ai.enabled=True но пакет `openai` не установлен; fallback на static-шаблоны"
            )
            oracle_templates = json_oracle_templates
            forest_log_templates = json_forest_log_templates
            duel_log_templates = json_duel_log_templates
        else:
            ai_client = AsyncOpenAI(
                api_key=settings.ai.api_key.get_secret_value(),
                base_url=settings.ai.base_url,
                timeout=settings.ai.timeout_seconds,
            )
            ai_generator = OpenAiTextGenerator(
                client=ai_client,
                model=settings.ai.model,
                timeout_seconds=settings.ai.timeout_seconds,
            )
            ai_oracle_provider = AiOracleTemplateProvider(
                generator=ai_generator,
                fallback=json_oracle_templates,
                batch_size=settings.ai.batch_size_oracle,
            )
            ai_forest_provider = AiForestLogTemplateProvider(
                generator=ai_generator,
                fallback=json_forest_log_templates,
                batch_size=settings.ai.batch_size_forest,
            )
            ai_duel_provider = AiDuelLogTemplateProvider(
                generator=ai_generator,
                fallback=json_duel_log_templates,
                batch_size=settings.ai.batch_size_duel,
            )
            oracle_templates = ai_oracle_provider
            forest_log_templates = ai_forest_provider
            duel_log_templates = ai_duel_provider
    else:
        oracle_templates = json_oracle_templates
        forest_log_templates = json_forest_log_templates
        duel_log_templates = json_duel_log_templates
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
    # Спринт 4.1-I (шаг I.2): config-flag-режим бэкенда
    # `IDauCounter`. `sql` (default-name; реально — in-memory
    # `InMemoryDauCounter`, имя сохранено для единообразия
    # с `activity_lock_backend`/`lobby_backend` config-flag-ами) —
    # `asyncio`-Lock-нутый `set[int]` теряется на рестарте.
    # `redis` — `RedisDauCounter` поверх `redis.asyncio.Redis`
    # (per-day ZSET `dau:{YYYY-MM-DD}` + TTL 48h; pipelined ZADD+EXPIRE);
    # переживает рестарт бота, lazy-reset на МСК-полночи
    # через смену key-а. Требует поднятого Redis-инстанса по
    # `settings.redis.url`. Default `sql` — backward-compat на момент
    # 4.1-I-merge-а; Redis включается явным env-флагом
    # `BOT_DAU_BACKEND=redis`.
    dau_counter: IDauCounter
    if settings.bot.dau_backend == "redis":
        # `needs_redis` гарантирует not-None; ассерт сужает mypy-типы.
        assert redis_client is not None
        dau_counter = RedisDauCounter(
            client=redis_client,
            clock=clock,
            metrics=redis_metrics,
        )
    else:
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
        business_metrics=business_metrics,
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
        # 4.1-D / D.9.d: late-bound фабрика `ExpireReservedPrizeLots`
        # (собирается ниже по файлу рядом с `generate_prize_lots`).
        expire_reserved_prize_lots_factory=lambda: expire_reserved_prize_lots,
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
        business_metrics=business_metrics,
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
        business_metrics=business_metrics,
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
        business_metrics=business_metrics,
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
        business_metrics=business_metrics,
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
        business_metrics=business_metrics,
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
        business_metrics=business_metrics,
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
    # Спринт 4.1-E / E.10–E.11a: `IPayoutFreezeRepository` + `IPayoutLimitChecker`
    # для `ClaimPrize.execute(...)` (freeze-check + rolling-window-лимит) и
    # admin-команд `/freeze_payouts`/`/unfreeze_payouts`/`/prize_pool`.
    payout_freeze_repo: IPayoutFreezeRepository = SqlAlchemyPayoutFreezeRepository(
        uow=uow,
    )
    payout_limit_checker: IPayoutLimitChecker = EvaluatePayoutLimit(
        lot_repo=prize_lot_repo,
        balance_config=balance,
    )
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
    # Спринт 4.1-E / E.12: admin-команда `/prize_pool` (super-admin
    # read-only + audit `ADMIN_PRIZE_POOL_VIEWED`).
    get_prize_pool_status = GetPrizePoolStatus(
        uow=uow,
        admins=admins,
        prize_pool_repository=prize_pool_repo,
        prize_lot_repository=prize_lot_repo,
        payout_freeze_repo=payout_freeze_repo,
        admin_audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    # Спринт 4.1-E / E.13: admin-команда `/refund_lot <lot_id> <reason>`
    # (super-admin + TOTP). Двухфазный flow: handler `admin_refund_lot`
    # → `RequestAdminConfirm` (фаза 1, выдаёт token), `admin_support.handle_confirm`
    # → `dispatch_refund_lot` (фаза 2, после TOTP-verify, вызывает усе-кейс).
    # Регистрация в `CONFIRM_DISPATCHERS` срабатывает при импорте
    # модуля `bot/handlers/admin_refund_lot.py` (через `register_routers`).
    refund_lot = RefundLot(
        uow=uow,
        admins=admins,
        prize_lot_repository=prize_lot_repo,
        prize_pool_repository=prize_pool_repo,
        audit=audit,
        admin_audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    # Спринт 4.1-E / E.14: admin-команды `/freeze_payouts <reason>` и
    # `/unfreeze_payouts` (super-admin + TOTP). Двухфазный flow: handler
    # `admin_freeze_payouts` → `RequestAdminConfirm` (фаза 1, выдаёт token),
    # `admin_support.handle_confirm` → `dispatch_(un)freeze_payouts` (фаза 2,
    # после TOTP-verify, вызывает `FreezePayouts` / `UnfreezePayouts`).
    # Регистрация в `CONFIRM_DISPATCHERS` срабатывает при импорте
    # `bot/handlers/admin_freeze_payouts.py` (через `register_routers`).
    freeze_payouts_uc = FreezePayouts(
        uow=uow,
        admins=admins,
        payout_freeze_repo=payout_freeze_repo,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    unfreeze_payouts_uc = UnfreezePayouts(
        uow=uow,
        admins=admins,
        payout_freeze_repo=payout_freeze_repo,
        audit=admin_audit,
        clock=clock,
        authz=admin_authz,
    )
    # 4.1-C / C.7.a + C.7.b: cron `GeneratePrizeLots` 1×/час per currency.
    # 4.1-C / C.7.d: тот же use-case прокидывается в `RecordDonation` как
    # внеочередной триггер «крупного» доната (>= 0.5 TON / >= 1 USDT),
    # вложенный в open-UoW `SpinPaidRoulette` через ambient-UoW-паттерн
    # (`GeneratePrizeLots` сам решает — открывать UoW или переиспользовать
    # caller-овский, см. `is_active`-проверку в `GeneratePrizeLots.execute`).
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
    record_donation = RecordDonation(
        prize_pool_repository=prize_pool_repo,
        audit_logger=audit,
        clock=clock,
        generate_prize_lots=generate_prize_lots,
        business_metrics=business_metrics,
    )
    # 4.1-D / D.9.c + D.9.d: refund RESERVED-лотов по TTL
    # (`balance.prize_lot.reserved_ttl_seconds`, дефолт 48 h). Дёргается
    # из APScheduler-а 1×/час через `expire_reserved_prize_lots_factory`
    # late-bound лямбду (см. выше в инициализации scheduler-а).
    expire_reserved_prize_lots = ExpireReservedPrizeLots(
        uow=uow,
        prize_lot_repository=prize_lot_repo,
        prize_pool_repository=prize_pool_repo,
        audit_logger=audit,
        balance_config=balance,
        clock=clock,
    )
    # Спринт 4.1-D / D.10.c: composition root для крипто-выплат.
    # Если `settings.tg_stars` / `settings.ton_rpc` не заданы (None) —
    # собираем дефолтами (placeholder-seed `0`*32, placeholder-secret
    # `"placeholder-tg-stars-secret"`). Это позволяет unit-тестам
    # инстанцировать Container без env-context-а. В production-сборке
    # обе секции должны быть подняты из env-переменных `TG_STARS_*` и
    # `TON_RPC_*`.
    tg_stars_settings = settings.tg_stars or TgStarsSettings(
        secret=SecretStr("placeholder-tg-stars-secret-replace-via-env-32b"),
    )
    tg_stars_verifier: ITgStarsPayloadVerifier = HmacTgStarsPayloadVerifier(
        settings=tg_stars_settings,
    )
    ton_rpc_settings = settings.ton_rpc or TonRpcSettings()
    # Hex-seed из `TonRpcSettings.payout_wallet_signing_key_seed`:
    # 64 hex-символа → 32 байта; используется `Ed25519MessageSigner`-ом.
    # Validator в `TonRpcSettings` уже проверил формат, здесь декодируем.
    _payout_seed_bytes = bytes.fromhex(
        ton_rpc_settings.payout_wallet_signing_key_seed.get_secret_value(),
    )
    ton_rpc_http_client = TonRpcHttpClient(settings=ton_rpc_settings)
    ton_message_signer = Ed25519MessageSigner(signing_key_seed=_payout_seed_bytes)
    jetton_usdt_provider = JettonUsdtProvider(
        client=ton_rpc_http_client,
        jetton_master_address=ton_rpc_settings.usdt_jetton_master,
    )
    ton_payout_adapter: ITonPayoutAdapter = TonRpcAdapter(
        client=ton_rpc_http_client,
        settings=ton_rpc_settings,
        jetton_provider=jetton_usdt_provider,
        signer=ton_message_signer,
    )
    # Спринт 4.1-D / D.6: `IWalletRepository` для use-case-ов
    # `LinkWallet` / `ClaimPrize`. Upsert через ON CONFLICT (Postgres/SQLite).
    wallet_repo: IWalletRepository = SqlAlchemyWalletRepository(uow=uow)
    # Спринт 4.1-F (шаг F.7): config-flag-режим TON Connect 2.0-verify-flow-а.
    # `sandbox` — `SandboxTonConnectVerifier` (D.10.c stub) + `InMemoryNonceStore`
    # (in-process dict); `production` — `TonConnectProductionVerifier` (F.5.c,
    # реальный Ed25519-verify) + `SqlAlchemyNonceStore` (F.6.b, persistent
    # atomic-CAS). Default `sandbox` для backward-compatibility на момент
    # 4.1-F-merge-а; mainnet включается env-флагом
    # `BOT_TON_CONNECT_VERIFIER_MODE=production`.
    ton_connect_settings = settings.ton_connect
    ton_connect_verifier: ITonConnectVerifier
    nonce_store: INonceStore
    if ton_connect_settings.verifier_mode == "production":
        ton_connect_verifier = TonConnectProductionVerifier(
            config=TonConnectProductionConfig(
                allowed_domains=ton_connect_settings.allowed_domains,
                max_age_seconds=ton_connect_settings.max_age_seconds,
                clock_skew_seconds=ton_connect_settings.clock_skew_seconds,
            ),
            clock=clock,
        )
        nonce_store = SqlAlchemyNonceStore(uow=uow, clock=clock)
    else:
        # sandbox-mode: D.10.c stub (принимает non-empty proof только в testnet,
        # mainnet → fail-closed) + in-process dict-nonce-store (теряется при
        # рестарте, для unit/integration-тестов и testnet-демо).
        ton_connect_verifier = SandboxTonConnectVerifier(
            is_sandbox=ton_rpc_settings.is_sandbox,
        )
        nonce_store = InMemoryNonceStore()
    request_link_wallet_proof = RequestLinkWalletProof(
        nonce_store=nonce_store,
        clock=clock,
        config=RequestLinkWalletProofConfig(
            canonical_domain=ton_connect_settings.canonical_domain,
            nonce_ttl_seconds=ton_connect_settings.nonce_ttl_seconds,
        ),
    )
    link_wallet = LinkWallet(
        wallet_repository=wallet_repo,
        ton_connect_verifier=ton_connect_verifier,
        nonce_store=nonce_store,
        audit_logger=audit,
        clock=clock,
    )
    claim_prize = ClaimPrize(
        prize_lot_repository=prize_lot_repo,
        prize_pool_repository=prize_pool_repo,
        wallet_repository=wallet_repo,
        payout_adapter=ton_payout_adapter,
        audit_logger=audit,
        clock=clock,
        payout_freeze_repository=payout_freeze_repo,
        payout_limit_checker=payout_limit_checker,
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
        business_metrics=business_metrics,
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
        business_metrics=business_metrics,
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
        business_metrics=business_metrics,
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

    # ── Спринт 4.9: Канал-анонсы ──
    announcement_publisher: IAnnouncementPublisher | None = None
    announcement_stats_query: IAnnouncementStatsQuery | None = None
    publish_weekly_digest: PublishWeeklyDigest | None = None
    publish_leaderboard: PublishLeaderboard | None = None
    if settings.bot.announcement_channel_id is not None and bot is not None:
        announcement_publisher = AiogramAnnouncementPublisher(bot=bot)
        announcement_stats_query = SqlAlchemyAnnouncementStatsQuery(
            session_factory=session_maker,
        )
        publish_weekly_digest = PublishWeeklyDigest(
            publisher=announcement_publisher,
            players_query=top_players_query,
            clans_query=top_clans_query,
            stats_query=announcement_stats_query,
            clock=clock,
        )
        publish_leaderboard = PublishLeaderboard(
            publisher=announcement_publisher,
            players_query=top_players_query,
            clans_query=top_clans_query,
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
        metrics_registry=metrics_registry,
        business_metrics=business_metrics,
        oracle_templates=oracle_templates,
        duel_log_templates=duel_log_templates,
        ai_oracle_provider=ai_oracle_provider,
        ai_forest_provider=ai_forest_provider,
        ai_duel_provider=ai_duel_provider,
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
        prize_lot_repo=prize_lot_repo,
        wallet_repo=wallet_repo,
        payout_freeze_repo=payout_freeze_repo,
        payout_limit_checker=payout_limit_checker,
        ton_payout_adapter=ton_payout_adapter,
        ton_connect_verifier=ton_connect_verifier,
        nonce_store=nonce_store,
        tg_stars_verifier=tg_stars_verifier,
        generate_prize_lots=generate_prize_lots,
        request_link_wallet_proof=request_link_wallet_proof,
        link_wallet=link_wallet,
        claim_prize=claim_prize,
        get_prize_pool_status=get_prize_pool_status,
        refund_lot=refund_lot,
        freeze_payouts=freeze_payouts_uc,
        unfreeze_payouts=unfreeze_payouts_uc,
        expire_reserved_prize_lots=expire_reserved_prize_lots,
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
        announcement_publisher=announcement_publisher,
        announcement_stats_query=announcement_stats_query,
        publish_weekly_digest=publish_weekly_digest,
        publish_leaderboard=publish_leaderboard,
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
    # Спринт 4.1-D — bot-handler `/roulette_paid` теперь проверяет
    # подпись `invoice_payload`-а HMAC-верификатором (D.8.c). Раньше
    # `tg_stars_verifier` не пробрасывался в workflow-data (handler
    # бросал MissingDependencyError на первом же платеже). На D.10.c
    # composition root собирает `HmacTgStarsPayloadVerifier` из
    # `TgStarsSettings`-секрета и пробрасывает в dispatcher.
    dispatcher["tg_stars_verifier"] = container.tg_stars_verifier
    # Спринт 4.1-D — bot-handler-ы `/link_wallet*` (личка-only) и
    # `/claim_prize <lot_id>`. `link_wallet`-use-case верифицирует
    # `ton_proof` (D.6 — manual entry; production — TON Connect signature
    # verification, добавится в 4.1-E). `claim_prize`-use-case проверяет
    # `wallet.address == recipient_address`, вызывает `ITonPayoutAdapter`
    # и обрабатывает refund-ветку (`actual_fee > fee_buffer`). Handler-ы
    # требуют доступа к `wallet_repo` / `prize_lot_repo` для read-side
    # отображения карточек.
    # Спринт 4.1-F (шаг F.8.a) — `RequestLinkWalletProof`-use-case (phase-1
    # двухфазного flow привязки кошелька): bot-handler `/link_wallet
    # <ton|usdt> <address>` через него получает server-issued nonce +
    # canonical-domain + expires_at и рендерит инструкцию игроку
    # «подпишите nonce в TonConnect-app-е, отправьте через
    # /link_wallet_confirm». Composition root (F.7) уже собрал use-case
    # из `TonConnectSettings` + `INonceStore`-имплементации, осталось
    # пробросить в workflow_data.
    dispatcher["request_link_wallet_proof"] = container.request_link_wallet_proof
    dispatcher["link_wallet"] = container.link_wallet
    dispatcher["claim_prize"] = container.claim_prize
    dispatcher["wallet_repository"] = container.wallet_repo
    dispatcher["prize_lot_repository"] = container.prize_lot_repo
    # Спринт 4.1-E — admin-команды `/prize_pool`, `/refund_lot`,
    # `/freeze_payouts`, `/unfreeze_payouts` (E.12–E.14) требуют доступа
    # к `IPayoutFreezeRepository` (set_frozen/set_unfrozen/get_state) и
    # `IPayoutLimitChecker` (read-side для статус-отчёта `/prize_pool`).
    dispatcher["payout_freeze_repository"] = container.payout_freeze_repo
    dispatcher["payout_limit_checker"] = container.payout_limit_checker
    dispatcher["get_prize_pool_status"] = container.get_prize_pool_status
    # 4.1-E.13: `dispatch_refund_lot` (фаза 2 `/refund_lot`) живёт в
    # `ConfirmDispatchDeps.refund_lot` — `admin_support.handle_confirm`
    # резолвит его из workflow-data и вкладывает в `deps`-контейнер
    # перед регистрированным dispatcher-ом. Сам handler фазы 1 вызывает
    # только `RequestAdminConfirm` (уже проброшен в dispatcher раньше).
    dispatcher["refund_lot"] = container.refund_lot
    # 4.1-E.14: `dispatch_(un)freeze_payouts` (фаза 2 соотв-их команд)
    # живёт в `ConfirmDispatchDeps.freeze_payouts` / `.unfreeze_payouts` —
    # `admin_support.handle_confirm` резолвит оба из workflow-data и вкладывает
    # в `deps`-контейнер перед вызовом зарегистрированного dispatcher-а.
    # Сами handler-ы фазы 1 вызывают только `RequestAdminConfirm`
    # (уже проброшен в dispatcher выше).
    dispatcher["freeze_payouts"] = container.freeze_payouts
    dispatcher["unfreeze_payouts"] = container.unfreeze_payouts
    # Канал-анонсы (Спринт 4.9)
    dispatcher["publish_weekly_digest"] = container.publish_weekly_digest
    dispatcher["publish_leaderboard"] = container.publish_leaderboard
    dispatcher["announcement_channel_id"] = container.settings.bot.announcement_channel_id
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


async def _announcement_scheduler(container: Container, *, interval_seconds: float = 60.0) -> None:
    """Фоновый таск проверки расписания еженедельного дайджеста (Спринт 4.9).

    Каждые `interval_seconds` секунд проверяет, совпадает ли текущее
    время с cron-выражением и не публиковался ли дайджест на этой неделе.
    """
    channel_id = container.settings.bot.announcement_channel_id
    if (
        channel_id is None
        or container.publish_weekly_digest is None
        or not container.settings.bot.announcement_weekly_enabled
    ):
        return

    cron_expr = container.settings.bot.announcement_weekly_cron
    published_weeks: set[tuple[int, int]] = set()

    while True:
        try:
            now = container.clock.now()
            iso = now.isocalendar()
            week_key = (iso[0], iso[1])

            if week_key not in published_weeks and _cron_matches(cron_expr, now):
                await container.publish_weekly_digest.execute(
                    channel_id=channel_id,
                )
                published_weeks.add(week_key)
                logger.info(
                    "announcement_scheduler_published",
                    extra={"week_key": week_key},
                )
        except Exception:
            logger.warning("announcement_scheduler_error", exc_info=True)
        await asyncio.sleep(interval_seconds)


def _cron_matches(cron_expr: str, now: datetime) -> bool:
    """Check if current time matches the cron expression (minute hour dom month dow)."""

    parts = cron_expr.split()
    if len(parts) != 5:
        return False

    minute_str, hour_str, dom_str, month_str, dow_str = parts
    return (
        _cron_field_matches(minute_str, now.minute)
        and _cron_field_matches(hour_str, now.hour)
        and _cron_field_matches(dom_str, now.day)
        and _cron_field_matches(month_str, now.month)
        and _cron_field_matches(dow_str, now.isoweekday() % 7)
    )


def _cron_field_matches(field: str, value: int) -> bool:
    """Check if a single cron field matches the value."""
    if field == "*":
        return True
    for part in field.split(","):
        if "/" in part:
            base, step = part.split("/", 1)
            step_val = int(step)
            if base == "*":
                if value % step_val == 0:
                    return True
            else:
                base_val = int(base)
                if value >= base_val and (value - base_val) % step_val == 0:
                    return True
        elif "-" in part:
            low, high = part.split("-", 1)
            if int(low) <= value <= int(high):
                return True
        elif int(part) == value:
            return True
    return False


async def _business_metrics_dau_poller(
    container: Container, *, interval_seconds: float = 60.0
) -> None:
    """Фоновый таск-snapshot DAU в `pipirik_dau_active_users`-gauge (Спринт 4.1-N).

    Hot-path use-case `RecordPlayerActivity` НЕ инструментирован — это
    счётчик-на-message, который дорожает на больших чатах и не несёт
    самостоятельной ценности. Вместо инкрементов на каждый event здесь
    раз в `interval_seconds` секунд (default = 60) считывается актуальное
    значение через `IDauCounter.current()` и устанавливается в gauge.

    Запускается только при `business_metrics`-нумере (`needs_redis=True` +
    `PrometheusBusinessMetrics`). При `NullBusinessMetrics()`-default-е
    task сразу завершается (зачем тратить asyncio-цикл на no-op).
    """
    if isinstance(container.business_metrics, NullBusinessMetrics):
        return
    while True:
        try:
            value = await container.dau_counter.current()
            container.business_metrics.set_dau(value)
        except Exception:
            logger.warning("DAU snapshot failed", exc_info=True)
        await asyncio.sleep(interval_seconds)


async def _ai_refresh_loop(container: Container, *, interval_seconds: float) -> None:
    """Фоновый таск периодического refresh-а AI-шаблонов (Спринт 4.1-M).

    Вызывается только если включён `AI_ENABLED=True` (т.е. хотя бы один из
    `ai_*_provider` не `None`). Раз в `interval_seconds` секунд пробегает
    по всем `SUPPORTED_LOCALES` и вызывает `refresh(locale=...)` на каждом
    AI-провайдере. Ошибки LLM не пробрасываются — провайдеры сами их ловят
    и сохраняют старый кэш (см. `AiOracleTemplateProvider.refresh`).

    Стартует с немедленного refresh-а (без `sleep(interval)` сначала),
    чтобы при первом запуске AI-кэш заполнился сразу, а не через 24 ч.
    """
    providers = [
        p
        for p in (
            container.ai_oracle_provider,
            container.ai_forest_provider,
            container.ai_duel_provider,
        )
        if p is not None
    ]
    if not providers:
        return
    while True:
        for locale in sorted(SUPPORTED_LOCALES):
            for provider in providers:
                await provider.refresh(locale=locale)
        await asyncio.sleep(interval_seconds)


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
        # 4.1-D / D.9.d: hourly cron `ExpireReservedPrizeLots` (1 инстанс,
        # обход валют внутри use-case-а).
        scheduler.schedule_expire_reserved_prize_lots_cron()

    # Спринт 4.1-J (шаг J.2): Prometheus-`/metrics`-endpoint. Поднимаем
    # отдельный aiohttp-web-runner на `BOT_METRICS_PORT` (default 9100)
    # **только** если activity-lock/lobby/dau бэкенд выставлен в `redis`
    # (`container.metrics_registry is not None`). Default-sql-конфигурация
    # observability-сервер не поднимает.
    metrics_runner: web.AppRunner | None = None
    if container.metrics_registry is not None:
        metrics_app = build_metrics_app(container.metrics_registry)
        metrics_runner = web.AppRunner(metrics_app)
        await metrics_runner.setup()
        site = web.TCPSite(metrics_runner, host="0.0.0.0", port=settings.bot.metrics_port)
        await site.start()

    # Спринт 4.1-M: фоновый таск refresh-а AI-кэша. Запускается только
    # если хотя бы один AI-провайдер собран (AI_ENABLED=True + openai
    # импортируется + валидный API-key). Иначе task завершается мгновенно.
    ai_refresh_task: asyncio.Task[None] | None = None
    if (
        container.ai_oracle_provider is not None
        or container.ai_forest_provider is not None
        or container.ai_duel_provider is not None
    ):
        ai_refresh_task = asyncio.create_task(
            _ai_refresh_loop(
                container,
                interval_seconds=settings.ai.refresh_interval_hours * 3600.0,
            ),
            name="ai-refresh-loop",
        )

    # Спринт 4.1-N: фоновый DAU-poller. При NullBusinessMetrics()-default-е
    # task сам завершится сразу — мы это не проверяем здесь повторно,
    # чтобы не дублировать isinstance-проверку.
    dau_metrics_task: asyncio.Task[None] = asyncio.create_task(
        _business_metrics_dau_poller(container),
        name="business-metrics-dau-poller",
    )

    # Спринт 4.9: фоновый таск расписания еженедельных анонсов.
    announcement_task: asyncio.Task[None] | None = None
    if container.publish_weekly_digest is not None:
        announcement_task = asyncio.create_task(
            _announcement_scheduler(container),
            name="announcement-scheduler",
        )

    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=list(_ALLOWED_UPDATES),
        )
    finally:
        dau_metrics_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await dau_metrics_task
        if announcement_task is not None:
            announcement_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await announcement_task
        if ai_refresh_task is not None:
            ai_refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await ai_refresh_task
        if isinstance(scheduler, APSchedulerDelayedJobScheduler):
            scheduler.shutdown(wait=False)
        if metrics_runner is not None:
            await metrics_runner.cleanup()
        await bot.session.close()


def main() -> None:  # pragma: no cover
    """Sync wrapper над `run()`. Используется как ``python -m``-entry."""
    asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    main()
