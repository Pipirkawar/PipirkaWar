"""Use-case `GeneratePrizeLots` (Спринт 4.1-C, ГДД §12.6.3).

Нарезка свободного остатка `PrizePool` в данной валюте на лоты
фиксированного размера + декремент пула на сумму каждого лота +
audit-запись `PRIZE_LOT_GENERATED` per lot.

Контракт:
* Вход — `GeneratePrizeLotsCommand(currency, idempotency_key)`.
* Выход — `GeneratePrizeLotsResult(generated_lots, pool_after,
  lots_generated_count, idempotent)`.
* Идемпотентно по `idempotency_key` через `IIdempotencyKey`
  (single-flight семантика: повторный вызов с тем же ключом
  не генерирует лоты повторно, возвращает `idempotent=True` +
  пустой `generated_lots=()` + текущий снапшот пула).
* Транзакционно: use-case использует **ambient-UoW**-паттерн
  (см. `domain/shared/ports/uow.py::IUnitOfWork`-docstring). Если
  caller ещё не открыл `async with self._uow:` (типичный случай —
  hourly cron в `C.7.b`), use-case открывает свой собственный
  контекст и сам коммитит. Если caller уже внутри своей транзакции
  (типичный случай — триггер из `RecordDonation.execute(...)` C.7.d,
  вложенный в `SpinPaidRoulette`-UoW), use-case переиспользует
  ambient-UoW (запись лотов, декремент пула, audit и idempotency-`mark`
  попадают в общую транзакцию caller-а; commit/rollback — на caller-е).
  Это сохраняет инвариант «один контекст — одна транзакция»
  (см. `IUnitOfWork.__aenter__`-контракт) и одновременно даёт
  атомарность донат-инкремента пула и нарезки лотов в одном PR-flow.

Алгоритм нарезки (ГДД §12.6.3):

1. Прочитать снапшот пула — `pool = await pool_repo.get_current()`,
   `free = pool.balance_for(currency)`.
2. Если `free >= _MAX_USD_NATIVE[currency]` — режим **max**:
   * Оценить комиссию `fee = await fee_estimator.estimate_fee(
     currency, target_amount_native=_MAX_USD_NATIVE[currency])`.
   * Размер лота `lot_amount = _MAX_USD_NATIVE[currency] + fee`.
   * Пока `free >= lot_amount` — резать лот размера `lot_amount`
     с `fee_buffer = FeeBufferAmount(fee)`, декрементировать пул,
     писать audit. После цикла остаток (`< lot_amount`) **не**
     нарезается дополнительно мин-лотами (он подождёт следующего
     `cron`-вызова, когда пул дорастёт до очередного max-лота).
3. Иначе если `free >= _MIN_USD_NATIVE[currency]` — режим **min**:
   * Оценить комиссию для `_MIN_USD_NATIVE[currency]`-цели.
   * Размер лота `lot_amount = _MIN_USD_NATIVE[currency] + fee`.
   * Пока `free >= lot_amount` — резать мин-лот, декрементировать,
     писать audit.
4. Иначе `free < _MIN_USD_NATIVE[currency]` — 0 лотов, пул не меняется.
5. Sanity check: если `fee >= _MIN_USD_NATIVE[currency]` (комиссия
   ≥ целевого USD-эквивалента — `net <= 0`), генерация **прерывается**
   на текущем target-е (0 лотов в этом режиме). Это защита от
   деградировавшего `IFeeEstimator` (например, спайк газа в TON-сети).

Примеры (см. unit-тесты):

* пул 3 USDT → 3 лота × 1 USDT (мин-режим, fee=0 для USDT in-memory);
* пул 15 USDT → 1 лот × 10 USDT, 5 USDT остаются (max-режим);
* пул 0 → 0 лотов;
* пул 25 USDT → 2 лота × 10 USDT, 5 USDT остаются (max-режим, два лота);
* fee >= min_usd → 0 лотов.

Audit-запись per lot (см. `AuditAction.PRIZE_LOT_GENERATED` /
`AuditSource.PRIZE_LOT_GENERATED` в `domain/shared/ports/audit.py`):

* `action=PRIZE_LOT_GENERATED`, `source=PRIZE_LOT_GENERATED`.
* `actor_id=None` — генерация — системное событие (cron / триггер).
* `target_kind="prize_lot"`, `target_id=f"{root_key}:lot:{idx}"` —
  стабильный 0-based индекс per generate-вызов (детерминирован).
* `after={"lot_id", "currency", "amount_native", "fee_buffer_native",
  "net_amount_native", "pool_after_native"}`. `before=None` (delta +
  after однозначно восстанавливают before).
* `idempotency_key=f"{root_key}:lot:{idx}"` — уникален per audit-row
  внутри одного `GeneratePrizeLots`-вызова.

Конфиг (ГДД §12.6.3):

* `_MIN_USD_NATIVE` / `_MAX_USD_NATIVE` — таргет-сумма лота в native-
  юнитах per currency (без учёта `fee_buffer`). Эквивалент 1 USD / 10 USD
  по статичному курсу 4.1-C. На 4.1-D эти константы переедут в
  `domain/balance/config.py` + `balance.yaml` (с возможностью hot-reload).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from pipirik_wars.domain.monetization.entities import (
    PrizeLot,
    PrizePool,
)
from pipirik_wars.domain.monetization.ports import (
    IFeeEstimator,
    IPrizeLotRepository,
    IPrizePoolRepository,
)
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    FeeBufferAmount,
    IdempotencyKey,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    AuditSource,
    IAuditLogger,
    IClock,
    IIdempotencyKey,
    IUnitOfWork,
)

__all__ = [
    "GeneratePrizeLots",
    "GeneratePrizeLotsCommand",
    "GeneratePrizeLotsResult",
]

_NAMESPACE = "prize_lot_generator"
_REASON_LOT_GENERATED = "prize_lot_generated"

# Таргет-сумма мин-лота в native-юнитах per currency (ГДД §12.6.3).
# Эквивалент 1 USD по статичному курсу 4.1-C:
# - STARS: 100 ⭐ ≈ $1 (TG-курс продажи Stars-пачек ноябрь 2025).
# - TON_NANO: 500_000_000 = 0.5 TON ≈ $1 (TON ноябрь 2025 ≈ $2/TON).
# - USDT_DECIMAL: 1_000_000 = 1 USDT (USDT TON-jetton с 6-digit decimals).
# На 4.1-D эти константы переедут в `balance.yaml` (поддержка hot-reload).
_MIN_USD_NATIVE: Mapping[Currency, int] = MappingProxyType(
    {
        Currency.STARS: 100,
        Currency.TON_NANO: 500_000_000,
        Currency.USDT_DECIMAL: 1_000_000,
    }
)

# Таргет-сумма макс-лота в native-юнитах per currency (ГДД §12.6.3,
# 10× мин-лота). Эквивалент $10 по тому же статичному курсу 4.1-C.
_MAX_USD_NATIVE: Mapping[Currency, int] = MappingProxyType(
    {
        Currency.STARS: 1_000,
        Currency.TON_NANO: 5_000_000_000,
        Currency.USDT_DECIMAL: 10_000_000,
    }
)


@dataclass(frozen=True, slots=True)
class GeneratePrizeLotsCommand:
    """Команда use-case `GeneratePrizeLots`.

    Поля:
    - `currency` — валюта лот-нарезки (`STARS` / `TON_NANO` / `USDT_DECIMAL`).
      Use-case режет **только** баланс пула в этой валюте; остальные
      валюты пула не трогаются. Caller (cron в C.7 / триггер в C.7)
      запускает use-case отдельно per currency.
    - `idempotency_key` — `IdempotencyKey` вызова. На повторе с тем же
      ключом use-case возвращает `idempotent=True` без побочных эффектов
      (single-flight семантика). Реалистичные namespaces: для cron-а —
      `f"prize_lot_generator:cron:{period_id}"`; для триггера после
      доната — `f"prize_lot_generator:donation:{payment.idempotency_key}"`.
    """

    currency: Currency
    idempotency_key: IdempotencyKey


@dataclass(frozen=True, slots=True)
class GeneratePrizeLotsResult:
    """Результат use-case `GeneratePrizeLots`.

    Поля:
    - `generated_lots` — кортеж свежесгенерированных `PrizeLot`-ов в порядке
      создания (с проставленными `id`). Пустой на `idempotent=True` или
      когда `free_balance < min_lot_amount`.
    - `pool_after` — снапшот всего пула (по всем валютам) после декремента
      на сумму всех созданных лотов. На `idempotent=True` — текущий
      снапшот без изменений.
    - `lots_generated_count` — `len(generated_lots)`. Дублирует поле
      для удобства caller-а (например, audit-handler-а в C.7).
    - `idempotent` — `True`, если caller вызвал use-case повторно с уже
      виденным `idempotency_key`-ом (use-case вышел no-op-ом сразу после
      `is_seen`-проверки). `False` иначе (даже если 0 лотов сгенерировано
      — `free_balance` мог быть `< min_lot_amount`).
    """

    generated_lots: Sequence[PrizeLot]
    pool_after: PrizePool
    lots_generated_count: int
    idempotent: bool


class GeneratePrizeLots:
    """Use-case: нарезать свободный остаток пула на крипто-лоты + audit.

    Архитектура (ГДД §0): чистый application-слой. Сам открывает UoW
    (top-level use-case), вызывает domain-порт для пула / лотов /
    fee-оценки / audit / часов / idempotency. Никаких Telegram-вызовов,
    никаких HTTP — это инфраструктура (за `IFeeEstimator` в C.8 /
    `IPrizeLotRepository` в C.3 / `IPrizePoolRepository` в 4.1-B).
    """

    __slots__ = (
        "_audit",
        "_clock",
        "_fee_estimator",
        "_idempotency",
        "_lot_repo",
        "_pool_repo",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        prize_pool_repository: IPrizePoolRepository,
        prize_lot_repository: IPrizeLotRepository,
        fee_estimator: IFeeEstimator,
        audit_logger: IAuditLogger,
        idempotency: IIdempotencyKey,
        clock: IClock,
    ) -> None:
        """DI-конструктор (keyword-only).

        Args:
            uow: `IUnitOfWork` — атомарность всех записей (lot+pool+audit).
            prize_pool_repository: `IPrizePoolRepository` — чтение/декремент пула.
            prize_lot_repository: `IPrizeLotRepository` — добавление лотов.
            fee_estimator: `IFeeEstimator` — оценка комиссии per currency.
            audit_logger: `IAuditLogger` — audit per лот.
            idempotency: `IIdempotencyKey` — single-flight семантика.
            clock: `IClock` — источник `created_at` для лотов и audit-а.
        """
        self._uow = uow
        self._pool_repo = prize_pool_repository
        self._lot_repo = prize_lot_repository
        self._fee_estimator = fee_estimator
        self._audit = audit_logger
        self._idempotency = idempotency
        self._clock = clock

    async def execute(self, command: GeneratePrizeLotsCommand) -> GeneratePrizeLotsResult:
        """Выполнить нарезку. Контракт — в docstring-е модуля."""
        # Ambient-UoW-паттерн (см. `IUnitOfWork`-docstring): если caller
        # уже открыл свою транзакцию (триггер из `RecordDonation`-flow
        # C.7.d), переиспользуем её и не пытаемся открыть вложенную
        # (`SqlAlchemyUnitOfWork.__aenter__` запрещает nested). При
        # самостоятельном вызове (cron в C.7.b) — открываем сами.
        if self._uow.is_active:
            return await self._run(command)
        async with self._uow:
            return await self._run(command)

    async def _run(self, command: GeneratePrizeLotsCommand) -> GeneratePrizeLotsResult:
        """Тело use-case-а, выполняемое внутри уже открытой UoW."""
        root_key = self._idempotency.build(
            _NAMESPACE,
            [command.currency.value, command.idempotency_key.value],
        )
        if await self._idempotency.is_seen(root_key):
            current_pool = await self._pool_repo.get_current()
            return GeneratePrizeLotsResult(
                generated_lots=(),
                pool_after=current_pool,
                lots_generated_count=0,
                idempotent=True,
            )

        pool = await self._pool_repo.get_current()
        free_balance = pool.balance_for(command.currency)
        max_usd_native = _MAX_USD_NATIVE[command.currency]
        min_usd_native = _MIN_USD_NATIVE[command.currency]

        # Выбор режима: max-mode если хватает на хотя бы один max-лот,
        # иначе min-mode если хватает на хотя бы один min-лот.
        target_usd_native: int | None
        if free_balance >= max_usd_native:
            target_usd_native = max_usd_native
        elif free_balance >= min_usd_native:
            target_usd_native = min_usd_native
        else:
            target_usd_native = None

        generated_lots: list[PrizeLot] = []
        now = self._clock.now()

        if target_usd_native is not None:
            fee_native = await self._fee_estimator.estimate_fee(
                currency=command.currency,
                target_amount_native=target_usd_native,
            )
            # Sanity check: комиссия не должна превышать таргет — иначе
            # net_amount <= 0 и лот деградировал. Защита от спайков газа.
            if fee_native < target_usd_native:
                lot_amount = target_usd_native + fee_native
                fee_buffer = FeeBufferAmount(fee_native)
                while free_balance >= lot_amount:
                    lot = PrizeLot.freshly_generated(
                        currency=command.currency,
                        amount_native=lot_amount,
                        fee_buffer_native=fee_buffer,
                        created_at=now,
                    )
                    saved_lot = await self._lot_repo.add(lot=lot)
                    pool = await self._pool_repo.apply_increment(
                        currency=command.currency,
                        amount_native=-lot_amount,
                    )
                    await self._audit.record(
                        AuditEntry(
                            action=AuditAction.PRIZE_LOT_GENERATED,
                            actor_id=None,
                            target_kind="prize_lot",
                            target_id=(f"{root_key}:lot:{len(generated_lots)}"),
                            before=None,
                            after={
                                "lot_id": saved_lot.id,
                                "currency": command.currency.value,
                                "amount_native": saved_lot.amount_native,
                                "fee_buffer_native": (saved_lot.fee_buffer_native.value),
                                "net_amount_native": (saved_lot.net_amount_native),
                                "pool_after_native": pool.balance_for(command.currency),
                            },
                            reason=_REASON_LOT_GENERATED,
                            idempotency_key=(f"{root_key}:lot:{len(generated_lots)}"),
                            occurred_at=now,
                            source=AuditSource.PRIZE_LOT_GENERATED,
                        )
                    )
                    generated_lots.append(saved_lot)
                    free_balance = pool.balance_for(command.currency)

        await self._idempotency.mark(root_key, namespace=_NAMESPACE)

        return GeneratePrizeLotsResult(
            generated_lots=tuple(generated_lots),
            pool_after=pool,
            lots_generated_count=len(generated_lots),
            idempotent=False,
        )
