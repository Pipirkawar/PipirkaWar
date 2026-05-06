"""`AdminGuard` — outer-middleware расширенного админ-интерфейса (Спринт 2.5-A.2).

Что делает:

1. Берёт `tg_identity` (его кладёт `AuthMiddleware` уровнем выше).
2. Ходит в `IAdminRepository.get_by_tg_id(tg_user_id)` через `IUnitOfWork`.
3. Если найден активный `Admin` — кладёт его в `data["admin"]`. Иначе —
   `data["admin"] = None`.
4. **Всегда** вызывает `handler(event, data)` (это enrichment-middleware,
   а не gate-keeper). Сам по себе апдейт не отбрасывается — конкретные
   `/admin_*`-handler-ы и use-case-декораторы `requires_*` (Спринт 1.2.B+)
   проверяют `data["admin"]` и решают, отвечать пользователю или нет.

Почему именно так (а не «отбрасывать чужих»):

- Тот же middleware будет навешен в Спринтах 2.5-B/C/D на админ-роутер —
  но и в обычном чате он не должен ломать поток (например, `/profile`
  от не-админа должен работать как раньше).
- Молчаливый skip для чужих в /admin_* реализуется на уровне фильтра
  команды или handler-а (см. ГДД §18.6.4: «не светим в /audit чужие
  попытки» — если бы middleware отвечал «недостаточно прав», он бы
  засветил факт существования команды).
- Per-update DB-roundtrip приемлем потому, что middleware будет
  навешен **только** на админ-router, а не на глобальный dispatcher
  (см. вызов `register_middlewares(...admin_guard=...)`).

Инвариант: если `data["admin"]` есть и не `None` — это **активный**
админ (`is_active=True`). Деактивированные админы через middleware не
проходят.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from pipirik_wars.bot.middlewares.auth import DATA_KEY as AUTH_DATA_KEY, TgIdentity
from pipirik_wars.domain.admin import Admin, IAdminRepository
from pipirik_wars.domain.shared.ports import IUnitOfWork

DATA_KEY = "admin"


class AdminGuard(BaseMiddleware):
    """Кладёт `data["admin"]` (`Admin | None`) на основании `tg_identity`."""

    __slots__ = ("_admins", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
    ) -> None:
        super().__init__()
        self._uow = uow
        self._admins = admins

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        identity = data.get(AUTH_DATA_KEY)
        admin: Admin | None = None
        if isinstance(identity, TgIdentity):
            async with self._uow:
                admin = await self._admins.get_by_tg_id(identity.tg_user_id)
            if admin is not None and not admin.is_active:
                # Деактивированные не считаются админами для целей
                # текущей команды — see ГДД §18.6 (revoke = отзыв прав).
                admin = None
        data[DATA_KEY] = admin
        return await handler(event, data)


__all__ = ["DATA_KEY", "AdminGuard"]
