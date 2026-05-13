"""Helper для проверки RBAC в admin-use-case-ах (Спринт 2.5-D.8).

Каждый admin-use-case должен:

1. Загрузить `Admin` через `IAdminRepository.get_by_tg_id`.
2. Убедиться, что админ активен (`is_active`) — иначе `AuthorizationError`.
3. Проверить, что роль админа покрывает запрашиваемую команду через
   `IAdminAuthorizationPolicy.is_authorized(...)` — иначе записать
   `ADMIN_AUTHORIZATION_DENIED` в `admin_audit_log` и бросить
   `AdminAuthorizationDeniedError`.

Шаги (1) + (2) уже стандартизированы в use-case-ах паттерном
`if admin is None or not admin.is_active: raise AuthorizationError(...)`.
Этот модуль добавляет шаг (3): функция `ensure_admin_authorized(...)`
открывает **отдельный, короткоживущий** `IUnitOfWork`, пишет
`ADMIN_AUTHORIZATION_DENIED` и коммитит до того, как поднять
`AdminAuthorizationDeniedError`. Так audit-запись остаётся в БД
независимо от того, что произойдёт дальше с основной транзакцией
use-case-а (например, она ещё не открыта или будет откачена).

Use-case вызывает функцию **до** открытия своего основного
`async with self._uow:`-блока — это и проще (помещение try/except
внутрь uow усложняет логику), и безопасно (помечаем попытку
эскалации даже при последующем сбое). Если admin авторизован —
функция возвращает `None`, побочных эффектов нет.

Запись содержит:

* `target_kind` / `target_id` — переданные use-case-ом (например,
  `("player", "12345")`); это позволяет в `/audit` отфильтровать
  попытки эскалации привилегий по конкретному игроку/клану.
* `after.command_kind` — строковое имя команды (для удобства
  фильтрации в Telegram и без знания внутренней матрицы).
* `after.actor_role` — реальная роль админа на момент попытки
  (помогает анализировать аномалии: «почему support дёрнул
  /grant_length?»).
"""

from __future__ import annotations

from datetime import datetime

from pipirik_wars.domain.admin import (
    Admin,
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminAuthorizationDeniedError,
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
)
from pipirik_wars.domain.shared.ports import IUnitOfWork


async def ensure_admin_authorized(
    *,
    admin: Admin,
    command_kind: AdminCommandKind,
    policy: IAdminAuthorizationPolicy,
    audit: IAdminAuditLogger,
    uow: IUnitOfWork,
    target_kind: str,
    target_id: str,
    tg_chat_id: int | None,
    occurred_at: datetime,
    reason_suffix: str | None = None,
    source: AdminAuditSource = AdminAuditSource.BOT,
    ip: str | None = None,
) -> None:
    """Проверить RBAC; при отказе — записать `ADMIN_AUTHORIZATION_DENIED`
    в **отдельной** транзакции и бросить `AdminAuthorizationDeniedError`.

    Должна вызываться **до** открытия основного `async with self._uow:`
    use-case-а: функция сама открывает и коммитит свой UoW для записи
    audit-а денайла. Это гарантирует, что попытка эскалации зафиксирована
    в БД независимо от того, что произойдёт дальше.

    Параметры:

    * `admin` — уже загруженная активная сущность (use-case проверил
      `is_active` и `id is not None` до вызова).
    * `command_kind` — константа `AdminCommandKind` запрошенной команды.
    * `policy` / `audit` / `uow` — DI-зависимости use-case-а.
    * `target_kind` / `target_id` — контекст запрошенной команды
      (например, `("player", "12345")` для `BanPlayer`). Сохраняется в
      audit-записи как-есть.
    * `tg_chat_id` — id чата команды (для `source=BOT`); `None` для web.
    * `occurred_at` — timestamp попытки (берётся из `IClock.now()` use-case-ом).
    * `reason_suffix` — дополнительный человекочитаемый комментарий;
      полезен для фильтра в `/audit` без JSON-парсинга `after`.

    Если admin авторизован — функция возвращает `None`, ничего не
    пишет, дополнительных эффектов нет.
    """
    if policy.is_authorized(admin, command_kind):
        return

    admin_id = admin.id
    if admin_id is None:  # pragma: no cover — invariant of the repo
        raise RuntimeError("admin.id is None at authorization check")

    detail = f"role={admin.role.value} command={command_kind.value} target={target_id!r}"
    reason = f"authz_denied:{command_kind.value}:role={admin.role.value}" + (
        f":{reason_suffix}" if reason_suffix else ""
    )
    async with uow:
        await audit.record(
            AdminAuditEntry(
                admin_id=admin_id,
                action=AdminAuditAction.ADMIN_AUTHORIZATION_DENIED,
                target_kind=target_kind,
                target_id=target_id,
                before=None,
                after={
                    "command_kind": command_kind.value,
                    "actor_role": admin.role.value,
                },
                reason=reason,
                idempotency_key=None,
                source=source,
                tg_chat_id=tg_chat_id,
                ip=ip,
                occurred_at=occurred_at,
            ),
        )
    raise AdminAuthorizationDeniedError(
        command_kind=command_kind,
        actor_role=admin.role,
        detail=detail,
    )


__all__ = ["ensure_admin_authorized"]
