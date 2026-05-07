"""Use-case `SetupAdminTotp` (Спринт 2.5-D.6, ГДД §18.6.5).

`/admin_setup_totp <bootstrap_password>` — self-service выдача
TOTP-секрета живому super-admin-у. Команда используется один раз при
первом подключении 2FA: после успешного выполнения `admin.totp_secret`
заполнен, и все последующие опасные команды (`/ban`, `/grant_*`,
`/balance_set`, `/announce`) уже могут проходить TOTP-confirm-flow
(`RequestAdminConfirm` / `VerifyAdminConfirm`).

Алгоритм:

1. Резолвим админа по `actor_tg_id` (`IAdminRepository.get_by_tg_id`).
   Если нет — `AuthorizationError` (как и в остальных admin-use-case-ах).
2. Проверяем `is_active` (защита-в-глубину: между revoke-ом и вызовом
   нескольких миллисекунд бывает достаточно).
3. RBAC через `ensure_admin_authorized(...)` для `AdminCommandKind.SETUP_TOTP`.
   Текущая RBAC-матрица допускает только `SUPER_ADMIN`. Запись
   `ADMIN_AUTHORIZATION_DENIED` пишется отдельной транзакцией внутри
   helper-а — попытка эскалации видна в `/audit` независимо от того,
   что произойдёт дальше.
4. Проверяем настроен ли `bootstrap_admin_password` в окружении бота.
   Если `bootstrap_password is None` — `BootstrapPasswordNotConfiguredError`.
   Это fail-closed: self-service-выдача нового TOTP-секрета без
   второго фактора недопустима.
5. Constant-time-сравнение пароля через `hmac.compare_digest`. Если
   не сошёлся — `BootstrapPasswordInvalidError`. Никаких подсказок «был
   пароль настроен или нет» наружу не отдаём — для этого есть отдельный
   класс ошибки, но handler формулирует одинаково: «настройка не
   удалась, обратитесь к оператору».
6. Проверяем `admin.totp_secret is None`. Если уже настроен —
   `TotpAlreadyConfiguredError`. Перезапись запрещена: даже если
   bootstrap-пароль перехвачен, злоумышленник не сможет молча подменить
   чужой секрет (super-admin сначала должен явно сбросить поле в БД).
7. Генерируем свежий BASE32-секрет через `ITotpSecretGenerator`.
8. В одной транзакции: записываем `set_totp_secret(...)` и пишем
   `ADMIN_TOTP_SETUP` в admin-аудит. `before`/`after` — `None`: сам
   секрет в audit-лог не пишется, чтобы из аудита его нельзя было
   извлечь. `target` = `("admin", str(admin.id))` — actor и target
   совпадают по дизайну. `idempotency_key` — `None`: повторный вызов
   уже отбит шагом 6.
9. Возвращаем `SetupAdminTotpOutput(secret=..., provisioning_uri=...)`.
   `provisioning_uri` — RFC 6238 `otpauth://totp/...`-URI для импорта
   в TOTP-приложение (Google Authenticator / Authy / 1Password).

Никакой логики QR-генерации в use-case нет — это transport-concern
(handler покажет URI или пропишет дальше через `qrcode`-lib). Use-case
возвращает только сам URI как plain-string.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from urllib.parse import quote

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminCommandKind,
    BootstrapPasswordInvalidError,
    BootstrapPasswordNotConfiguredError,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminRepository,
    ITotpSecretGenerator,
    TotpAlreadyConfiguredError,
)
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork

#: Имя issuer-а для `otpauth://`-URI. Видно в TOTP-приложении админа
#: (Google Authenticator / Authy) над полем 6-значного кода.
PROVISIONING_ISSUER = "Pipirik Wars"

#: TOTP-параметры для provisioning-URI. Совпадают с дефолтами `pyotp`
#: и RFC 6238: HMAC-SHA1, 6 цифр, период 30 секунд (соответствует
#: `valid_window=1` в `PyOtpTotpVerifier` — ±30 секунд).
PROVISIONING_ALGORITHM = "SHA1"
PROVISIONING_DIGITS = 6
PROVISIONING_PERIOD = 30


def build_provisioning_uri(*, secret: str, account_name: str) -> str:
    """Собрать `otpauth://totp/<issuer>:<account>?secret=...`-URI.

    Чисто-строковая операция, без зависимости от `pyotp` — это позволяет
    application-слою остаться pure-Python и тестироваться без TOTP-стека.
    Формат — RFC 6238 / Key URI Format (de-facto-стандарт Google
    Authenticator):
    `otpauth://totp/<label>?secret=<base32>&issuer=<issuer>&...`.
    Label = `<issuer>:<account_name>` (двойное упоминание issuer-а — это
    UX-договорённость Authenticator-а: в списке аккаунтов будет
    `Pipirik Wars (admin_<id>)`).
    """
    label = quote(f"{PROVISIONING_ISSUER}:{account_name}", safe="")
    issuer = quote(PROVISIONING_ISSUER, safe="")
    return (
        f"otpauth://totp/{label}"
        f"?secret={secret}"
        f"&issuer={issuer}"
        f"&algorithm={PROVISIONING_ALGORITHM}"
        f"&digits={PROVISIONING_DIGITS}"
        f"&period={PROVISIONING_PERIOD}"
    )


@dataclass(frozen=True, slots=True)
class SetupAdminTotpInput:
    """Параметры выдачи TOTP-секрета."""

    actor_tg_id: int
    password: str
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class SetupAdminTotpOutput:
    """Что вернуть handler-у, чтобы он показал админу секрет + URI.

    `secret` — BASE32-строка (RFC 4648). Подставляется в TOTP-приложение
    вручную, если QR-сканер недоступен.
    `provisioning_uri` — `otpauth://totp/...`-URI для QR-кода
    (handler/UI рисует QR из этого URI; в логах на INFO-уровне это
    значение тоже маркируется явным префиксом).
    """

    secret: str
    provisioning_uri: str


class SetupAdminTotp:
    """Self-service выдача TOTP-секрета super-admin-у."""

    __slots__ = (
        "_admins",
        "_audit",
        "_authz",
        "_bootstrap_password",
        "_clock",
        "_secret_generator",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
        secret_generator: ITotpSecretGenerator,
        bootstrap_password: str | None,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._audit = audit
        self._clock = clock
        self._authz = authz
        self._secret_generator = secret_generator
        self._bootstrap_password = bootstrap_password

    async def execute(self, inp: SetupAdminTotpInput) -> SetupAdminTotpOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover — invariant of the repo
            raise RuntimeError("admin.id is None after get_by_tg_id")

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.SETUP_TOTP,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="admin",
            target_id=str(admin_id),
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
        )

        if self._bootstrap_password is None:
            raise BootstrapPasswordNotConfiguredError(
                "BOOTSTRAP_ADMIN_PASSWORD is not configured in bot environment",
            )
        # Constant-time сравнение защищает от тайминг-атак: даже если
        # злоумышленник может подбирать пароль по 1 символу за запрос,
        # время ответа не зависит от длины общего префикса.
        if not hmac.compare_digest(self._bootstrap_password, inp.password):
            raise BootstrapPasswordInvalidError(
                f"bootstrap password mismatch for admin id={admin_id}",
            )

        if admin.totp_secret is not None:
            raise TotpAlreadyConfiguredError(
                f"admin id={admin_id} already has TOTP secret configured",
            )

        secret = self._secret_generator.generate()
        async with self._uow:
            await self._admins.set_totp_secret(admin_id=admin_id, secret=secret)
            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_TOTP_SETUP,
                    target_kind="admin",
                    target_id=str(admin_id),
                    before=None,
                    after=None,
                    reason="self setup via /admin_setup_totp",
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        provisioning_uri = build_provisioning_uri(
            secret=secret,
            account_name=f"admin_{admin_id}",
        )
        return SetupAdminTotpOutput(secret=secret, provisioning_uri=provisioning_uri)


__all__ = [
    "PROVISIONING_ALGORITHM",
    "PROVISIONING_DIGITS",
    "PROVISIONING_ISSUER",
    "PROVISIONING_PERIOD",
    "SetupAdminTotp",
    "SetupAdminTotpInput",
    "SetupAdminTotpOutput",
    "build_provisioning_uri",
]
