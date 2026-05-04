"""Composition root для Telegram-бота.

ГДД §0 / development_plan.md Спринт 0.1.4: вся сборка зависимостей —
ровно в этом модуле. Никаких сервис-локаторов / глобальных DI-контейнеров —
явный конструктор `Container` собирает всё, что нужно use-case-ам, и
пробрасывает в bot-handlers через `Dispatcher` data.

В Спринте 0.1 здесь — только каркас (типизированный контейнер с TODO).
Реальные адаптеры (`SqlAlchemyUnitOfWork`, `Aiogram*`, `RealClock`,
`RealRandom`) появятся в Спринте 0.2 / 1.1, не раньше.
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


def build_container() -> Container:
    """Собрать контейнер для production-запуска.

    В Спринте 0.1 ещё нечего собирать — реализации портов появятся
    в `infrastructure/` начиная со Спринта 0.2. Сейчас — placeholder,
    помечен как `NotImplementedError`, чтобы в `bot/main.py` нельзя
    было случайно запустить «пустой бот».
    """
    raise NotImplementedError(
        "build_container() появится в Спринте 0.2 (infrastructure adapters). "
        "См. development_plan.md → Спринт 0.2.",
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
