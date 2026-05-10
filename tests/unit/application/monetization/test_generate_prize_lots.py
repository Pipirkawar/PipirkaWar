"""Unit-тесты use-case-а `GeneratePrizeLots` (Спринт 4.1-C / Шаг C.2, ГДД §12.6.3).

Покрытие:

* **Нарезка max-режима** (несколько кейсов): пул >= max_usd-эквивалента →
  один или несколько max-лотов, остаток < max остаётся в пуле.
* **Нарезка min-режима**: пул < max но >= min_usd → серия min-лотов.
* **Пустой пул**: пул < min_usd → 0 лотов, пул не меняется.
* **Все 3 валюты**: STARS / TON_NANO / USDT_DECIMAL (с разными native-
  единицами) — каждая режется корректно.
* **Идемпотентность**: повторный вызов с тем же `idempotency_key`-ом →
  `idempotent=True`, 0 новых лотов, пул не меняется.
* **Fee буфер**: `IFeeEstimator` возвращает `0` (дефолт) → `fee_buffer=0`;
  возвращает положительное число → `fee_buffer=fee`, `amount = target + fee`.
* **Sanity check fee >= target**: возвращает `>= target` → 0 лотов
  (защита от спайков газа, ГДД §12.6.3).
* **Audit-запись per lot**: `action=PRIZE_LOT_GENERATED`,
  `source=PRIZE_LOT_GENERATED`, payload (lot_id, currency, amount,
  fee_buffer, net, pool_after), `idempotency_key` per lot стабилен.
* **Декремент пула**: каждый лот вызывает `apply_increment(currency, -amount)`.
* **UoW commit**: успешный вызов → UoW commit ровно 1 раз.

Итого ~30+ тестов (часть параметризованных).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.monetization import (
    GeneratePrizeLots,
    GeneratePrizeLotsCommand,
    GeneratePrizeLotsResult,
)
from pipirik_wars.domain.monetization import (
    Currency,
    IdempotencyKey,
    PrizeLot,
    PrizeLotStatus,
    PrizePool,
    StarsPoolBalance,
    TonNanoAmount,
    UsdtDecimalAmount,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditSource,
)
from tests.fakes import (
    FakeAuditLogger,
    FakeClock,
    FakeFeeEstimator,
    FakeIdempotencyKey,
    FakePrizeLotRepository,
    FakePrizePoolRepository,
    FakeUnitOfWork,
)

_KEY = IdempotencyKey("prize_lot_gen:hour:2026-05-10T12")
_FIXED_NOW = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)


def _make_pool(
    *,
    stars: int = 0,
    ton_nano: int = 0,
    usdt_decimal: int = 0,
) -> PrizePool:
    """Соберём `PrizePool` с заданными балансами."""
    return PrizePool(
        stars=StarsPoolBalance(stars),
        ton_nano=TonNanoAmount(ton_nano),
        usdt_decimal=UsdtDecimalAmount(usdt_decimal),
    )


def _make_use_case(
    *,
    pool_repo: FakePrizePoolRepository | None = None,
    lot_repo: FakePrizeLotRepository | None = None,
    fee_estimator: FakeFeeEstimator | None = None,
    audit: FakeAuditLogger | None = None,
    idempotency: FakeIdempotencyKey | None = None,
    clock: FakeClock | None = None,
    uow: FakeUnitOfWork | None = None,
) -> tuple[
    GeneratePrizeLots,
    FakePrizePoolRepository,
    FakePrizeLotRepository,
    FakeFeeEstimator,
    FakeAuditLogger,
    FakeIdempotencyKey,
    FakeClock,
    FakeUnitOfWork,
]:
    """Фабрика use-case-а + всех fake-ов. Возвращает кортеж для assert-ов."""
    pool_repo = pool_repo if pool_repo is not None else FakePrizePoolRepository()
    lot_repo = lot_repo if lot_repo is not None else FakePrizeLotRepository()
    fee_estimator = fee_estimator if fee_estimator is not None else FakeFeeEstimator()
    audit = audit if audit is not None else FakeAuditLogger()
    idempotency = idempotency if idempotency is not None else FakeIdempotencyKey()
    clock = clock if clock is not None else FakeClock(_FIXED_NOW)
    uow = uow if uow is not None else FakeUnitOfWork()
    use_case = GeneratePrizeLots(
        uow=uow,
        prize_pool_repository=pool_repo,
        prize_lot_repository=lot_repo,
        fee_estimator=fee_estimator,
        audit_logger=audit,
        idempotency=idempotency,
        clock=clock,
    )
    return use_case, pool_repo, lot_repo, fee_estimator, audit, idempotency, clock, uow


# --------------------------------------------------------------------------- #
# Max-режим (пул >= max_usd_native)
# --------------------------------------------------------------------------- #


class TestMaxMode:
    """Когда пул >= 10 USD-эквивалента: режется max-лотами по 10 USD-эквивалента."""

    @pytest.mark.asyncio
    async def test_pool_15_usdt_yields_one_max_lot_with_5_residue(self) -> None:
        """Пример из ГДД §12.6.3: пул 15 USDT → 1 лот × 10 USDT, 5 USDT остаются."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=15_000_000))
        use_case, _, lot_repo, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert isinstance(result, GeneratePrizeLotsResult)
        assert result.lots_generated_count == 1
        assert len(result.generated_lots) == 1
        assert result.generated_lots[0].amount_native == 10_000_000
        assert result.generated_lots[0].fee_buffer_native.value == 0
        assert result.generated_lots[0].status is PrizeLotStatus.ACTIVE
        assert result.pool_after.usdt_decimal.value == 5_000_000
        assert result.idempotent is False
        # Лот сохранён в репозитории с id=1
        stored = await lot_repo.get_by_id(lot_id=1)
        assert stored is not None
        assert stored.amount_native == 10_000_000

    @pytest.mark.asyncio
    async def test_pool_25_usdt_yields_two_max_lots_with_5_residue(self) -> None:
        """Пул 25 USDT → 2 лота × 10 USDT, 5 USDT остаются."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=25_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 2
        assert all(lot.amount_native == 10_000_000 for lot in result.generated_lots)
        assert result.pool_after.usdt_decimal.value == 5_000_000

    @pytest.mark.asyncio
    async def test_pool_exactly_10_usdt_yields_one_max_lot_no_residue(self) -> None:
        """Граничный кейс: пул == max_usd → 1 max-лот, остаток 0."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=10_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 1
        assert result.generated_lots[0].amount_native == 10_000_000
        assert result.pool_after.usdt_decimal.value == 0


# --------------------------------------------------------------------------- #
# Min-режим (min_usd <= пул < max_usd)
# --------------------------------------------------------------------------- #


class TestMinMode:
    """Когда min_usd <= пул < max_usd: серия min-лотов по 1 USD-эквиваленту."""

    @pytest.mark.asyncio
    async def test_pool_3_usdt_yields_three_min_lots(self) -> None:
        """Пример из ГДД §12.6.3: пул 3 USDT → 3 лота × 1 USDT."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 3
        assert all(lot.amount_native == 1_000_000 for lot in result.generated_lots)
        assert result.pool_after.usdt_decimal.value == 0

    @pytest.mark.asyncio
    async def test_pool_exactly_1_usdt_yields_one_min_lot(self) -> None:
        """Граничный кейс: пул == min_usd → 1 min-лот, остаток 0."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=1_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 1
        assert result.generated_lots[0].amount_native == 1_000_000
        assert result.pool_after.usdt_decimal.value == 0


# --------------------------------------------------------------------------- #
# Below-min пул
# --------------------------------------------------------------------------- #


class TestBelowMin:
    """Когда пул < min_usd: 0 лотов, пул не меняется."""

    @pytest.mark.asyncio
    async def test_empty_pool_yields_zero_lots(self) -> None:
        pool_repo = FakePrizePoolRepository()  # PrizePool.empty()
        use_case, _, lot_repo, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 0
        assert result.generated_lots == ()
        assert result.idempotent is False
        assert result.pool_after.usdt_decimal.value == 0
        # repo не получал add()-вызовов
        assert lot_repo.add_calls == []

    @pytest.mark.asyncio
    async def test_pool_below_min_yields_zero_lots(self) -> None:
        """0.5 USDT (< 1 USDT min) → 0 лотов, пул остаётся 500_000."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=500_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 0
        assert result.pool_after.usdt_decimal.value == 500_000


# --------------------------------------------------------------------------- #
# Все 3 валюты
# --------------------------------------------------------------------------- #


class TestAllCurrencies:
    """Все 3 валюты режутся корректно."""

    @pytest.mark.asyncio
    async def test_stars_100_yields_one_min_lot(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(stars=100))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.STARS, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 1
        assert result.generated_lots[0].currency is Currency.STARS
        assert result.generated_lots[0].amount_native == 100
        assert result.pool_after.stars.value == 0

    @pytest.mark.asyncio
    async def test_stars_1000_yields_one_max_lot(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(stars=1000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.STARS, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 1
        assert result.generated_lots[0].amount_native == 1000

    @pytest.mark.asyncio
    async def test_ton_nano_500m_yields_one_min_lot(self) -> None:
        """0.5 TON (== 500_000_000 nano) → 1 min-лот."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(ton_nano=500_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.TON_NANO, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 1
        assert result.generated_lots[0].currency is Currency.TON_NANO
        assert result.generated_lots[0].amount_native == 500_000_000

    @pytest.mark.asyncio
    async def test_ton_nano_5b_yields_one_max_lot(self) -> None:
        """5 TON → 1 max-лот."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(ton_nano=5_000_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.TON_NANO, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 1
        assert result.generated_lots[0].amount_native == 5_000_000_000

    @pytest.mark.asyncio
    async def test_currency_isolation_other_currencies_unchanged(self) -> None:
        """Генерация в STARS не трогает баланс TON_NANO / USDT_DECIMAL."""
        pool_repo = FakePrizePoolRepository(
            state=_make_pool(stars=1000, ton_nano=12345, usdt_decimal=67890),
        )
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.STARS, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 1
        assert result.pool_after.stars.value == 0
        assert result.pool_after.ton_nano.value == 12345
        assert result.pool_after.usdt_decimal.value == 67890


# --------------------------------------------------------------------------- #
# Идемпотентность
# --------------------------------------------------------------------------- #


class TestIdempotency:
    """Повторный вызов с тем же `idempotency_key`-ом → no-op (`idempotent=True`)."""

    @pytest.mark.asyncio
    async def test_first_call_marks_seen(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        use_case, _, _, _, _, idempotency, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        # После первого вызова root_key помечен seen-ом
        assert await idempotency.is_seen(
            f"prize_lot_generator:{Currency.USDT_DECIMAL.value}|{_KEY.value}"
        )

    @pytest.mark.asyncio
    async def test_second_call_returns_idempotent_true(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        first = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )
        second = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert first.idempotent is False
        assert first.lots_generated_count == 3
        assert second.idempotent is True
        assert second.lots_generated_count == 0
        assert second.generated_lots == ()

    @pytest.mark.asyncio
    async def test_second_call_does_not_decrement_pool(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )
        # пул сейчас == 0
        # «Зальём» обратно вручную (симулируем, что donate пришёл)
        await pool_repo.apply_increment(currency=Currency.USDT_DECIMAL, amount_native=5_000_000)
        # второй вызов с тем же ключом — пул должен остаться 5_000_000
        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert result.idempotent is True
        assert result.pool_after.usdt_decimal.value == 5_000_000

    @pytest.mark.asyncio
    async def test_second_call_does_not_call_repo_add(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        use_case, _, lot_repo, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )
        n_calls_after_first = len(lot_repo.add_calls)
        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert len(lot_repo.add_calls) == n_calls_after_first

    @pytest.mark.asyncio
    async def test_different_keys_each_generate_lots(self) -> None:
        """Разные `idempotency_key`-и → каждый раз генерируем лоты."""
        # 15M → 1 max-лот (10M), 5M остаток. После доната ещё 6M → 11M → 1 max + 1M.
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=15_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        first = await use_case.execute(
            GeneratePrizeLotsCommand(
                currency=Currency.USDT_DECIMAL,
                idempotency_key=IdempotencyKey("prize_lot_gen:hour:2026-05-10T12"),
            )
        )
        # Симуляция: ещё один донат пришёл (+6M)
        await pool_repo.apply_increment(currency=Currency.USDT_DECIMAL, amount_native=6_000_000)
        second = await use_case.execute(
            GeneratePrizeLotsCommand(
                currency=Currency.USDT_DECIMAL,
                idempotency_key=IdempotencyKey("prize_lot_gen:hour:2026-05-10T13"),
            )
        )

        assert first.idempotent is False
        assert first.lots_generated_count == 1  # 15M → 1 max-лот (10M), 5M остаток
        assert second.idempotent is False
        # 5M + 6M = 11M → 1 max-лот (10M), 1M остаток
        assert second.lots_generated_count == 1
        assert second.pool_after.usdt_decimal.value == 1_000_000

    @pytest.mark.asyncio
    async def test_different_currencies_share_no_idempotency(self) -> None:
        """Один `idempotency_key`, разные валюты — независимые scope-ы."""
        pool_repo = FakePrizePoolRepository(
            state=_make_pool(stars=100, usdt_decimal=1_000_000),
        )
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        stars_result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.STARS, idempotency_key=_KEY)
        )
        usdt_result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        # Оба вызова — первое срабатывание per (currency, key)-scope
        assert stars_result.idempotent is False
        assert stars_result.lots_generated_count == 1
        assert usdt_result.idempotent is False
        assert usdt_result.lots_generated_count == 1


# --------------------------------------------------------------------------- #
# Fee буфер
# --------------------------------------------------------------------------- #


class TestFeeBuffer:
    """`IFeeEstimator` корректно встраивается в размер лота."""

    @pytest.mark.asyncio
    async def test_zero_fee_lot_has_zero_buffer(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=10_000_000))
        estimator = FakeFeeEstimator()  # default: 0
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo, fee_estimator=estimator)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 1
        assert result.generated_lots[0].fee_buffer_native.value == 0
        assert result.generated_lots[0].amount_native == 10_000_000
        assert result.generated_lots[0].net_amount_native == 10_000_000

    @pytest.mark.asyncio
    async def test_positive_fee_lot_amount_is_target_plus_fee(self) -> None:
        """Комиссия 0.05 USDT → амаунт лота = 10 USDT (target) + 0.05 USDT (fee)."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=15_050_000))
        estimator = FakeFeeEstimator(fees={Currency.USDT_DECIMAL: 50_000})
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo, fee_estimator=estimator)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        # 15_050_000 >= 10_000_000 → max mode. lot_amount = 10_000_000 + 50_000.
        assert result.lots_generated_count == 1
        assert result.generated_lots[0].amount_native == 10_050_000
        assert result.generated_lots[0].fee_buffer_native.value == 50_000
        assert result.generated_lots[0].net_amount_native == 10_000_000
        # Остаток в пуле = 15_050_000 - 10_050_000 = 5_000_000
        assert result.pool_after.usdt_decimal.value == 5_000_000

    @pytest.mark.asyncio
    async def test_fee_estimator_called_with_target_amount(self) -> None:
        """Estimator вызывается с правильным `target_amount_native`."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=10_000_000))
        estimator = FakeFeeEstimator()
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo, fee_estimator=estimator)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        # max-mode: target = 10_000_000 (10 USDT)
        assert estimator.calls == [(Currency.USDT_DECIMAL, 10_000_000)]

    @pytest.mark.asyncio
    async def test_min_mode_estimator_called_with_min_target(self) -> None:
        """min-режим вызывает estimator с min_usd (1 USDT) target-ом."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        estimator = FakeFeeEstimator()
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo, fee_estimator=estimator)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert estimator.calls == [(Currency.USDT_DECIMAL, 1_000_000)]


# --------------------------------------------------------------------------- #
# Sanity check fee >= target → 0 лотов
# --------------------------------------------------------------------------- #


class TestFeeSanityCheck:
    """Если оценка комиссии >= target_usd_native — 0 лотов (защита от спайка газа)."""

    @pytest.mark.asyncio
    async def test_fee_equals_target_yields_zero_lots(self) -> None:
        """fee == target → 0 лотов (net <= 0)."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=10_000_000))
        estimator = FakeFeeEstimator(fees={Currency.USDT_DECIMAL: 10_000_000})
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo, fee_estimator=estimator)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 0
        assert result.pool_after.usdt_decimal.value == 10_000_000  # пул не тронут

    @pytest.mark.asyncio
    async def test_fee_greater_than_target_yields_zero_lots(self) -> None:
        """fee > target → 0 лотов."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=10_000_000))
        estimator = FakeFeeEstimator(fees={Currency.USDT_DECIMAL: 999_999_999})
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo, fee_estimator=estimator)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert result.lots_generated_count == 0
        assert result.pool_after.usdt_decimal.value == 10_000_000


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


class TestAudit:
    """Audit-запись per lot с правильной семантикой."""

    @pytest.mark.asyncio
    async def test_audit_record_per_lot(self) -> None:
        """3 лота → 3 audit-записи."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        use_case, _, _, _, audit, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert len(audit.entries) == 3

    @pytest.mark.asyncio
    async def test_audit_action_and_source(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=1_000_000))
        use_case, _, _, _, audit, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        entry = audit.entries[0]
        assert entry.action is AuditAction.PRIZE_LOT_GENERATED
        assert entry.source is AuditSource.PRIZE_LOT_GENERATED

    @pytest.mark.asyncio
    async def test_audit_target_kind_and_id_pattern(self) -> None:
        """target_kind='prize_lot', target_id='<root_key>:lot:<idx>'."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=2_000_000))
        use_case, _, _, _, audit, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert audit.entries[0].target_kind == "prize_lot"
        assert audit.entries[1].target_kind == "prize_lot"
        assert audit.entries[0].target_id.endswith(":lot:0")
        assert audit.entries[1].target_id.endswith(":lot:1")
        # И target_id-ы детерминированы относительно root_key
        root_key_part = f"{Currency.USDT_DECIMAL.value}|{_KEY.value}"
        assert root_key_part in audit.entries[0].target_id

    @pytest.mark.asyncio
    async def test_audit_idempotency_key_is_stable_per_lot(self) -> None:
        """`idempotency_key` audit-записи — `<root_key>:lot:<idx>`."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=2_000_000))
        use_case, _, _, _, audit, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert audit.entries[0].idempotency_key is not None
        assert audit.entries[0].idempotency_key.endswith(":lot:0")
        assert audit.entries[1].idempotency_key is not None
        assert audit.entries[1].idempotency_key.endswith(":lot:1")
        # Уникальны
        assert audit.entries[0].idempotency_key != audit.entries[1].idempotency_key

    @pytest.mark.asyncio
    async def test_audit_actor_id_is_none(self) -> None:
        """Системное событие — `actor_id=None`."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=1_000_000))
        use_case, _, _, _, audit, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert audit.entries[0].actor_id is None

    @pytest.mark.asyncio
    async def test_audit_payload_after(self) -> None:
        """`after` содержит lot_id, currency, amount_native, fee_buffer_native, net, pool_after_native."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=10_000_000))
        estimator = FakeFeeEstimator(fees={Currency.USDT_DECIMAL: 50_000})
        # Пул 10M < (10M + 50K = 10_050_000) → max-mode не зайдёт.
        # Зайдёт min-mode: 10M >= 1M (min) → estimate fee для 1M target,
        # fee=50_000 < 1M (sanity OK). lot_amount = 1_050_000.
        # 10M // 1_050_000 = 9 лотов? Точнее: while 10M >= 1_050_000 → loop.
        # Это нормальный тест, but a lot of lots. Use less.
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=1_050_000))
        use_case, _, _, _, audit, _, _, _ = _make_use_case(
            pool_repo=pool_repo, fee_estimator=estimator
        )

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert len(audit.entries) == 1
        after = audit.entries[0].after
        assert after is not None
        assert after["currency"] == Currency.USDT_DECIMAL.value
        assert after["amount_native"] == 1_050_000
        assert after["fee_buffer_native"] == 50_000
        assert after["net_amount_native"] == 1_000_000
        assert after["pool_after_native"] == 0
        assert after["lot_id"] == 1  # id assigned by FakePrizeLotRepository

    @pytest.mark.asyncio
    async def test_audit_before_is_none(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=1_000_000))
        use_case, _, _, _, audit, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert audit.entries[0].before is None

    @pytest.mark.asyncio
    async def test_audit_occurred_at_uses_clock(self) -> None:
        """`occurred_at` — из `IClock.now()`."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=1_000_000))
        clock = FakeClock(_FIXED_NOW)
        use_case, _, _, _, audit, _, _, _ = _make_use_case(pool_repo=pool_repo, clock=clock)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert audit.entries[0].occurred_at == _FIXED_NOW

    @pytest.mark.asyncio
    async def test_no_audit_on_zero_lots(self) -> None:
        """Пустой пул → 0 audit-записей."""
        pool_repo = FakePrizePoolRepository()  # empty
        use_case, _, _, _, audit, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_no_audit_on_idempotent_replay(self) -> None:
        """Повторный вызов с тем же ключом → 0 новых audit-записей."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        use_case, _, _, _, audit, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )
        n_after_first = len(audit.entries)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert len(audit.entries) == n_after_first


# --------------------------------------------------------------------------- #
# Декремент пула
# --------------------------------------------------------------------------- #


class TestPoolDecrement:
    """`apply_increment(currency, -amount)` вызывается per lot."""

    @pytest.mark.asyncio
    async def test_pool_decrement_per_lot(self) -> None:
        """3 лота × 1 USDT → 3 декремента -1_000_000 USDT_DECIMAL."""
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert len(pool_repo.calls) == 3
        for call in pool_repo.calls:
            assert call.currency is Currency.USDT_DECIMAL
            assert call.amount_native == -1_000_000

    @pytest.mark.asyncio
    async def test_no_decrement_on_zero_lots(self) -> None:
        pool_repo = FakePrizePoolRepository()  # empty
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert pool_repo.calls == []


# --------------------------------------------------------------------------- #
# UoW
# --------------------------------------------------------------------------- #


class TestUow:
    """Use-case открывает UoW ровно один раз."""

    @pytest.mark.asyncio
    async def test_successful_execute_commits_once(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        use_case, _, _, _, _, _, _, uow = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_empty_pool_still_commits_once(self) -> None:
        pool_repo = FakePrizePoolRepository()
        use_case, _, _, _, _, _, _, uow = _make_use_case(pool_repo=pool_repo)

        await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        assert uow.commits == 1


# --------------------------------------------------------------------------- #
# PrizeLot фабрика
# --------------------------------------------------------------------------- #


class TestPrizeLotConstruction:
    """Создаваемый `PrizeLot` соответствует доменным инвариантам."""

    @pytest.mark.asyncio
    async def test_lots_are_active(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        for lot in result.generated_lots:
            assert lot.status is PrizeLotStatus.ACTIVE
            assert isinstance(lot, PrizeLot)
            assert lot.claimed_at is None
            assert lot.created_at == _FIXED_NOW
            assert lot.id is not None
            assert lot.id >= 1

    @pytest.mark.asyncio
    async def test_lots_have_unique_ids(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=3_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.USDT_DECIMAL, idempotency_key=_KEY)
        )

        ids = [lot.id for lot in result.generated_lots]
        assert len(set(ids)) == len(ids)

    @pytest.mark.asyncio
    async def test_lots_currency_matches_command(self) -> None:
        pool_repo = FakePrizePoolRepository(state=_make_pool(ton_nano=1_500_000_000))
        use_case, _, _, _, _, _, _, _ = _make_use_case(pool_repo=pool_repo)

        result = await use_case.execute(
            GeneratePrizeLotsCommand(currency=Currency.TON_NANO, idempotency_key=_KEY)
        )

        for lot in result.generated_lots:
            assert lot.currency is Currency.TON_NANO
