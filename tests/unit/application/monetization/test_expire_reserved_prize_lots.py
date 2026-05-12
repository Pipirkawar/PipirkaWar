"""Unit-тесты use-case `ExpireReservedPrizeLots` (Спринт 4.1-D / D.9.c).

Покрытие:

* **Нет лотов** — пустой `list_expired_reserved` → 0 рефандов, нет audit.
* **Один лот в одной валюте** — `RESERVED → REFUNDED`, `apply_increment(+amount)`,
  ровно одна audit-запись.
* **Несколько лотов в одной валюте** — все рефанднуты, audit для каждого.
* **Смешанные валюты** — лоты в STARS / TON_NANO / USDT_DECIMAL рефандятся
  независимо, в порядке итерации `Currency`-enum.
* **TTL граница** — лоты с `reserved_at == cutoff` рефандятся (`<=`-условие
  в порте), `reserved_at > cutoff` остаются.
* **`reserved_ttl_seconds` читается из `balance.get()`** — изменение
  конфига между вызовами `execute()` меняет cutoff.
* **Audit-shape** — точная форма payload-а: `action=PRIZE_LOT_REFUNDED`,
  `source=PRIZE_LOT_REFUNDED`, `target_id=f"{lot.id}:refund"`,
  `after={lot_id, currency, amount_native, prev_status, pool_after_native,
  reason="timeout"}`, `idempotency_key=f"expire_reserved_lot:{lot.id}"`,
  `occurred_at=clock.now()` (НЕ `cutoff`).
* **Pool increment корректен** — `apply_increment(currency, +amount_native)`
  (gross, не `net_amount_native`).
* **UoW commit** — успешный вызов → ровно 1 коммит UoW.
* **Идемпотентность state-machine** — повторный `execute()` после первого
  не рефандит уже-REFUNDED лоты (они вышли из `list_expired_reserved`-выборки).
* **Pagination** — если первая пачка `>= _BATCH_SIZE`, делается следующий
  вызов; завершается на неполной пачке.
* **Детерминированный порядок Currency** — refund идёт в порядке
  `STARS → TON_NANO → USDT_DECIMAL`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.monetization import (
    ExpireReservedPrizeLots,
    ExpireReservedPrizeLotsResult,
)
from pipirik_wars.application.monetization.expire_reserved_prize_lots import (
    _BATCH_SIZE,
)
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.monetization import (
    Currency,
    FeeBufferAmount,
    PrizeLot,
    PrizeLotStatus,
    PrizePool,
    StarsPoolBalance,
    TonNanoAmount,
    UsdtDecimalAmount,
)
from pipirik_wars.domain.shared.ports import AuditAction, AuditSource
from tests.fakes import (
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakePrizeLotRepository,
    FakePrizePoolRepository,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import valid_balance_payload

_FIXED_NOW = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)
_TTL_SECONDS: int = 172_800  # 48h — дефолт из `balance.yaml`.


def _make_balance(ttl_seconds: int = _TTL_SECONDS) -> FakeBalanceConfig:
    """Собрать FakeBalanceConfig с подменённым `prize_lot.reserved_ttl_seconds`."""
    # Pydantic v2 `model_copy(update={...})` не работает для nested-mode
    # через dotted-key; собираем raw payload и пересоздаём.
    raw = valid_balance_payload()
    raw["prize_lot"]["reserved_ttl_seconds"] = ttl_seconds
    snapshot = BalanceConfig.model_validate(raw)
    return FakeBalanceConfig(snapshot)


def _make_use_case(
    *,
    lot_repo: FakePrizeLotRepository | None = None,
    pool_repo: FakePrizePoolRepository | None = None,
    audit: FakeAuditLogger | None = None,
    balance: FakeBalanceConfig | None = None,
    clock: FakeClock | None = None,
    uow: FakeUnitOfWork | None = None,
) -> tuple[
    ExpireReservedPrizeLots,
    FakePrizeLotRepository,
    FakePrizePoolRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeUnitOfWork,
]:
    """Фабрика use-case-а + всех fake-ов."""
    lot_repo = lot_repo if lot_repo is not None else FakePrizeLotRepository()
    pool_repo = pool_repo if pool_repo is not None else FakePrizePoolRepository()
    audit = audit if audit is not None else FakeAuditLogger()
    balance = balance if balance is not None else _make_balance()
    clock = clock if clock is not None else FakeClock(_FIXED_NOW)
    uow = uow if uow is not None else FakeUnitOfWork()
    use_case = ExpireReservedPrizeLots(
        uow=uow,
        prize_lot_repository=lot_repo,
        prize_pool_repository=pool_repo,
        audit_logger=audit,
        balance_config=balance,
        clock=clock,
    )
    return use_case, lot_repo, pool_repo, audit, balance, clock, uow


async def _seed_reserved_lot(
    *,
    repo: FakePrizeLotRepository,
    currency: Currency,
    amount_native: int,
    reserved_at: datetime,
    fee_buffer_native: int = 0,
) -> PrizeLot:
    """Хелпер: создать ACTIVE-лот, тут же зарезервировать его.

    Возвращает persisted `RESERVED`-лот с проставленным `id`.
    """
    fresh = PrizeLot.freshly_generated(
        currency=currency,
        amount_native=amount_native,
        fee_buffer_native=FeeBufferAmount(fee_buffer_native),
        created_at=reserved_at - timedelta(hours=1),
    )
    added = await repo.add(lot=fresh)
    assert added.id is not None
    return await repo.update_status(
        lot_id=added.id,
        new_status=PrizeLotStatus.RESERVED,
        reserved_at=reserved_at,
    )


def _make_pool(
    *,
    stars: int = 0,
    ton_nano: int = 0,
    usdt_decimal: int = 0,
) -> PrizePool:
    return PrizePool(
        stars=StarsPoolBalance(stars),
        ton_nano=TonNanoAmount(ton_nano),
        usdt_decimal=UsdtDecimalAmount(usdt_decimal),
    )


# --------------------------------------------------------------------------- #
# Базовые сценарии (empty / single / multi)
# --------------------------------------------------------------------------- #


class TestEmpty:
    """Когда нет просроченных лотов — refund-batch — no-op."""

    @pytest.mark.asyncio
    async def test_no_reserved_lots_returns_empty(self) -> None:
        """Пустой репозиторий → 0 рефандов, нет audit, UoW коммитится."""
        use_case, lot_repo, pool_repo, audit, _, _, uow = _make_use_case()

        result = await use_case.execute()

        assert isinstance(result, ExpireReservedPrizeLotsResult)
        assert result.total_refunded == 0
        assert dict(result.refunded_per_currency) == {}
        assert audit.entries == []
        assert lot_repo.update_status_calls == []
        assert pool_repo.calls == []
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_only_non_expired_reserved_returns_empty(self) -> None:
        """RESERVED-лот с `reserved_at = now - 1h` (TTL=48h) → не просрочен."""
        lot_repo = FakePrizeLotRepository()
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.USDT_DECIMAL,
            amount_native=1_000_000,
            reserved_at=_FIXED_NOW - timedelta(hours=1),
        )
        use_case, _, pool_repo, audit, _, _, uow = _make_use_case(lot_repo=lot_repo)

        result = await use_case.execute()

        assert result.total_refunded == 0
        assert audit.entries == []
        assert pool_repo.calls == []
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_only_active_lot_is_skipped(self) -> None:
        """ACTIVE-лот (никогда не резервировался) — не попадает в выборку."""
        lot_repo = FakePrizeLotRepository()
        await lot_repo.add(
            lot=PrizeLot.freshly_generated(
                currency=Currency.STARS,
                amount_native=500,
                fee_buffer_native=FeeBufferAmount(0),
                created_at=_FIXED_NOW - timedelta(days=10),
            )
        )
        use_case, _, _, audit, _, _, _ = _make_use_case(lot_repo=lot_repo)

        result = await use_case.execute()

        assert result.total_refunded == 0
        assert audit.entries == []


class TestSingleLot:
    """Один просроченный лот → refund + pool increment + audit."""

    @pytest.mark.asyncio
    async def test_single_usdt_lot_refunded(self) -> None:
        """RESERVED-USDT-лот с `reserved_at = now - 49h` → refunded."""
        lot_repo = FakePrizeLotRepository()
        lot = await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.USDT_DECIMAL,
            amount_native=10_000_000,
            reserved_at=_FIXED_NOW - timedelta(hours=49),
        )
        use_case, _, pool_repo, audit, _, _, uow = _make_use_case(lot_repo=lot_repo)

        result = await use_case.execute()

        # Result
        assert result.total_refunded == 1
        assert dict(result.refunded_per_currency) == {Currency.USDT_DECIMAL: 1}

        # Status → REFUNDED
        stored = await lot_repo.get_by_id(lot_id=lot.id)  # type: ignore[arg-type]
        assert stored is not None
        assert stored.status is PrizeLotStatus.REFUNDED

        # Pool increment — gross `amount_native` (НЕ `net_amount_native`)
        assert len(pool_repo.calls) == 1
        call = pool_repo.calls[0]
        assert call.currency is Currency.USDT_DECIMAL
        assert call.amount_native == 10_000_000

        # Один audit-record
        assert len(audit.entries) == 1

        # UoW commit
        assert uow.commits == 1

    @pytest.mark.asyncio
    async def test_lot_at_cutoff_boundary_is_refunded(self) -> None:
        """Граничный кейс: `reserved_at == now - ttl` → попадает в refund (`<=` cutoff)."""
        lot_repo = FakePrizeLotRepository()
        lot = await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.STARS,
            amount_native=200,
            reserved_at=_FIXED_NOW - timedelta(seconds=_TTL_SECONDS),
        )
        use_case, _, _, _, _, _, _ = _make_use_case(lot_repo=lot_repo)

        result = await use_case.execute()

        assert result.total_refunded == 1
        stored = await lot_repo.get_by_id(lot_id=lot.id)  # type: ignore[arg-type]
        assert stored is not None
        assert stored.status is PrizeLotStatus.REFUNDED

    @pytest.mark.asyncio
    async def test_lot_just_inside_ttl_is_skipped(self) -> None:
        """`reserved_at = cutoff + 1s` → НЕ просрочен (строго `> cutoff`)."""
        lot_repo = FakePrizeLotRepository()
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.STARS,
            amount_native=200,
            reserved_at=_FIXED_NOW - timedelta(seconds=_TTL_SECONDS - 1),
        )
        use_case, _, pool_repo, audit, _, _, _ = _make_use_case(lot_repo=lot_repo)

        result = await use_case.execute()

        assert result.total_refunded == 0
        assert audit.entries == []
        assert pool_repo.calls == []


# --------------------------------------------------------------------------- #
# Multi-currency и порядок
# --------------------------------------------------------------------------- #


class TestMultiCurrency:
    """Refund-batch проходит по всем валютам в порядке `Currency`-enum."""

    @pytest.mark.asyncio
    async def test_mixed_currencies_all_refunded(self) -> None:
        """Лот в каждой валюте → refunded; per-currency count корректен."""
        lot_repo = FakePrizeLotRepository()
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.STARS,
            amount_native=300,
            reserved_at=_FIXED_NOW - timedelta(hours=49),
        )
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.TON_NANO,
            amount_native=500_000_000,
            reserved_at=_FIXED_NOW - timedelta(hours=49),
        )
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.USDT_DECIMAL,
            amount_native=1_000_000,
            reserved_at=_FIXED_NOW - timedelta(hours=49),
        )
        use_case, _, pool_repo, audit, _, _, _ = _make_use_case(lot_repo=lot_repo)

        result = await use_case.execute()

        assert result.total_refunded == 3
        assert dict(result.refunded_per_currency) == {
            Currency.STARS: 1,
            Currency.TON_NANO: 1,
            Currency.USDT_DECIMAL: 1,
        }
        # Один pool-call per лот
        assert len(pool_repo.calls) == 3
        # Audit per лот
        assert len(audit.entries) == 3

    @pytest.mark.asyncio
    async def test_only_one_currency_has_expired(self) -> None:
        """Просрочен один TON-лот, остальные валюты нетронуты."""
        lot_repo = FakePrizeLotRepository()
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.TON_NANO,
            amount_native=500_000_000,
            reserved_at=_FIXED_NOW - timedelta(hours=49),
        )
        # STARS-лот не просрочен
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.STARS,
            amount_native=200,
            reserved_at=_FIXED_NOW - timedelta(hours=1),
        )
        use_case, _, _, audit, _, _, _ = _make_use_case(lot_repo=lot_repo)

        result = await use_case.execute()

        assert result.total_refunded == 1
        assert dict(result.refunded_per_currency) == {Currency.TON_NANO: 1}
        # STARS остался RESERVED
        assert len(audit.entries) == 1

    @pytest.mark.asyncio
    async def test_currency_iteration_order_is_deterministic(self) -> None:
        """Порядок refund-а в audit-log-е = `Currency.STARS → TON_NANO → USDT_DECIMAL`."""
        lot_repo = FakePrizeLotRepository()
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.USDT_DECIMAL,
            amount_native=1_000_000,
            reserved_at=_FIXED_NOW - timedelta(hours=49),
        )
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.STARS,
            amount_native=200,
            reserved_at=_FIXED_NOW - timedelta(hours=49),
        )
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.TON_NANO,
            amount_native=500_000_000,
            reserved_at=_FIXED_NOW - timedelta(hours=49),
        )
        use_case, _, _, audit, _, _, _ = _make_use_case(lot_repo=lot_repo)

        await use_case.execute()

        recorded_currencies = [
            entry.after["currency"]  # type: ignore[index]
            for entry in audit.entries
        ]
        assert recorded_currencies == [
            Currency.STARS.value,
            Currency.TON_NANO.value,
            Currency.USDT_DECIMAL.value,
        ]


# --------------------------------------------------------------------------- #
# Audit shape / payload
# --------------------------------------------------------------------------- #


class TestAuditShape:
    """Точная форма audit-payload-а."""

    @pytest.mark.asyncio
    async def test_audit_entry_fields(self) -> None:
        """Проверяем все ключевые поля `AuditEntry`."""
        lot_repo = FakePrizeLotRepository()
        pool_repo = FakePrizePoolRepository(state=_make_pool(usdt_decimal=4_000_000))
        lot = await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.USDT_DECIMAL,
            amount_native=1_000_000,
            reserved_at=_FIXED_NOW - timedelta(hours=49),
            fee_buffer_native=0,
        )
        use_case, _, _, audit, _, clock, _ = _make_use_case(
            lot_repo=lot_repo,
            pool_repo=pool_repo,
        )

        await use_case.execute()

        assert len(audit.entries) == 1
        entry = audit.entries[0]

        assert entry.action is AuditAction.PRIZE_LOT_REFUNDED
        assert entry.source is AuditSource.PRIZE_LOT_REFUNDED
        assert entry.actor_id is None  # system event
        assert entry.target_kind == "prize_lot"
        assert entry.target_id == f"{lot.id}:refund"
        assert entry.before is None
        assert entry.idempotency_key == f"expire_reserved_lot:{lot.id}"
        assert entry.occurred_at == clock.now()

        # `after`-payload
        assert entry.after is not None
        assert entry.after["lot_id"] == lot.id
        assert entry.after["currency"] == Currency.USDT_DECIMAL.value
        assert entry.after["amount_native"] == 1_000_000
        assert entry.after["prev_status"] == "reserved"
        # Пул увеличился: 4_000_000 + 1_000_000 = 5_000_000
        assert entry.after["pool_after_native"] == 5_000_000
        assert entry.after["reason"] == "timeout"


# --------------------------------------------------------------------------- #
# Pool increment correctness
# --------------------------------------------------------------------------- #


class TestPoolIncrement:
    """Pool инкрементируется на gross `amount_native`, не `net`."""

    @pytest.mark.asyncio
    async def test_pool_increment_is_gross_amount(self) -> None:
        """Лот с `fee_buffer=10` и `amount=110` → pool += 110 (не 100)."""
        lot_repo = FakePrizeLotRepository()
        pool_repo = FakePrizePoolRepository()
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.TON_NANO,
            amount_native=510_000_000,  # 0.5 TON + fee_buffer
            reserved_at=_FIXED_NOW - timedelta(hours=49),
            fee_buffer_native=10_000_000,
        )
        use_case, _, _, _, _, _, _ = _make_use_case(lot_repo=lot_repo, pool_repo=pool_repo)

        await use_case.execute()

        assert len(pool_repo.calls) == 1
        assert pool_repo.calls[0].amount_native == 510_000_000


# --------------------------------------------------------------------------- #
# UoW / Clock / Balance integration
# --------------------------------------------------------------------------- #


class TestUoW:
    """UoW открывается / коммитится корректно."""

    @pytest.mark.asyncio
    async def test_uow_commits_once_on_success(self) -> None:
        """Успешный run → 1 commit, 0 rollback."""
        lot_repo = FakePrizeLotRepository()
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.STARS,
            amount_native=200,
            reserved_at=_FIXED_NOW - timedelta(hours=49),
        )
        use_case, _, _, _, _, _, uow = _make_use_case(lot_repo=lot_repo)

        await use_case.execute()

        assert uow.commits == 1
        assert uow.rollbacks == 0


class TestClockInjection:
    """`expired_before` берётся из `clock.now() - ttl`."""

    @pytest.mark.asyncio
    async def test_advancing_clock_picks_up_more_lots(self) -> None:
        """Лот зарезервирован 47h59m назад → не просрочен. Двинули часы на 1m
        вперёд → теперь просрочен (`reserved_at` = `now - 48h`)."""
        lot_repo = FakePrizeLotRepository()
        # ttl = 48h, лот зарезервирован 48h - 1min назад → ещё валидный
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.STARS,
            amount_native=200,
            reserved_at=_FIXED_NOW - timedelta(seconds=_TTL_SECONDS - 60),
        )
        clock = FakeClock(_FIXED_NOW)
        use_case, _, _, audit, _, _, _ = _make_use_case(
            lot_repo=lot_repo,
            clock=clock,
        )

        result1 = await use_case.execute()
        assert result1.total_refunded == 0

        # Двигаем часы на 1m вперёд — лот теперь просрочен (cutoff сдвинулся)
        clock.advance(minutes=1)
        result2 = await use_case.execute()
        assert result2.total_refunded == 1
        assert len(audit.entries) == 1

    @pytest.mark.asyncio
    async def test_cutoff_iso_in_result(self) -> None:
        """`cutoff_iso` = `(now - ttl).isoformat()`."""
        clock = FakeClock(_FIXED_NOW)
        use_case, _, _, _, _, _, _ = _make_use_case(clock=clock)

        result = await use_case.execute()

        expected_cutoff = _FIXED_NOW - timedelta(seconds=_TTL_SECONDS)
        assert result.cutoff_iso == expected_cutoff.isoformat()


class TestBalanceConfigRead:
    """`reserved_ttl_seconds` берётся из `balance.get()` per вызов."""

    @pytest.mark.asyncio
    async def test_ttl_change_via_hot_reload_picks_up_lots(self) -> None:
        """До hot-reload (TTL=48h) лот не просрочен; после reload (TTL=1h) — просрочен."""
        lot_repo = FakePrizeLotRepository()
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.USDT_DECIMAL,
            amount_native=1_000_000,
            reserved_at=_FIXED_NOW - timedelta(hours=2),
        )
        balance = _make_balance(ttl_seconds=_TTL_SECONDS)
        use_case, _, _, _, _, _, _ = _make_use_case(
            lot_repo=lot_repo,
            balance=balance,
        )

        result1 = await use_case.execute()
        assert result1.total_refunded == 0

        # Hot-reload: сокращаем TTL до 1h
        raw = valid_balance_payload()
        raw["prize_lot"]["reserved_ttl_seconds"] = 3600
        balance.set(BalanceConfig.model_validate(raw))

        result2 = await use_case.execute()
        assert result2.total_refunded == 1


# --------------------------------------------------------------------------- #
# Идемпотентность
# --------------------------------------------------------------------------- #


class TestIdempotency:
    """Повторный вызов не рефандит уже-REFUNDED лоты."""

    @pytest.mark.asyncio
    async def test_second_run_is_noop(self) -> None:
        """Первый run рефандит 1 лот; второй run — 0 (лот уже REFUNDED)."""
        lot_repo = FakePrizeLotRepository()
        await _seed_reserved_lot(
            repo=lot_repo,
            currency=Currency.STARS,
            amount_native=200,
            reserved_at=_FIXED_NOW - timedelta(hours=49),
        )
        use_case, _, pool_repo, audit, _, _, uow = _make_use_case(lot_repo=lot_repo)

        result1 = await use_case.execute()
        assert result1.total_refunded == 1
        assert len(audit.entries) == 1
        assert len(pool_repo.calls) == 1

        result2 = await use_case.execute()
        assert result2.total_refunded == 0
        # Не появились новые audit-записи
        assert len(audit.entries) == 1
        # Не появились новые pool-incr
        assert len(pool_repo.calls) == 1
        # UoW коммитился оба раза
        assert uow.commits == 2


# --------------------------------------------------------------------------- #
# Pagination
# --------------------------------------------------------------------------- #


class TestPagination:
    """Если просрочено больше _BATCH_SIZE — обрабатываем все в pagination-loop-е."""

    @pytest.mark.asyncio
    async def test_more_than_batch_size_lots_all_refunded(self) -> None:
        """Создаём `_BATCH_SIZE + 5` просроченных лотов → все рефандятся."""
        lot_repo = FakePrizeLotRepository()
        total_lots = _BATCH_SIZE + 5
        for i in range(total_lots):
            await _seed_reserved_lot(
                repo=lot_repo,
                currency=Currency.USDT_DECIMAL,
                amount_native=1_000_000 + i,
                reserved_at=_FIXED_NOW - timedelta(hours=49, seconds=i),
            )
        use_case, _, _, audit, _, _, _ = _make_use_case(lot_repo=lot_repo)

        result = await use_case.execute()

        assert result.total_refunded == total_lots
        assert dict(result.refunded_per_currency) == {Currency.USDT_DECIMAL: total_lots}
        assert len(audit.entries) == total_lots
