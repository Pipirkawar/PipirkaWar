"""Use-case ``RefundLot`` (Спринт 4.1-E / Шаг E.8, ГДД §12.6.6).

``/refund_lot <lot_id> <reason>`` — super-admin принудительно возвращает
лот в призовой пул. Применяется, например, когда лот завис в
``RESERVED``-статусе из-за бага инфраструктуры (TON-RPC лежит, expire-cron
сломан), или когда нужно «откатить» некорректно сгенерированный
``ACTIVE``-лот (после правки баланса).

Эффекты внутри одной UoW-транзакции:

1. ``IPrizeLotRepository.update_status(lot_id, REFUNDED)`` — атомарный
   переход ``ACTIVE|RESERVED → REFUNDED`` через домен-state-machine.
   ``CLAIMED`` и ``REFUNDED`` отвергаются доменом
   (``PrizeLotStatusTransitionError``); ``REFUNDED``-вход обрабатывается
   use-case-ом как идемпотентный no-op (``was_already_refunded=True``).
2. ``IPrizePoolRepository.apply_increment(currency, +amount_native)`` —
   возвращает gross-сумму лота в пул (та же сумма, что списалась при
   ``GeneratePrizeLots`` — см. C.2). ``fee_buffer_native`` входит в
   ``amount_native`` по инварианту ``PrizeLot``, отдельной операции нет.
3. ``IAuditLogger.record(PRIZE_LOT_REFUNDED)`` — player-side audit-запись
   с ``source=ADMIN_REFUND``, ``target_id="<lot_id>:refund"``, payload
   аналогичен ``ClaimPrize`` refund-flow-у (плюс ``reason="admin"``,
   ``admin_id`` в ``after``).
4. ``IAdminAuditLogger.record(ADMIN_REFUND_LOT)`` — admin-side audit-запись
   с ``before={"status": ..., "amount_native": ..., "currency": ...}`` и
   ``after={"status": "refunded", "pool_after_native": ..., "reason": ...}``.

Идемпотентность:

* Если ``lot.status == REFUNDED`` на входе — use-case считает запрос
  no-op-ом: возвращает ``RefundLotOutput(was_already_refunded=True)``,
  не пишет audit, не дёргает ``apply_increment``. Это позволяет
  повторно вызывать команду без двойного зачисления в пул.
* На любом другом статусе (``ACTIVE`` / ``RESERVED``) — выполняется
  полный refund-flow с audit-записями. ``CLAIMED`` отвергается доменом
  через ``PrizeLotStatusTransitionError`` — это by design: пул уже
  выплатил приз игроку, возврат денег в пул создал бы дисбаланс
  (см. ``ClaimPrize`` для нормального flow-а CLAIMED).

TOTP-confirm живёт в bot-handler-е (E.14). Use-case проверяет только
RBAC через ``AdminCommandKind.REFUND_LOT`` (super-admin only, см.
матрицу ``RoleBasedAdminAuthorizationPolicy``).

Authorization-flow (см. ``application/admin/_authorization.py``):

1. Загрузить ``Admin`` через ``IAdminRepository.get_by_tg_id``.
2. Если ``admin is None`` или ``not is_active`` — ``AuthorizationError``.
3. ``ensure_admin_authorized(..., command_kind=AdminCommandKind.REFUND_LOT)``
   проверяет матрицу RBAC; при отказе пишет ``ADMIN_AUTHORIZATION_DENIED``
   в отдельной короткоживущей транзакции и поднимает
   ``AdminAuthorizationDeniedError``.
4. Только после успешного RBAC открываем ``async with self._uow:`` и
   читаем/мутируем состояние лота.
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
from pipirik_wars.domain.monetization.entities import PrizeLotStatus
from pipirik_wars.domain.monetization.errors import PrizeLotNotFoundError
from pipirik_wars.domain.monetization.ports import (
    IPrizeLotRepository,
    IPrizePoolRepository,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    AuditSource,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)

__all__ = [
    "RefundLot",
    "RefundLotInput",
    "RefundLotOutput",
]


_PRIZE_LOT_TARGET_KIND = "prize_lot"
_ADMIN_REFUND_REASON = "admin"


@dataclass(frozen=True, slots=True)
class RefundLotInput:
    """Вход ``RefundLot.execute``.

    Поля:

    * ``actor_tg_id`` — telegram-id админа, инициировавшего команду.
    * ``lot_id`` — id ``prize_lot``-а в БД (``> 0``).
    * ``reason`` — обязательный человекочитаемый комментарий для
      ``admin_audit_log.reason`` и ``audit_log.after.reason_detail``.
      Непустая строка после ``strip()`` (handler валидирует, но use-case
      дублирует).
    * ``tg_chat_id`` — id чата команды для admin-аудита
      (``source=BOT``). ``None`` для будущего web-канала.
    """

    actor_tg_id: int
    lot_id: int
    reason: str
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class RefundLotOutput:
    """Результат ``RefundLot.execute``.

    * ``lot_id`` — id обработанного лота (эхо входа).
    * ``was_already_refunded`` — ``True`` если запрос был чистым no-op
      (лот уже в ``REFUNDED``). Handler использует флаг, чтобы сообщить
      «лот уже возвращён в пул» без двойного audit-spam.
    * ``pool_after_native`` — баланс пула в этой валюте после refund-а.
      На no-op-ветке — текущий баланс (без изменений).
    """

    lot_id: int
    was_already_refunded: bool
    pool_after_native: int


class RefundLot:
    """Use-case «вернуть лот в пул» (super-admin + TOTP)."""

    __slots__ = (
        "_admin_audit",
        "_admins",
        "_audit",
        "_authz",
        "_clock",
        "_lots",
        "_pool",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        prize_lot_repository: IPrizeLotRepository,
        prize_pool_repository: IPrizePoolRepository,
        audit: IAuditLogger,
        admin_audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._lots = prize_lot_repository
        self._pool = prize_pool_repository
        self._audit = audit
        self._admin_audit = admin_audit
        self._clock = clock
        self._authz = authz

    async def execute(self, inp: RefundLotInput) -> RefundLotOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            raise RuntimeError("admin.id is None after get_by_tg_id")

        if inp.lot_id <= 0:
            raise ValueError(
                f"RefundLot.lot_id must be a positive int, got {inp.lot_id}",
            )
        if not inp.reason or not inp.reason.strip():
            raise ValueError("RefundLot.reason must be a non-empty string")
        reason = inp.reason.strip()
        target_id = str(inp.lot_id)

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.REFUND_LOT,
            policy=self._authz,
            audit=self._admin_audit,
            uow=self._uow,
            target_kind=_PRIZE_LOT_TARGET_KIND,
            target_id=target_id,
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
        )

        async with self._uow:
            lot = await self._lots.get_by_id(lot_id=inp.lot_id)
            if lot is None:
                raise PrizeLotNotFoundError(lot_id=inp.lot_id)

            if lot.status is PrizeLotStatus.REFUNDED:
                # Идемпотентный retry: лот уже возвращён в пул.
                pool = await self._pool.get_current()
                return RefundLotOutput(
                    lot_id=inp.lot_id,
                    was_already_refunded=True,
                    pool_after_native=pool.balance_for(lot.currency),
                )

            prev_status = lot.status
            await self._lots.update_status(
                lot_id=inp.lot_id,
                new_status=PrizeLotStatus.REFUNDED,
            )
            pool_after = await self._pool.apply_increment(
                currency=lot.currency,
                amount_native=lot.amount_native,
            )
            pool_after_native = pool_after.balance_for(lot.currency)

            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PRIZE_LOT_REFUNDED,
                    actor_id=admin_id,
                    target_kind=_PRIZE_LOT_TARGET_KIND,
                    target_id=f"{inp.lot_id}:refund",
                    before=None,
                    after={
                        "lot_id": inp.lot_id,
                        "currency": lot.currency.value,
                        "amount_native": lot.amount_native,
                        "fee_buffer_native": lot.fee_buffer_native.value,
                        "prev_status": prev_status.value,
                        "pool_after_native": pool_after_native,
                        "reason": _ADMIN_REFUND_REASON,
                        "admin_id": admin_id,
                        "reason_detail": reason,
                    },
                    reason=reason,
                    idempotency_key=f"admin_refund_lot:{inp.lot_id}",
                    occurred_at=now,
                    source=AuditSource.ADMIN_REFUND,
                ),
            )

            await self._admin_audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_REFUND_LOT,
                    target_kind=_PRIZE_LOT_TARGET_KIND,
                    target_id=target_id,
                    before={
                        "status": prev_status.value,
                        "currency": lot.currency.value,
                        "amount_native": lot.amount_native,
                        "fee_buffer_native": lot.fee_buffer_native.value,
                    },
                    after={
                        "status": PrizeLotStatus.REFUNDED.value,
                        "currency": lot.currency.value,
                        "amount_native": lot.amount_native,
                        "pool_after_native": pool_after_native,
                    },
                    reason=reason,
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return RefundLotOutput(
            lot_id=inp.lot_id,
            was_already_refunded=False,
            pool_after_native=pool_after_native,
        )
