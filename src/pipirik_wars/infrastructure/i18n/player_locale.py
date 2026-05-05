"""`PlayerLocaleResolverDB` — реализация `IPlayerLocaleResolver` поверх БД.

Спринт 1.5.F / ПД 1.5.2: фоновые jobs (`TelegramForestFinishNotifier`)
и `LocaleMiddleware` спрашивают «какой язык хочет игрок» по `tg_id`.
Резолвер делает SELECT `locale_override FROM users WHERE tg_id = :tg_id`
через активный UoW. Если ряд найден и колонка непустая — возвращает
`Locale(...)`. Иначе — `None` (caller дальше фолбэчит сам).

Транзакционность:

- метод `resolve_for_tg_id` входит в `async with self._uow`. Если UoW
  уже открыт (например, middleware вызывается внутри другого
  use-case-а — на MVP такого нет), это безопасно: вложенный
  `__aenter__` в `SqlAlchemyUnitOfWork` создаёт savepoint.
- Никаких записей — только read.
"""

from __future__ import annotations

from sqlalchemy import select

from pipirik_wars.application.i18n import IPlayerLocaleResolver, Locale
from pipirik_wars.application.i18n.locale import SUPPORTED_LOCALES
from pipirik_wars.infrastructure.db.models import UserORM
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork


class PlayerLocaleResolverDB(IPlayerLocaleResolver):
    """Реализация `IPlayerLocaleResolver` поверх таблицы `users`."""

    __slots__ = ("_uow",)

    def __init__(self, *, uow: SqlAlchemyUnitOfWork) -> None:
        self._uow = uow

    async def resolve_for_tg_id(self, tg_id: int) -> Locale | None:
        async with self._uow:
            stmt = select(UserORM.locale_override).where(UserORM.tg_id == tg_id)
            result = await self._uow.session.execute(stmt)
            override = result.scalar_one_or_none()
        if override is None:
            return None
        if override not in SUPPORTED_LOCALES:
            # CHECK-constraint в БД должен это запрещать; но если кто-то
            # руко-патчем подсунул мусор — лучше вернуть None и не падать.
            return None
        return Locale(code=override)


__all__ = ["PlayerLocaleResolverDB"]
