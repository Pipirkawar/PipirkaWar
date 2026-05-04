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
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from pipirik_wars.bot.handlers import register_routers
from pipirik_wars.bot.middlewares import register_middlewares
from pipirik_wars.domain.balance import IBalanceConfig
from pipirik_wars.domain.shared.ports import (
    IAuditLogger,
    IClock,
    IIdempotencyKey,
    IRandom,
    IUnitOfWork,
)
from pipirik_wars.infrastructure.balance import YamlBalanceLoader
from pipirik_wars.infrastructure.clock import RealClock
from pipirik_wars.infrastructure.db.engine import build_engine, build_sessionmaker
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
    """Контейнер инфраструктурных зависимостей.

    Иммутабельный, по одному экземпляру на процесс. Use-case-ы
    конструируются с явными аргументами `clock=container.clock`, без
    «магического» резолва.
    """

    clock: IClock
    random: IRandom
    uow: IUnitOfWork
    idempotency: IIdempotencyKey
    audit: IAuditLogger
    balance: IBalanceConfig
    rate_limiter: IRateLimiter
    settings: Settings


def build_container(
    settings: Settings | None = None,
    *,
    balance_yaml_path: Path | None = None,
) -> Container:
    """Собрать контейнер для production-запуска.

    Production: настройки из env (через `pydantic-settings`).
    Tests: можно передать заранее собранный `Settings(db=DatabaseSettings(url=...))`.

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
    rate_limiter = InMemoryTokenBucketRateLimiter(
        capacity=settings.bot.default_throttle_capacity,
        refill_per_second=settings.bot.default_throttle_per_second,
        clock=clock,
    )
    return Container(
        clock=clock,
        random=RealRandom(),
        uow=uow,
        idempotency=SqlAlchemyIdempotencyService(uow=uow),
        audit=SqlAlchemyAuditLogger(uow=uow),
        balance=balance,
        rate_limiter=rate_limiter,
        settings=settings,
    )


def build_dispatcher(container: Container) -> Dispatcher:
    """Собрать aiogram `Dispatcher` со стеком middleware-ов и роутерами.

    Вынесено в отдельную функцию (а не «всё в `run()`»), чтобы тесты
    могли проверить факт регистрации middleware-ов и handler-ов на
    том же объекте, который пойдёт в production.
    """
    dispatcher = Dispatcher()
    register_middlewares(dispatcher, limiter=container.rate_limiter)
    register_routers(dispatcher)
    return dispatcher


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
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:  # pragma: no cover
    """Sync wrapper над `run()`. Используется как ``python -m``-entry."""
    asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    main()
