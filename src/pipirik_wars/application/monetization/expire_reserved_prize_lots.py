"""Use-case ``ExpireReservedPrizeLots`` (Спринт 4.1-D / Шаг D.9.c, ГДД §12.6.4).

Refund-таймаут для зарезервированных крипто-лотов. Если игрок не выполнил
``ClaimPrize`` в течение ``balance.prize_lot.reserved_ttl_seconds`` секунд
после резервирования (`PrizeLot.reserve(reserved_at=now)`), лот
автоматически возвращается в пул:

1. ``IPrizeLotRepository.list_expired_reserved(currency, expired_before=now-ttl)``
   возвращает пачку RESERVED-лотов с просроченным TTL (ORDER BY ``reserved_at ASC,
   id ASC``).
2. Для каждого лота:
   * ``update_status(lot.id, new_status=REFUNDED)`` — терминальный
     переход (см. машину состояний ``PrizeLotStatus``).
   * ``apply_increment(currency, +lot.amount_native)`` — возврат полной
     суммы лота (``amount_native``, не ``net_amount_native``) в пул.
     ``fee_buffer`` не списывался (payout не пытался), поэтому пул
     получает gross-сумму.
   * audit ``PRIZE_LOT_REFUNDED`` (``source=PRIZE_LOT_REFUNDED``,
     ``reason="timeout"`` в ``after``-payload-е).

Особенности:

* **Источник аудит-записи** — существующий ``AuditSource.PRIZE_LOT_REFUNDED``
  (whitelist расширен Alembic-миграцией ``0031_audit_source_prize_lot_refunded``,
  шаг C.4). Этот источник целевым образом покрывает все варианты refund-а:
  ``timeout`` (этот use-case), ``player_decline`` (4.1-E
  ``/refund_lot``), ``admin`` (4.1-E ``/refund_lot``), ``fee_overflow``
  (``ClaimPrize``-handler 4.1-D). Различение по ``after["reason"]``.
  Новой миграции для D.9.c **не нужно** — handoff с пометкой
  «требует Alembic 0037» был основан на устаревшем плане.

* **Идемпотентность.** Каждый лот может быть рефанднут только один раз
  (``RESERVED → REFUNDED`` — terminal-переход; повторный
  ``update_status(REFUNDED)`` бросит ``PrizeLotStatusTransitionError``).
  Поэтому use-case полагается на natural-идемпотентность state-machine-а:
  если cron сработает дважды в одну и ту же минуту, второй вызов вернёт
  пустой список (``list_expired_reserved`` фильтрует ``status=RESERVED``).

* **Транзакционность.** Один UoW на весь cron-вызов (по всем валютам).
  Все ``update_status`` / ``apply_increment`` / audit пишутся в одну
  транзакцию — atomicity всего refund-batch-а. На больших объёмах
  (1000+ просроченных лотов в час) UoW может стать длинной; этот сценарий
  не ожидается в MVP (cron-частота ``1×/час``, реалистичный поток —
  десятки лотов в час). Если когда-нибудь упрётся в lock-время —
  decomposeable на per-currency UoW.

* **Pagination.** Если ``list_expired_reserved`` возвращает полную пачку
  (``len == limit``), use-case делает следующий вызов. ``status``
  обновлён в открытой UoW-сессии → следующий запрос увидит уже
  ``REFUNDED``-статус → не вернёт refunded-лоты дважды. Loop завершается
  на не-полной пачке.

Контракт:
* Вход — нет (cron-job, без параметров).
* Выход — ``ExpireReservedPrizeLotsResult(refunded_per_currency,
  total_refunded, cutoff)``.

Каноническая точка вызова — APScheduler hourly cron (D.9.d):
``_run_expire_reserved_prize_lots_cron_job`` в
``infrastructure/scheduler/aps.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType

from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.monetization.entities import PrizeLotStatus
from pipirik_wars.domain.monetization.ports import (
    IPrizeLotRepository,
    IPrizePoolRepository,
)
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    AuditSource,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)

__all__ = [
    "ExpireReservedPrizeLots",
    "ExpireReservedPrizeLotsResult",
]

# Максимальный размер пачки за один SELECT в `list_expired_reserved`.
# Совпадает с дефолтом порта (`limit=100`); use-case делает несколько
# проходов через pagination-loop, пока возвращаются полные пачки.
_BATCH_SIZE: int = 100

# Маркер причины refund-а в audit-payload-е. Отличает timeout-refund от
# `fee_overflow` (`ClaimPrize`-handler), `admin` / `player_decline`
# (4.1-E). Стабильный machine-readable id — для будущих фильтров /
# дашбордов; не отображается игроку.
_REASON_TIMEOUT: str = "timeout"

# Human-readable reason для `AuditEntry.reason`-поля (отображается в
# admin-просмотре audit-log-а — `/audit_lot <lot_id>`).
_REASON_HUMAN: str = "reserved_ttl expired without ClaimPrize"


@dataclass(frozen=True, slots=True)
class ExpireReservedPrizeLotsResult:
    """Результат одного cron-прохода ``ExpireReservedPrizeLots``.

    Поля:

    * ``refunded_per_currency`` — read-only map ``Currency → int``,
      сколько лотов рефанднуто per валюта. Валюты без рефандов
      **отсутствуют** в map-е (НЕ зануляются ``0`` — это short-hand,
      позволяющий cron-логу не печатать «STARS: 0, TON: 0, ...» в
      типовом «нечего рефандить» проходе).
    * ``total_refunded`` — суммарное число рефанднутых лотов по всем
      валютам (``sum(refunded_per_currency.values())``).
    * ``cutoff_iso`` — ISO-8601 UTC момент, относительно которого считалась
      просрочка (``clock.now() - timedelta(seconds=reserved_ttl_seconds)``).
      Хранится как строка, чтобы dataclass оставался hashable для тестов.
    """

    refunded_per_currency: Mapping[Currency, int]
    total_refunded: int
    cutoff_iso: str


class ExpireReservedPrizeLots:
    """Refund RESERVED-лотов, у которых истёк TTL (ГДД §12.6.4)."""

    __slots__ = (
        "_audit",
        "_balance",
        "_clock",
        "_lot_repo",
        "_pool_repo",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        prize_lot_repository: IPrizeLotRepository,
        prize_pool_repository: IPrizePoolRepository,
        audit_logger: IAuditLogger,
        balance_config: IBalanceConfig,
        clock: IClock,
    ) -> None:
        """DI-конструктор (keyword-only).

        Args:
            uow: ``IUnitOfWork`` — атомарность всех refund-операций.
            prize_lot_repository: ``IPrizeLotRepository`` — выборка
                просроченных лотов + status-transition.
            prize_pool_repository: ``IPrizePoolRepository`` — возврат
                сумм в пул через ``apply_increment(+amount)``.
            audit_logger: ``IAuditLogger`` — audit-запись per лот.
            balance_config: ``IBalanceConfig`` — источник
                ``prize_lot.reserved_ttl_seconds`` (D.9.a). Читается
                один раз в начале ``execute()`` для стабильного
                snapshot-а на весь прогон.
            clock: ``IClock`` — UTC-now для расчёта ``expired_before``
                и для ``occurred_at``-аудит-записи.
        """
        self._uow = uow
        self._lot_repo = prize_lot_repository
        self._pool_repo = prize_pool_repository
        self._audit = audit_logger
        self._balance = balance_config
        self._clock = clock

    async def execute(self) -> ExpireReservedPrizeLotsResult:
        """Прогнать refund-batch по всем валютам.

        Алгоритм:
        1. Открыть UoW (top-level cron-вызов, ambient-UoW не ожидается).
        2. Прочитать ``reserved_ttl_seconds`` из ``balance.get()`` —
           snapshot для всего прогона; hot-reload в середине batch-а
           не учитывается.
        3. Посчитать ``cutoff = now - timedelta(seconds=ttl)``.
        4. Для каждой ``Currency`` (детерминированный порядок enum) —
           pagination-loop через ``list_expired_reserved(currency,
           expired_before=cutoff, limit=100)``. Для каждого лота:
           refund + pool increment + audit.
        5. Закрыть UoW (commit) — все refund-ы атомарны.
        """
        async with self._uow:
            return await self._run()

    async def _run(self) -> ExpireReservedPrizeLotsResult:
        """Тело use-case-а, выполняемое внутри уже открытой UoW."""
        snapshot = self._balance.get()
        ttl_seconds = snapshot.prize_lot.reserved_ttl_seconds
        now = self._clock.now()
        cutoff = now - timedelta(seconds=ttl_seconds)

        refunded: dict[Currency, int] = {}
        total = 0

        for currency in Currency:
            currency_count = await self._refund_currency(
                currency=currency,
                cutoff_now=now,
                expired_before=cutoff,
            )
            if currency_count > 0:
                refunded[currency] = currency_count
                total += currency_count

        return ExpireReservedPrizeLotsResult(
            refunded_per_currency=MappingProxyType(refunded),
            total_refunded=total,
            cutoff_iso=cutoff.isoformat(),
        )

    async def _refund_currency(
        self,
        *,
        currency: Currency,
        cutoff_now: datetime,
        expired_before: datetime,
    ) -> int:
        """Рефанднуть все просроченные RESERVED-лоты одной валюты.

        Pagination-loop: запрашиваем пачки по ``_BATCH_SIZE`` пока
        возвращается полная пачка. Status-update внутри открытой UoW —
        следующий запрос увидит обновлённое состояние (autoflush) и не
        вернёт refunded-лоты повторно.
        """
        count = 0
        while True:
            batch = await self._lot_repo.list_expired_reserved(
                currency=currency,
                expired_before=expired_before,
                limit=_BATCH_SIZE,
            )
            if not batch:
                return count
            for lot in batch:
                assert lot.id is not None  # list_expired_reserved → persisted
                await self._lot_repo.update_status(
                    lot_id=lot.id,
                    new_status=PrizeLotStatus.REFUNDED,
                )
                pool_after = await self._pool_repo.apply_increment(
                    currency=currency,
                    amount_native=lot.amount_native,
                )
                await self._audit.record(
                    AuditEntry(
                        action=AuditAction.PRIZE_LOT_REFUNDED,
                        actor_id=None,
                        target_kind="prize_lot",
                        target_id=f"{lot.id}:refund",
                        before=None,
                        after={
                            "lot_id": lot.id,
                            "currency": currency.value,
                            "amount_native": lot.amount_native,
                            "prev_status": "reserved",
                            "pool_after_native": pool_after.balance_for(currency),
                            "reason": _REASON_TIMEOUT,
                        },
                        reason=_REASON_HUMAN,
                        idempotency_key=f"expire_reserved_lot:{lot.id}",
                        occurred_at=cutoff_now,
                        source=AuditSource.PRIZE_LOT_REFUNDED,
                    )
                )
                count += 1
            if len(batch) < _BATCH_SIZE:
                return count
