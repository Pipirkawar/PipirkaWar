"""Use-case `GetAdminAuditTrail` (Спринт 2.5-D.5, ГДД §18.6.4).

`/audit [target_tg_id] [action] [limit]` — read-side листинг
`admin_audit_log`-а. Команду может вызвать любой активный админ
(см. ГДД §18.6.4 — это операционный observability-инструмент); сам
факт обращения тоже пишется в `admin_audit_log` (`ADMIN_AUDIT_QUERIED`),
чтобы super-admin видел, кто и какие срезы аудита смотрел.

Параметры use-case-а (все опциональные):

- `target_admin_tg_id` — Telegram-ID админа, по которому фильтруем
  (use-case транслирует его во внутренний `Admin.id`). Если переданный
  tg_id никому не соответствует, возвращаем пустой результат
  (а не ошибку) — это валидный «никто такого не делал» сценарий.
- `action_value` — строковое значение `AdminAuditAction` для фильтра
  по категории. Невалидное значение → `AdminAuditActionUnknownError`.
- `limit` — верхняя граница выдачи, ограничивается use-case-ом
  значением `MAX_AUDIT_LIMIT` (50), чтобы Telegram-сообщение не
  расползалось. Дефолт — `DEFAULT_AUDIT_LIMIT` (20).

Без TOTP — read-only. Запись в `admin_audit_log` идёт **внутри** UoW
вместе с собственно SELECT-ом (read+write в одной транзакции —
SQLAlchemy умеет это поверх одного коннекта).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditRecord,
    AdminAuditSource,
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuditQuery,
    IAdminAuthorizationPolicy,
    IAdminRepository,
)
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork

#: Дефолтный размер выдачи `/audit` без явного `limit`-аргумента.
DEFAULT_AUDIT_LIMIT = 20
#: Жёсткий потолок выдачи (длинная простыня в Telegram-чате только
#: усложняет операционный поиск). Use-case clamp-ит входной `limit`
#: до этого значения.
MAX_AUDIT_LIMIT = 50


class AdminAuditActionUnknownError(ValueError):
    """Неизвестное значение `action`-фильтра.

    Поднимается use-case-ом при попытке передать строку, не входящую
    в whitelist `AdminAuditAction`. Сообщение — для отладки/логов;
    handler рендерит локализованный текст с подстановкой `value`.
    """

    def __init__(self, *, value: str) -> None:
        self.value = value
        super().__init__(f"unknown admin-audit action filter: {value!r}")


@dataclass(frozen=True, slots=True)
class GetAdminAuditTrailInput:
    """Параметры `/audit`-запроса."""

    actor_tg_id: int
    target_admin_tg_id: int | None = None
    action_value: str | None = None
    limit: int = DEFAULT_AUDIT_LIMIT
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class GetAdminAuditTrailOutput:
    """Результат: применённые фильтры + список записей.

    `target_admin_resolved` — `True`, если переданный `tg_id` нашёлся
    в `admins`. `False` — handler покажет «такого админа нет» вместо
    «нет записей по этому админу», чтобы оператор не путал
    «не делал ничего» и «не существует».
    """

    target_admin_tg_id: int | None
    target_admin_resolved: bool
    action: AdminAuditAction | None
    limit: int
    records: Sequence[AdminAuditRecord]


class GetAdminAuditTrail:
    """Use-case листинга админ-аудит-лога."""

    __slots__ = ("_admins", "_audit", "_authz", "_clock", "_query", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        query: IAdminAuditQuery,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._query = query
        self._audit = audit
        self._clock = clock
        self._authz = authz

    async def execute(self, inp: GetAdminAuditTrailInput) -> GetAdminAuditTrailOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover — invariant of the repo
            raise RuntimeError("admin.id is None after get_by_tg_id")

        action = self._parse_action(inp.action_value)
        limit = self._clamp_limit(inp.limit)
        now = self._clock.now()

        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.GET_ADMIN_AUDIT_TRAIL,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="admin_audit_log",
            target_id=(
                str(inp.target_admin_tg_id) if inp.target_admin_tg_id is not None else "all"
            ),
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
        )

        async with self._uow:
            target_admin_id: int | None = None
            target_resolved = True
            if inp.target_admin_tg_id is not None:
                target = await self._admins.get_by_tg_id(inp.target_admin_tg_id)
                if target is None or target.id is None:
                    target_resolved = False
                else:
                    target_admin_id = target.id

            if target_resolved:
                records = await self._query.list_recent(
                    limit=limit,
                    target_admin_id=target_admin_id,
                    action=action,
                )
            else:
                records = ()

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_AUDIT_QUERIED,
                    target_kind="admin_audit_log",
                    target_id=(
                        str(inp.target_admin_tg_id) if inp.target_admin_tg_id is not None else "all"
                    ),
                    before=None,
                    after={
                        "filter_action": action.value if action is not None else None,
                        "limit": limit,
                        "results_count": len(records),
                        "target_resolved": target_resolved,
                    },
                    reason=_build_reason(
                        target_admin_tg_id=inp.target_admin_tg_id,
                        action=action,
                        limit=limit,
                    ),
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return GetAdminAuditTrailOutput(
            target_admin_tg_id=inp.target_admin_tg_id,
            target_admin_resolved=target_resolved,
            action=action,
            limit=limit,
            records=tuple(records),
        )

    @staticmethod
    def _parse_action(value: str | None) -> AdminAuditAction | None:
        if value is None or value == "":
            return None
        try:
            return AdminAuditAction(value)
        except ValueError as exc:
            raise AdminAuditActionUnknownError(value=value) from exc

    @staticmethod
    def _clamp_limit(limit: int) -> int:
        if limit <= 0:
            return DEFAULT_AUDIT_LIMIT
        return min(limit, MAX_AUDIT_LIMIT)


def _build_reason(
    *,
    target_admin_tg_id: int | None,
    action: AdminAuditAction | None,
    limit: int,
) -> str:
    target = target_admin_tg_id if target_admin_tg_id is not None else "all"
    action_label = action.value if action is not None else "all"
    return f"audit:target={target},action={action_label},limit={limit}"


__all__ = [
    "DEFAULT_AUDIT_LIMIT",
    "MAX_AUDIT_LIMIT",
    "AdminAuditActionUnknownError",
    "GetAdminAuditTrail",
    "GetAdminAuditTrailInput",
    "GetAdminAuditTrailOutput",
]
