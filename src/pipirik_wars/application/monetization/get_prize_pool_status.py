"""Use-case ``GetPrizePoolStatus`` (Спринт 4.1-E / Шаг E.9, ГДД §12.6.6).

``/prize_pool`` — super-admin читает консолидированный снимок состояния
крипто-пула: per-currency balance, счётчики лотов по статусам
(``ACTIVE`` / ``RESERVED`` / ``CLAIMED`` / ``REFUNDED``), текущее
freeze-state. Используется для оперативного контроля экономики
(проверка инвариантов «сумма CLAIMED + сумма RESERVED + balance =
исходный пул»; диагностика стуков RESERVED-лотов; решение «нужно ли
``/freeze_payouts``»).

Read-only по экономике (никакие балансы не меняются), но **пишет
admin-аудит** ``ADMIN_PRIZE_POOL_VIEWED``: факт чтения чувствительных
финансовых данных фиксируется в audit-trail-е (compliance, ГДД §18.4).

RBAC через ``AdminCommandKind.GET_PRIZE_POOL`` — super-admin only по
матрице ``RoleBasedAdminAuthorizationPolicy`` (расширена в E.7). При
отказе пишется ``ADMIN_AUTHORIZATION_DENIED`` через
``ensure_admin_authorized(...)``.

Эффекты внутри одной UoW-транзакции:

1. ``IPrizePoolRepository.get_current()`` — snapshot пула.
2. ``IPrizeLotRepository.count_by_status(currency, status)`` × 3 валюты
   × 4 статуса = 12 быстрых COUNT-запросов (покрыты индексом
   ``ix_prize_lots__currency_status``, миграция ``0030_prize_lots``).
3. ``IPayoutFreezeRepository.get_state()`` — текущее состояние
   глобальной заморозки (singleton-строка).
4. ``IAdminAuditLogger.record(ADMIN_PRIZE_POOL_VIEWED)`` — admin-audit
   с ``target_kind="prize_pool"``, ``target_id="all"``, ``before=None``,
   ``after={...}`` с суммарной выжимкой отчёта (для упрощённого
   быстрого просмотра в admin-audit-grid-е без re-execute use-case-а).

Идемпотентность: каждый вызов пишет отдельную audit-запись
(``ADMIN_PRIZE_POOL_VIEWED`` нужен именно для трекинга КАЖДОГО
просмотра — это не data-mutation). Если admin вызовет ``/prize_pool``
дважды подряд — будет 2 audit-записи. Это by design.
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
from pipirik_wars.domain.monetization.entities import (
    PayoutFreeze,
    PrizeLotStatus,
)
from pipirik_wars.domain.monetization.ports import (
    IPayoutFreezeRepository,
    IPrizeLotRepository,
    IPrizePoolRepository,
)
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork

__all__ = [
    "CurrencyPoolStatus",
    "GetPrizePoolStatus",
    "GetPrizePoolStatusInput",
    "GetPrizePoolStatusOutput",
]


_TARGET_KIND = "prize_pool"
_TARGET_ID = "all"

# Порядок отображения в /prize_pool отчёте: Stars → TON → USDT
# (соответствует UX-сортировке остальных monetization-команд).
_CURRENCIES_DISPLAY_ORDER: tuple[Currency, ...] = (
    Currency.STARS,
    Currency.TON_NANO,
    Currency.USDT_DECIMAL,
)

_COUNTED_STATUSES: tuple[PrizeLotStatus, ...] = (
    PrizeLotStatus.ACTIVE,
    PrizeLotStatus.RESERVED,
    PrizeLotStatus.CLAIMED,
    PrizeLotStatus.REFUNDED,
)


@dataclass(frozen=True, slots=True)
class GetPrizePoolStatusInput:
    """Вход ``GetPrizePoolStatus.execute``.

    Поля:

    * ``actor_tg_id`` — telegram-id админа, запросившего команду.
    * ``tg_chat_id`` — id чата команды для admin-аудита
      (``source=BOT``). ``None`` для будущего web-канала.
    """

    actor_tg_id: int
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class CurrencyPoolStatus:
    """Снимок состояния пула в одной валюте (часть отчёта).

    * ``currency`` — валюта строки.
    * ``balance_native`` — текущий баланс пула в native-юнитах валюты
      (``stars`` / ``ton_nano`` / ``usdt_decimal``). Берётся из
      ``IPrizePoolRepository.get_current().balance_for(currency)``.
    * ``active_lots`` / ``reserved_lots`` / ``claimed_lots`` /
      ``refunded_lots`` — счётчики ``prize_lots``-строк per-status
      (через ``IPrizeLotRepository.count_by_status``).
    """

    currency: Currency
    balance_native: int
    active_lots: int
    reserved_lots: int
    claimed_lots: int
    refunded_lots: int


@dataclass(frozen=True, slots=True)
class GetPrizePoolStatusOutput:
    """Результат ``GetPrizePoolStatus.execute``.

    * ``per_currency`` — кортеж ``CurrencyPoolStatus`` в порядке
      ``Stars → TON → USDT`` (фиксированный, см. модуль).
    * ``freeze`` — текущее состояние ``payout_freeze``-агрегата.
    """

    per_currency: tuple[CurrencyPoolStatus, ...]
    freeze: PayoutFreeze


class GetPrizePoolStatus:
    """Use-case «снимок крипто-пула» (super-admin read-only + audit)."""

    __slots__ = (
        "_admin_audit",
        "_admins",
        "_authz",
        "_clock",
        "_lots",
        "_payout_freeze",
        "_pool",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        prize_pool_repository: IPrizePoolRepository,
        prize_lot_repository: IPrizeLotRepository,
        payout_freeze_repo: IPayoutFreezeRepository,
        admin_audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._pool = prize_pool_repository
        self._lots = prize_lot_repository
        self._payout_freeze = payout_freeze_repo
        self._admin_audit = admin_audit
        self._clock = clock
        self._authz = authz

    async def execute(
        self,
        inp: GetPrizePoolStatusInput,
    ) -> GetPrizePoolStatusOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            raise RuntimeError("admin.id is None after get_by_tg_id")

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.GET_PRIZE_POOL,
            policy=self._authz,
            audit=self._admin_audit,
            uow=self._uow,
            target_kind=_TARGET_KIND,
            target_id=_TARGET_ID,
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
        )

        async with self._uow:
            pool = await self._pool.get_current()
            freeze = await self._payout_freeze.get_state()

            per_currency_rows: list[CurrencyPoolStatus] = []
            for currency in _CURRENCIES_DISPLAY_ORDER:
                counts: dict[PrizeLotStatus, int] = {}
                for status in _COUNTED_STATUSES:
                    counts[status] = await self._lots.count_by_status(
                        currency=currency,
                        status=status,
                    )
                per_currency_rows.append(
                    CurrencyPoolStatus(
                        currency=currency,
                        balance_native=pool.balance_for(currency),
                        active_lots=counts[PrizeLotStatus.ACTIVE],
                        reserved_lots=counts[PrizeLotStatus.RESERVED],
                        claimed_lots=counts[PrizeLotStatus.CLAIMED],
                        refunded_lots=counts[PrizeLotStatus.REFUNDED],
                    ),
                )

            audit_after: dict[str, object] = {
                "per_currency": [
                    {
                        "currency": row.currency.value,
                        "balance_native": row.balance_native,
                        "active_lots": row.active_lots,
                        "reserved_lots": row.reserved_lots,
                        "claimed_lots": row.claimed_lots,
                        "refunded_lots": row.refunded_lots,
                    }
                    for row in per_currency_rows
                ],
                "is_frozen": freeze.is_frozen,
                "frozen_by_admin_id": freeze.frozen_by_admin_id,
            }

            await self._admin_audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_PRIZE_POOL_VIEWED,
                    target_kind=_TARGET_KIND,
                    target_id=_TARGET_ID,
                    before=None,
                    after=audit_after,
                    reason="view",
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return GetPrizePoolStatusOutput(
            per_currency=tuple(per_currency_rows),
            freeze=freeze,
        )
