"""Use-case-ы ``FreezePayouts`` / ``UnfreezePayouts`` (Спринт 4.1-E / Шаг E.7, ГДД §12.6.6).

``/freeze_payouts <reason>`` — super-admin останавливает все криптовалютные
выплаты глобально. После применения ``ClaimPrize`` отвергает попытки
claim-а с ``ClaimPrizePayoutsFrozenError`` (hook в шаге E.10). TOTP-confirm
живёт в bot-handler-е (E.14) — use-case проверяет только RBAC через
``AdminCommandKind.FREEZE_PAYOUTS`` (super-admin only по матрице
``RoleBasedAdminAuthorizationPolicy``).

``/unfreeze_payouts`` — симметричный use-case, снимает заморозку.

Идемпотентность:

* ``FreezePayouts``: если текущее состояние ``is_frozen=True`` И
  ``frozen_by_admin_id == admin_id`` И ``reason == new_reason`` —
  чистый no-op (без обновления БД, без audit). Иначе вызывается
  ``IPayoutFreezeRepository.set_frozen(...)`` (UPSERT по singleton-строке)
  и пишется ``ADMIN_FREEZE_PAYOUTS``-запись в admin-аудит. Это позволяет
  отдельному админу «перезаморозить» с другой причиной (audit-trail
  фиксирует смену причины и/или ответственного админа).
* ``UnfreezePayouts``: если текущее состояние ``is_frozen=False`` —
  no-op (без обновления, без audit). Иначе ``set_unfrozen()`` и
  ``ADMIN_UNFREEZE_PAYOUTS`` в admin-аудит.

Семантика возвращаемого ``was_already_*`` зеркалит ``FreezePlayer`` /
``UnfreezePlayer`` (Спринт 2.5-B.3): handler видит флаг и сообщает
«уже заморожено» / «уже разморожено» без двойного audit-spam.

Authorization-flow (см. ``application/admin/_authorization.py``):

1. Загрузить ``Admin`` через ``IAdminRepository.get_by_tg_id``.
2. Если ``admin is None`` или ``not is_active`` — ``AuthorizationError``.
3. ``ensure_admin_authorized(..., command_kind=AdminCommandKind.FREEZE_PAYOUTS)``
   проверяет матрицу RBAC; при отказе пишет ``ADMIN_AUTHORIZATION_DENIED``
   в отдельной короткоживущей транзакции и поднимает
   ``AdminAuthorizationDeniedError``.
4. Только после успешного RBAC открываем ``async with self._uow:`` и
   читаем/мутируем состояние freeze.

Конкуррентность: ``IPayoutFreezeRepository`` гарантирует атомарный UPSERT
по singleton-строке ``payout_freeze`` (под row-lock в SQL-реализации,
шаг E.11). Если два super-admin-а одновременно дёргают
``/freeze_payouts`` с разными ``reason`` — последний выигрывает,
обе попытки фиксируются в admin-audit.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminRepository,
)
from pipirik_wars.domain.monetization.ports import IPayoutFreezeRepository
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork

__all__ = [
    "FreezePayouts",
    "FreezePayoutsInput",
    "FreezePayoutsOutput",
    "UnfreezePayouts",
    "UnfreezePayoutsInput",
    "UnfreezePayoutsOutput",
]


_PAYOUT_FREEZE_TARGET_KIND = "payout_freeze"
_PAYOUT_FREEZE_TARGET_ID = "all"


@dataclass(frozen=True, slots=True)
class FreezePayoutsInput:
    """Вход ``FreezePayouts.execute``.

    Поля:

    * ``actor_tg_id`` — telegram-id админа, инициировавшего команду.
      Резолвится в ``Admin`` через ``IAdminRepository.get_by_tg_id``.
    * ``reason`` — обязательный человекочитаемый комментарий для
      ``payout_freeze.reason`` / admin-аудита. Непустая строка после
      ``strip()`` (handler валидирует, но use-case дублирует).
    * ``tg_chat_id`` — id чата команды для admin-аудита
      (``source=BOT``). ``None`` для будущего web-канала.
    """

    actor_tg_id: int
    reason: str
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class FreezePayoutsOutput:
    """Результат ``FreezePayouts.execute``.

    * ``is_frozen`` — всегда ``True`` после успешного execute (даже на
      no-op-ветке: текущее состояние и так заморожено).
    * ``was_already_frozen`` — ``True`` если запрос был чистым no-op
      (тот же админ, та же причина). Handler использует флаг чтобы
      сообщить «выплаты уже заморожены (тем же админом и причиной)»
      без двойного audit.
    """

    is_frozen: bool
    was_already_frozen: bool


@dataclass(frozen=True, slots=True)
class UnfreezePayoutsInput:
    """Вход ``UnfreezePayouts.execute``.

    Поля:

    * ``actor_tg_id`` — telegram-id админа.
    * ``reason`` — опциональный комментарий для admin-аудита (handler
      может передать ``None``, тогда use-case использует дефолт-строку).
    * ``tg_chat_id`` — id чата команды.
    """

    actor_tg_id: int
    reason: str | None = None
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class UnfreezePayoutsOutput:
    """Результат ``UnfreezePayouts.execute``.

    * ``is_frozen`` — всегда ``False`` после успешного execute.
    * ``was_already_unfrozen`` — ``True`` если запрос был чистым no-op.
    """

    is_frozen: bool
    was_already_unfrozen: bool


class FreezePayouts:
    """Use-case «заморозить криптовалютные выплаты» (super-admin + TOTP)."""

    __slots__ = ("_admins", "_audit", "_authz", "_clock", "_payout_freeze", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        payout_freeze_repo: IPayoutFreezeRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._payout_freeze = payout_freeze_repo
        self._audit = audit
        self._clock = clock
        self._authz = authz

    async def execute(self, inp: FreezePayoutsInput) -> FreezePayoutsOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            raise RuntimeError("admin.id is None after get_by_tg_id")

        if not inp.reason or not inp.reason.strip():
            raise ValueError("FreezePayouts.reason must be a non-empty string")
        reason = inp.reason.strip()

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.FREEZE_PAYOUTS,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind=_PAYOUT_FREEZE_TARGET_KIND,
            target_id=_PAYOUT_FREEZE_TARGET_ID,
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
        )

        async with self._uow:
            state_before = await self._payout_freeze.get_state()

            if (
                state_before.is_frozen
                and state_before.frozen_by_admin_id == admin_id
                and state_before.reason == reason
            ):
                # Чистый no-op: тот же админ, та же причина. Не пишем в
                # БД, не пишем в audit (idempotent retry).
                return FreezePayoutsOutput(
                    is_frozen=True,
                    was_already_frozen=True,
                )

            state_after = await self._payout_freeze.set_frozen(
                admin_id=admin_id,
                at=now,
                reason=reason,
            )

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_FREEZE_PAYOUTS,
                    target_kind=_PAYOUT_FREEZE_TARGET_KIND,
                    target_id=_PAYOUT_FREEZE_TARGET_ID,
                    before={
                        "is_frozen": state_before.is_frozen,
                        "frozen_by_admin_id": state_before.frozen_by_admin_id,
                        "reason": state_before.reason,
                    },
                    after={
                        "is_frozen": state_after.is_frozen,
                        "frozen_by_admin_id": state_after.frozen_by_admin_id,
                        "reason": state_after.reason,
                    },
                    reason=reason,
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return FreezePayoutsOutput(
            is_frozen=True,
            was_already_frozen=False,
        )


class UnfreezePayouts:
    """Use-case «снять заморозку крипто-выплат» (super-admin + TOTP)."""

    __slots__ = ("_admins", "_audit", "_authz", "_clock", "_payout_freeze", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        payout_freeze_repo: IPayoutFreezeRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._payout_freeze = payout_freeze_repo
        self._audit = audit
        self._clock = clock
        self._authz = authz

    async def execute(self, inp: UnfreezePayoutsInput) -> UnfreezePayoutsOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            raise RuntimeError("admin.id is None after get_by_tg_id")

        reason = (inp.reason or "").strip() or "unfreeze payouts"

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.UNFREEZE_PAYOUTS,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind=_PAYOUT_FREEZE_TARGET_KIND,
            target_id=_PAYOUT_FREEZE_TARGET_ID,
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
        )

        async with self._uow:
            state_before = await self._payout_freeze.get_state()

            if not state_before.is_frozen:
                # Уже разморожено: чистый no-op, audit-spam не пишем.
                return UnfreezePayoutsOutput(
                    is_frozen=False,
                    was_already_unfrozen=True,
                )

            state_after = await self._payout_freeze.set_unfrozen()

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_UNFREEZE_PAYOUTS,
                    target_kind=_PAYOUT_FREEZE_TARGET_KIND,
                    target_id=_PAYOUT_FREEZE_TARGET_ID,
                    before={
                        "is_frozen": state_before.is_frozen,
                        "frozen_by_admin_id": state_before.frozen_by_admin_id,
                        "reason": state_before.reason,
                    },
                    after={
                        "is_frozen": state_after.is_frozen,
                        "frozen_by_admin_id": state_after.frozen_by_admin_id,
                        "reason": state_after.reason,
                    },
                    reason=reason,
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return UnfreezePayoutsOutput(
            is_frozen=False,
            was_already_unfrozen=False,
        )
