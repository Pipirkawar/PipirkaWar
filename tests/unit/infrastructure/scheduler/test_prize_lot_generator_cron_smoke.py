"""Smoke-тест cron-flow `GeneratePrizeLots` (Спринт 4.1-C / Шаг C.7.c).

Назначение
==========

C.7.a + C.7.b закрывают **отдельные срезы** cron-механики:
  * C.7.a — производственный `InMemoryFeeEstimator` + 8 unit-тестов
    значений констант и contract-conformance.
  * C.7.b — `schedule_prize_lot_generator_cron()` + `_run_prize_lot_generator_cron_job(...)`
    в `APSchedulerDelayedJobScheduler` + 8 unit-тестов
    регистрации/callback-shape/error-swallow (use-case подменён фейком).

Этот smoke-тест (C.7.c) **сшивает все слои разом** — без БД, но с реальным
prod-кодом use-case-а:

* `InMemoryFeeEstimator` (production-класс из `infrastructure/fees/`);
* `GeneratePrizeLots` (production use-case из `application/monetization/`);
* `APSchedulerDelayedJobScheduler` (production-адаптер из
  `infrastructure/scheduler/`);
* фейки `FakePrizePoolRepository` / `FakePrizeLotRepository` /
  `FakeAuditLogger` / `FakeIdempotencyKey` / `FakeClock` /
  `FakeUnitOfWork` — out of `tests/fakes/` (стандартные thin in-memory
  заглушки портов).

Тик cron-а эмулируется через прямой вызов callback-а
`_run_prize_lot_generator_cron_job(currency_value)` — это убирает
зависимость от wall-clock-а и делает тест детерминированным, но при
этом по-прежнему гонит сообщение целиком: `Currency`-resolve →
`period_id`-construction → `IdempotencyKey`-валидация →
`GeneratePrizeLots.execute(...)` через UoW → запись лотов / декремент
пула / audit per lot.

Покрытие
========

1. **Happy-path tick**: пул `usdt_decimal=10_500_000` (= 10.5 USDT,
   достаточно на 1 max-лот по 10.2 USDT с учётом `InMemoryFeeEstimator`
   fee=0.2 USDT) → cron-тик в USDT_DECIMAL → 1 лот создан,
   `pool.usdt_decimal == 300_000` после, 1 запись audit
   `PRIZE_LOT_GENERATED` per lot, UoW commit ровно 1×.

2. **Empty-pool tick** (no-op): пустой пул → cron-тик в STARS → 0 лотов,
   пул не изменился, 0 audit-записей. UoW по контракту C.2 всё равно
   коммитится (идемпотентный no-op путь записывает root-key через
   idempotency-port).

3. **Idempotent re-tick**: 2 cron-тика подряд внутри одного `period_id`
   (одинаковый ключ `prize_lot_generator:cron:<currency>:<YYYY-MM-DDTHH>`) →
   суммарно 1 лот (второй тик попадает в idempotency-кэш через
   `FakeIdempotencyKey`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pipirik_wars.application.monetization import GeneratePrizeLots
from pipirik_wars.domain.monetization import (
    Currency,
    PrizePool,
    StarsPoolBalance,
    TonNanoAmount,
    UsdtDecimalAmount,
)
from pipirik_wars.domain.shared.ports import AuditAction, AuditSource
from pipirik_wars.infrastructure.fees import InMemoryFeeEstimator
from pipirik_wars.infrastructure.scheduler import APSchedulerDelayedJobScheduler
from tests.fakes import (
    FakeAuditLogger,
    FakeClock,
    FakeIdempotencyKey,
    FakePrizeLotRepository,
    FakePrizePoolRepository,
    FakeUnitOfWork,
)

_FIXED_NOW = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)


def _build_pool(*, usdt_decimal: int = 0, ton_nano: int = 0, stars: int = 0) -> PrizePool:
    return PrizePool(
        stars=StarsPoolBalance(stars),
        ton_nano=TonNanoAmount(ton_nano),
        usdt_decimal=UsdtDecimalAmount(usdt_decimal),
    )


def _build_cron_adapter(
    *,
    pool: PrizePool,
) -> tuple[
    APSchedulerDelayedJobScheduler,
    FakePrizePoolRepository,
    FakePrizeLotRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    GeneratePrizeLots,
]:
    """Собрать полный prod-стек cron-flow на фейк-репозиториях.

    Возвращает кортеж `(adapter, pool_repo, lot_repo, audit, uow, use_case)`
    — все hooks нужны для assert-ов.
    """
    pool_repo = FakePrizePoolRepository(state=pool)
    lot_repo = FakePrizeLotRepository()
    audit = FakeAuditLogger()
    idempotency = FakeIdempotencyKey()
    clock = FakeClock(_FIXED_NOW)
    uow = FakeUnitOfWork()
    use_case = GeneratePrizeLots(
        uow=uow,
        prize_pool_repository=pool_repo,
        prize_lot_repository=lot_repo,
        fee_estimator=InMemoryFeeEstimator(),
        audit_logger=audit,
        idempotency=idempotency,
        clock=clock,
    )
    adapter = APSchedulerDelayedJobScheduler(
        scheduler=AsyncIOScheduler(),
        finish_factory=lambda: (_ for _ in ()).throw(
            AssertionError("finish_factory не должен зваться в cron-smoke")
        ),
        prize_lot_generator_factory=lambda: use_case,
    )
    return adapter, pool_repo, lot_repo, audit, uow, use_case


class TestPrizeLotGeneratorCronSmoke:
    """End-to-end cron-flow `GeneratePrizeLots` через `_run_prize_lot_generator_cron_job`."""

    @pytest.mark.asyncio
    async def test_single_tick_usdt_generates_one_max_lot(self) -> None:
        """Пул 10.5 USDT → 1 max-лот (target 10 + fee 0.2 = 10.2 USDT)."""
        adapter, pool_repo, lot_repo, audit, uow, _ = _build_cron_adapter(
            pool=_build_pool(usdt_decimal=10_500_000),
        )
        await adapter._run_prize_lot_generator_cron_job(Currency.USDT_DECIMAL.value)

        # 1 лот создан.
        assert len(lot_repo.add_calls) == 1
        added_lot = lot_repo.add_calls[0]
        # target=10 USDT, fee=0.2 USDT, total=10.2 USDT.
        assert added_lot.amount_native == 10_200_000
        assert added_lot.fee_buffer_native.value == 200_000
        assert added_lot.currency is Currency.USDT_DECIMAL

        # Пул декрементировался ровно на amount.
        assert pool_repo.state.usdt_decimal.value == 10_500_000 - 10_200_000
        assert len(pool_repo.calls) == 1
        assert pool_repo.calls[0].currency is Currency.USDT_DECIMAL
        assert pool_repo.calls[0].amount_native == -10_200_000

        # Audit-запись per lot.
        assert len(audit.entries) == 1
        record = audit.entries[0]
        assert record.action is AuditAction.PRIZE_LOT_GENERATED
        assert record.source is AuditSource.PRIZE_LOT_GENERATED

        # UoW коммитнулся ровно один раз.
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_single_tick_empty_pool_yields_no_lots(self) -> None:
        """Пустой пул → 0 лотов, 0 audit-записей, пул не изменился."""
        adapter, pool_repo, lot_repo, audit, uow, _ = _build_cron_adapter(
            pool=_build_pool(),
        )
        await adapter._run_prize_lot_generator_cron_job(Currency.STARS.value)

        assert lot_repo.add_calls == []
        assert pool_repo.calls == []  # apply_increment ни разу не звался
        assert pool_repo.state == _build_pool()
        assert audit.entries == []
        # Use-case всё равно открывал UoW и коммитил root-idempotency-key.
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_double_tick_same_period_is_idempotent(self) -> None:
        """2 cron-тика в один `period_id` → 1 лот суммарно (idempotency)."""
        adapter, pool_repo, lot_repo, audit, _, _ = _build_cron_adapter(
            pool=_build_pool(usdt_decimal=10_500_000),
        )
        await adapter._run_prize_lot_generator_cron_job(Currency.USDT_DECIMAL.value)
        # Второй тик в течение того же часа — `period_id` тот же, ключ тот же.
        await adapter._run_prize_lot_generator_cron_job(Currency.USDT_DECIMAL.value)

        # Лот создан ровно один (второй вызов словил idempotency).
        assert len(lot_repo.add_calls) == 1
        # Пул не сполз ниже после первого тика.
        assert pool_repo.state.usdt_decimal.value == 10_500_000 - 10_200_000
        # apply_increment вызывался ровно один раз (для первого лота).
        assert len(pool_repo.calls) == 1
        assert len(audit.entries) == 1
