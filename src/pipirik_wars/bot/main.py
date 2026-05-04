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

from pipirik_wars.application.balance import ReloadBalance
from pipirik_wars.application.clan import (
    FreezeClan,
    JoinClan,
    MigrateClanChatId,
    RegisterClan,
)
from pipirik_wars.application.dau import GetDauStats, SetMaxDau
from pipirik_wars.application.player import GetProfile, RegisterPlayer
from pipirik_wars.bot.handlers import register_routers
from pipirik_wars.bot.middlewares import register_middlewares
from pipirik_wars.domain.admin import IAdminRepository
from pipirik_wars.domain.balance import IBalanceConfig, IBalanceReloader
from pipirik_wars.domain.clan import IClanMembershipRepository, IClanRepository
from pipirik_wars.domain.dau import IDauCounter, IDauLimit
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.shared.ports import (
    IAuditLogger,
    IClock,
    IIdempotencyKey,
    IRandom,
    IUnitOfWork,
)
from pipirik_wars.infrastructure.balance import YamlBalanceLoader
from pipirik_wars.infrastructure.clock import RealClock
from pipirik_wars.infrastructure.dau import InMemoryDauCounter, InMemoryDauLimit
from pipirik_wars.infrastructure.db.engine import build_engine, build_sessionmaker
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyAdminRepository,
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.services import (
    SqlAlchemyAuditLogger,
    SqlAlchemyIdempotencyService,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.random import RealRandom
from pipirik_wars.infrastructure.rate_limit import (
    InMemoryTokenBucketRateLimiter,
    IRateLimiter,
)
from pipirik_wars.infrastructure.settings import Settings

# Путь к балансовому файлу по умолчанию (относительно cwd процесса).
# Деплой кладёт `config/balance.yaml` рядом с бинарём; локально
# pytest/`make ci` стартуют из корня репо, где он и лежит.
_DEFAULT_BALANCE_YAML = Path("config/balance.yaml")


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

    # Репозитории (Спринт 1.1.D + 1.1.E)
    players: IPlayerRepository
    clans: IClanRepository
    clan_members: IClanMembershipRepository
    admins: IAdminRepository

    # DAU Gate (Спринт 1.2.B)
    dau_counter: IDauCounter
    dau_limit: IDauLimit

    # Use-case-ы (Спринт 1.1.D + 1.1.E + 1.2.B)
    register_player: RegisterPlayer
    register_clan: RegisterClan
    migrate_clan: MigrateClanChatId
    join_clan: JoinClan
    freeze_clan: FreezeClan
    get_profile: GetProfile
    reload_balance: ReloadBalance
    get_dau_stats: GetDauStats
    set_max_dau: SetMaxDau


def build_container(
    settings: Settings | None = None,
    *,
    balance_yaml_path: Path | None = None,
) -> Container:
    """Собрать контейнер для production-запуска.

    Production: настройки из env (через `pydantic-settings`).
    Tests: можно передать заранее собранный
    `Settings(db=DatabaseSettings(url=...))`.

    `balance_yaml_path` — переопределение пути к `balance.yaml`
    (по умолчанию ``config/balance.yaml``). Loader **lazy** — файл
    читается только при первом `container.balance.get()`.

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
    register_player = RegisterPlayer(
        uow=uow,
        players=players,
        audit=audit,
        clock=clock,
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
    dau_counter = InMemoryDauCounter(clock=clock)
    dau_limit = InMemoryDauLimit(initial=settings.bot.max_dau)
    get_dau_stats = GetDauStats(counter=dau_counter, limit=dau_limit)
    set_max_dau = SetMaxDau(
        uow=uow,
        admins=admins,
        limit=dau_limit,
        audit=audit,
        clock=clock,
    )
    return Container(
        clock=clock,
        random=RealRandom(),
        uow=uow,
        idempotency=SqlAlchemyIdempotencyService(uow=uow),
        audit=audit,
        balance=balance,
        balance_reloader=balance,
        rate_limiter=rate_limiter,
        settings=settings,
        players=players,
        clans=clans,
        clan_members=clan_members,
        admins=admins,
        dau_counter=dau_counter,
        dau_limit=dau_limit,
        register_player=register_player,
        register_clan=register_clan,
        migrate_clan=migrate_clan,
        join_clan=join_clan,
        freeze_clan=freeze_clan,
        get_profile=get_profile,
        reload_balance=reload_balance,
        get_dau_stats=get_dau_stats,
        set_max_dau=set_max_dau,
    )


def build_dispatcher(container: Container) -> Dispatcher:
    """Собрать aiogram `Dispatcher` со стеком middleware-ов и роутерами.

    Use-case-ы регистрируются в `dispatcher` workflow-data — aiogram
    автоматически пробросит их в handler-ы по имени параметра.
    """
    dispatcher = Dispatcher()
    register_middlewares(dispatcher, limiter=container.rate_limiter)
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
    container = build_container(settings, balance_yaml_path=balance_yaml_path)
    bot = Bot(
        token=container.settings.bot.token.get_secret_value(),
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dispatcher = build_dispatcher(container)
    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=list(_ALLOWED_UPDATES),
        )
    finally:
        await bot.session.close()


def main() -> None:  # pragma: no cover
    """Sync wrapper над `run()`. Используется как ``python -m``-entry."""
    asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    main()
