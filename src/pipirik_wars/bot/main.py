"""Composition root для Telegram-бота.

ГДД §0 / development_plan.md Спринт 0.1.4: вся сборка зависимостей —
ровно в этом модуле. Никаких сервис-локаторов / глобальных DI-контейнеров —
явный конструктор `Container` собирает всё, что нужно use-case-ам, и
пробрасывает в bot-handlers через `Dispatcher` data.

Спринт 0.2: `build_container()` собирает реальные адаптеры
(`SqlAlchemyUnitOfWork`, `RealClock`, `RealRandom`,
`SqlAlchemyIdempotencyService`, `SqlAlchemyAuditLogger`).
`main()` остаётся placeholder-ом — entry point появится в Спринте 1.1
(aiogram Dispatcher + handlers).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.shared.ports import (
    IAuditLogger,
    IClock,
    IIdempotencyKey,
    IRandom,
    IUnitOfWork,
)
from pipirik_wars.infrastructure.clock import RealClock
from pipirik_wars.infrastructure.db.engine import build_engine, build_sessionmaker
from pipirik_wars.infrastructure.db.services import (
    SqlAlchemyAuditLogger,
    SqlAlchemyIdempotencyService,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.random import RealRandom
from pipirik_wars.infrastructure.settings import Settings


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
    settings: Settings


def build_container(settings: Settings | None = None) -> Container:
    """Собрать контейнер для production-запуска.

    Production: настройки из env (через `pydantic-settings`).
    Tests: можно передать заранее собранный `Settings(db=DatabaseSettings(url=...))`.

    NB: `create_async_engine()` lazy — реальное подключение к БД
    произойдёт только при первом запросе.
    """
    settings = settings or Settings()
    engine = build_engine(settings.db)
    session_maker = build_sessionmaker(engine)
    uow = SqlAlchemyUnitOfWork(session_maker)
    return Container(
        clock=RealClock(),
        random=RealRandom(),
        uow=uow,
        idempotency=SqlAlchemyIdempotencyService(uow=uow),
        audit=SqlAlchemyAuditLogger(uow=uow),
        settings=settings,
    )


def main() -> None:
    """Entry point. Будет реализован в Спринте 1.1.

    Сейчас — placeholder, чтобы `python -m pipirik_wars.bot.main` не
    делал ничего «случайно».
    """
    raise NotImplementedError(
        "main() появится в Спринте 1.1 (регистрация и БД). См. development_plan.md → Спринт 1.1.",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
