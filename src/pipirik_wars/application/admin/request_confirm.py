"""Use-case `RequestAdminConfirm` (Спринт 2.5-A.3, ГДД §18.6).

Шаги:

1. Проверить, что `actor_admin_id` соответствует **активному** админу
   с настроенным TOTP (`totp_secret IS NOT NULL`). Иначе —
   `AuthorizationError` / `TotpNotConfiguredError`.
2. Сгенерировать одноразовый токен (`TokenFactory()` — обычно
   `secrets.token_urlsafe(16)`). Токен — это HMAC-стойкий идентификатор;
   его «секретность» защищает от того, чтобы посторонний ввёл TOTP в
   адрес чужого подтверждения.
3. Сохранить запись в `IAdminConfirmStore` с `expires_at = now + ttl`.
4. Записать `ADMIN_CONFIRM_REQUESTED` в `admin_audit_log` — это нужно,
   чтобы в `/audit` было видно, на какую команду админ просил
   подтверждение (даже если он передумал и не ввёл код).

Аудит и save-в-store — в одной транзакции `IUnitOfWork` (если
audit-запись не легла в БД, токен в store-е тоже не появится — будем
последовательны).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from types import MappingProxyType

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminConfirmEntry,
    AdminConfirmRequest,
    IAdminAuditLogger,
    IAdminConfirmStore,
    IAdminRepository,
    TotpNotConfiguredError,
)
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork

#: Заводская функция генерации одноразового токена. По дефолту в
#: production —  `secrets.token_urlsafe(16)`. Тестовый layer передаёт
#: детерминированный generator, чтобы не угадывать значение.
TokenFactory = Callable[[], str]

#: TTL ожидания подтверждения. ГДД §18.6.4: «admin вводит TOTP не позже
#: чем через минуту, иначе токен сгорает».
DEFAULT_CONFIRM_TTL = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class RequestAdminConfirmInput:
    """Параметры запроса на TOTP-подтверждение."""

    actor_tg_id: int
    command_kind: str
    target_kind: str
    target_id: str
    payload: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class RequestAdminConfirmOutput:
    """Что вернуть handler-у, чтобы он показал админу инструкцию."""

    token: str
    ttl_seconds: int


class RequestAdminConfirm:
    """Запрос на TOTP-подтверждение опасной admin-команды."""

    __slots__ = (
        "_admins",
        "_audit",
        "_clock",
        "_store",
        "_token_factory",
        "_ttl",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        store: IAdminConfirmStore,
        audit: IAdminAuditLogger,
        clock: IClock,
        token_factory: TokenFactory,
        ttl: timedelta = DEFAULT_CONFIRM_TTL,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._store = store
        self._audit = audit
        self._clock = clock
        self._token_factory = token_factory
        self._ttl = ttl

    async def execute(self, inp: RequestAdminConfirmInput) -> RequestAdminConfirmOutput:
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
        # `admin.id` гарантированно не None: get_by_tg_id возвращает
        # запись из БД с заполненным id.
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover — invariant of the repo
            raise RuntimeError("admin.id is None after get_by_tg_id")

        token = self._token_factory()
        now = self._clock.now()
        entry = AdminConfirmEntry(
            request=AdminConfirmRequest(
                admin_id=admin_id,
                command_kind=inp.command_kind,
                target_kind=inp.target_kind,
                target_id=inp.target_id,
                payload=inp.payload,
            ),
            expires_at=now + self._ttl,
        )

        async with self._uow:
            await self._store.save(token=token, entry=entry)
            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_CONFIRM_REQUESTED,
                    target_kind=inp.target_kind,
                    target_id=inp.target_id,
                    before=None,
                    after=None,
                    reason=f"confirm_requested:{inp.command_kind}",
                    idempotency_key=token,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return RequestAdminConfirmOutput(
            token=token,
            ttl_seconds=int(self._ttl.total_seconds()),
        )


__all__ = [
    "DEFAULT_CONFIRM_TTL",
    "RequestAdminConfirm",
    "RequestAdminConfirmInput",
    "RequestAdminConfirmOutput",
    "TokenFactory",
]
