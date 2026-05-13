"""Use-case `VerifyAdminConfirm` (Спринт 2.5-A.3, ГДД §18.6).

Завершает поток TOTP-подтверждения: handler принимает 6-значный
код от админа, отдаёт сюда вместе с токеном, получает payload
исходной команды (если код верен) или одну из ошибок.

Безопасность:

* **Однократность токена.** `IAdminConfirmStore.pop` атомарно удаляет
  запись — даже если код неверный, токен в store-е НЕ остаётся.
  Это защищает от brute-force-а: 2 минуты × 6 цифр = 1 000 000
  попыток в минуту → попыток должно быть не больше 1.
* **Сверка `admin_id`.** Запись принадлежит админу, который её
  завёл. Если код вводит другой админ (тот же `tg_chat_id`,
  но другой `tg_user_id`) — отказ + audit `ADMIN_CONFIRM_FAILED`
  с пометкой `admin_mismatch`.
* **Проверка TTL.** `expires_at < now()` → отказ + audit. TTL
  выставлялся в `RequestAdminConfirm` (по дефолту 60 секунд).
* **Аудит проигрыша.** Невалидный код → запись `ADMIN_CONFIRM_FAILED`
  в `admin_audit_log`. Валидный → `ADMIN_CONFIRM_VERIFIED`. Это
  нужно, чтобы super-admin видел в `/audit` подозрительную
  активность (множественные failed-коды у одного админа).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminCommandKind,
    ConfirmAdminMismatchError,
    ConfirmCodeInvalidError,
    ConfirmTokenExpiredError,
    ConfirmTokenNotFoundError,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminConfirmStore,
    IAdminRepository,
    ITotpVerifier,
    TotpNotConfiguredError,
)
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


@dataclass(frozen=True, slots=True)
class VerifyAdminConfirmInput:
    """Параметры подтверждения."""

    actor_tg_id: int
    token: str
    code: str
    tg_chat_id: int | None = None
    source: AdminAuditSource = AdminAuditSource.BOT
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class VerifyAdminConfirmOutput:
    """Восстановленный контекст исходной команды."""

    command_kind: str
    target_kind: str
    target_id: str
    payload: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))


class VerifyAdminConfirm:
    """Проверка 6-значного TOTP-кода и возврат payload-а команды."""

    __slots__ = ("_admins", "_audit", "_authz", "_clock", "_store", "_totp", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        store: IAdminConfirmStore,
        totp: ITotpVerifier,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._store = store
        self._totp = totp
        self._audit = audit
        self._clock = clock
        self._authz = authz

    async def execute(self, inp: VerifyAdminConfirmInput) -> VerifyAdminConfirmOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        if admin.totp_secret is None:
            raise TotpNotConfiguredError(
                f"admin id={admin.id} has no TOTP secret configured",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover — invariant of the repo
            raise RuntimeError("admin.id is None after get_by_tg_id")
        secret = admin.totp_secret

        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.VERIFY_ADMIN_CONFIRM,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="admin_confirm_token",
            target_id=inp.token,
            tg_chat_id=inp.tg_chat_id,
            occurred_at=self._clock.now(),
            source=inp.source,
            ip=inp.ip,
        )

        # `pop` сразу удаляет запись — токен одноразовый.
        entry = await self._store.pop(token=inp.token)
        if entry is None:
            raise ConfirmTokenNotFoundError(
                f"token={inp.token!r} is not awaiting confirmation",
            )

        now = self._clock.now()

        if entry.request.admin_id != admin_id:
            await self._record_failure(
                admin_id=admin_id,
                entry_admin_id=entry.request.admin_id,
                command_kind=entry.request.command_kind,
                target_kind=entry.request.target_kind,
                target_id=entry.request.target_id,
                token=inp.token,
                reason="admin_mismatch",
                tg_chat_id=inp.tg_chat_id,
                source=inp.source,
                ip=inp.ip,
            )
            raise ConfirmAdminMismatchError(
                f"token={inp.token!r} belongs to admin id={entry.request.admin_id}",
            )

        if entry.expires_at < now:
            await self._record_failure(
                admin_id=admin_id,
                entry_admin_id=admin_id,
                command_kind=entry.request.command_kind,
                target_kind=entry.request.target_kind,
                target_id=entry.request.target_id,
                token=inp.token,
                reason="token_expired",
                tg_chat_id=inp.tg_chat_id,
                source=inp.source,
                ip=inp.ip,
            )
            raise ConfirmTokenExpiredError(
                f"token={inp.token!r} expired at {entry.expires_at.isoformat()}",
            )

        if not self._totp.verify(secret=secret, code=inp.code):
            await self._record_failure(
                admin_id=admin_id,
                entry_admin_id=admin_id,
                command_kind=entry.request.command_kind,
                target_kind=entry.request.target_kind,
                target_id=entry.request.target_id,
                token=inp.token,
                reason="code_invalid",
                tg_chat_id=inp.tg_chat_id,
                source=inp.source,
                ip=inp.ip,
            )
            raise ConfirmCodeInvalidError(
                f"invalid totp code for admin id={admin_id}",
            )

        async with self._uow:
            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_CONFIRM_VERIFIED,
                    target_kind=entry.request.target_kind,
                    target_id=entry.request.target_id,
                    before=None,
                    after=None,
                    reason=f"confirm_verified:{entry.request.command_kind}",
                    idempotency_key=inp.token,
                    source=inp.source,
                    tg_chat_id=inp.tg_chat_id,
                    ip=inp.ip,
                    occurred_at=now,
                ),
            )

        return VerifyAdminConfirmOutput(
            command_kind=entry.request.command_kind,
            target_kind=entry.request.target_kind,
            target_id=entry.request.target_id,
            payload=entry.request.payload,
        )

    async def _record_failure(
        self,
        *,
        admin_id: int,
        entry_admin_id: int,
        command_kind: str,
        target_kind: str,
        target_id: str,
        token: str,
        reason: str,
        tg_chat_id: int | None,
        source: AdminAuditSource = AdminAuditSource.BOT,
        ip: str | None = None,
    ) -> None:
        async with self._uow:
            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_CONFIRM_FAILED,
                    target_kind=target_kind,
                    target_id=target_id,
                    before=None,
                    after={
                        "entry_admin_id": entry_admin_id,
                        "failure_reason": reason,
                    },
                    reason=f"confirm_failed:{command_kind}:{reason}",
                    idempotency_key=token,
                    source=source,
                    tg_chat_id=tg_chat_id,
                    ip=ip,
                    occurred_at=self._clock.now(),
                ),
            )


__all__ = [
    "VerifyAdminConfirm",
    "VerifyAdminConfirmInput",
    "VerifyAdminConfirmOutput",
]
