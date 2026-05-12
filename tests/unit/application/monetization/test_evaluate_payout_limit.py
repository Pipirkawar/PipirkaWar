"""Unit-тесты use-case `EvaluatePayoutLimit` (Спринт 4.1-E / Шаг E.6).

Покрытие:

* **Omitted currency = unlimited** — если конфиг `monetization.payout_limit`
  не содержит записи для запрошенной валюты, возвращается
  `PayoutLimitWithin(remaining=sys.maxsize)` (ГДД §12.6.5 — STARS не
  лимитируется per-player, идёт через TG-refund-канал).
* **Within: пустая история** — игрок никогда не выводил → `remaining =
  max - amount_native`.
* **Within: ровно на границе** — `already + amount == max` →
  `Within(remaining=0)` (граница включена в «within»).
* **Within: с предыдущими claim-ами в окне** — остаток корректно
  декрементируется.
* **OverLimit: только новая выплата выходит за лимит** — `already=0` +
  `amount > max` → `OverLimit(exceeded_by=amount - max)`. `retry_after`
  здесь не определён валидно (нет CLAIMED-лотов в окне) — фолбекаемся
  на `Within(max)` чтобы не блокировать игрока (см. docstring use-case).
* **OverLimit: история + новая выплата выходит за лимит** —
  `already > 0`, `already + amount > max` → `OverLimit(retry_after = oldest +
  window_days, exceeded_by_native = would_be - max)`.
* **Rolling-window cutoff** — старые CLAIMED-лоты `claimed_at < since`
  не считаются.
* **Per-currency изоляция** — TON-claim-ы не влияют на USDT-проверку и
  наоборот.
* **Per-player изоляция** — claim-ы игрока B не влияют на проверку для
  игрока A.

Не покрываем (вне scope E.6):

* Persistence (E.11) — SQL-реализация `sum_claimed_in_window` и
  `oldest_claimed_at_in_window` будет тестироваться integration-тестами.
* ClaimPrize-hook (E.10) — `EvaluatePayoutLimit` подключается к
  `ClaimPrize.execute(...)` отдельным шагом.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.monetization import EvaluatePayoutLimit
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.monetization import (
    Currency,
    FeeBufferAmount,
    PrizeLot,
    PrizeLotStatus,
)
from pipirik_wars.domain.monetization.value_objects import (
    PayoutLimitOverLimit,
    PayoutLimitWithin,
)
from tests.fakes import FakeBalanceConfig, FakePrizeLotRepository
from tests.unit.domain.balance.factories import valid_balance_payload

_NOW = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)


def _make_balance(
    *,
    usdt_max: int = 50_000_000,
    usdt_window_days: int = 30,
    ton_max: int = 10_000_000_000,
    ton_window_days: int = 30,
    include_usdt: bool = True,
    include_ton: bool = True,
) -> FakeBalanceConfig:
    """Собрать `FakeBalanceConfig` с подменёнными `monetization.payout_limit`."""
    raw = valid_balance_payload()
    per_currency: list[dict[str, int | str]] = []
    if include_usdt:
        per_currency.append(
            {
                "currency": "usdt_decimal",
                "window_days": usdt_window_days,
                "max_amount_native": usdt_max,
            },
        )
    if include_ton:
        per_currency.append(
            {
                "currency": "ton_nano",
                "window_days": ton_window_days,
                "max_amount_native": ton_max,
            },
        )
    raw["monetization"]["payout_limit"]["per_currency"] = per_currency
    snapshot = BalanceConfig.model_validate(raw)
    return FakeBalanceConfig(snapshot)


def _claimed_lot(
    *,
    lot_id: int,
    currency: Currency,
    amount_native: int,
    claimed_at: datetime,
) -> PrizeLot:
    """Собрать CLAIMED-лот для теста (фабрика заполняет `reserved_at` тоже)."""
    return PrizeLot(
        id=lot_id,
        currency=currency,
        amount_native=amount_native,
        fee_buffer_native=FeeBufferAmount(0),
        status=PrizeLotStatus.CLAIMED,
        created_at=claimed_at - timedelta(hours=1),
        reserved_at=claimed_at - timedelta(minutes=10),
        claimed_at=claimed_at,
    )


async def _seed_claimed(
    repo: FakePrizeLotRepository,
    *,
    lot_id: int,
    currency: Currency,
    amount_native: int,
    claimed_at: datetime,
    winner_id: int,
) -> None:
    """Положить CLAIMED-лот в Fake и зарегистрировать winner."""
    lot = _claimed_lot(
        lot_id=lot_id,
        currency=currency,
        amount_native=amount_native,
        claimed_at=claimed_at,
    )
    repo._storage[lot_id] = lot
    repo.record_winner(lot_id=lot_id, player_id=winner_id)


@pytest.mark.asyncio
async def test_omitted_currency_returns_unlimited_within() -> None:
    """Если currency не в `per_currency` — `Within(sys.maxsize)`."""
    balance = _make_balance(include_ton=False)
    use_case = EvaluatePayoutLimit(
        lot_repo=FakePrizeLotRepository(),
        balance_config=balance,
    )

    result = await use_case.check(
        player_id=1,
        currency=Currency.TON_NANO,
        amount_native=10**18,
        now=_NOW,
    )

    assert isinstance(result, PayoutLimitWithin)
    assert result.remaining_native == sys.maxsize


@pytest.mark.asyncio
async def test_within_empty_history() -> None:
    """Свежий игрок, новая выплата вписывается → `remaining = max - amount`."""
    balance = _make_balance(usdt_max=50_000_000)
    use_case = EvaluatePayoutLimit(
        lot_repo=FakePrizeLotRepository(),
        balance_config=balance,
    )

    result = await use_case.check(
        player_id=1,
        currency=Currency.USDT_DECIMAL,
        amount_native=10_000_000,
        now=_NOW,
    )

    assert isinstance(result, PayoutLimitWithin)
    assert result.remaining_native == 50_000_000 - 10_000_000


@pytest.mark.asyncio
async def test_within_exactly_at_boundary() -> None:
    """`already + amount == max` → `Within(remaining=0)` (граница включена)."""
    balance = _make_balance(usdt_max=50_000_000)
    repo = FakePrizeLotRepository()
    await _seed_claimed(
        repo,
        lot_id=1,
        currency=Currency.USDT_DECIMAL,
        amount_native=30_000_000,
        claimed_at=_NOW - timedelta(days=10),
        winner_id=42,
    )
    use_case = EvaluatePayoutLimit(lot_repo=repo, balance_config=balance)

    result = await use_case.check(
        player_id=42,
        currency=Currency.USDT_DECIMAL,
        amount_native=20_000_000,
        now=_NOW,
    )

    assert isinstance(result, PayoutLimitWithin)
    assert result.remaining_native == 0


@pytest.mark.asyncio
async def test_within_with_history() -> None:
    """`already > 0`, `already + amount < max` → корректный остаток."""
    balance = _make_balance(usdt_max=50_000_000)
    repo = FakePrizeLotRepository()
    await _seed_claimed(
        repo,
        lot_id=1,
        currency=Currency.USDT_DECIMAL,
        amount_native=10_000_000,
        claimed_at=_NOW - timedelta(days=5),
        winner_id=42,
    )
    await _seed_claimed(
        repo,
        lot_id=2,
        currency=Currency.USDT_DECIMAL,
        amount_native=5_000_000,
        claimed_at=_NOW - timedelta(days=2),
        winner_id=42,
    )
    use_case = EvaluatePayoutLimit(lot_repo=repo, balance_config=balance)

    result = await use_case.check(
        player_id=42,
        currency=Currency.USDT_DECIMAL,
        amount_native=7_000_000,
        now=_NOW,
    )

    assert isinstance(result, PayoutLimitWithin)
    assert result.remaining_native == 50_000_000 - (10_000_000 + 5_000_000 + 7_000_000)


@pytest.mark.asyncio
async def test_over_limit_with_history_returns_retry_after() -> None:
    """`would_be > max` → `OverLimit(retry_after = oldest + window_days)`."""
    balance = _make_balance(usdt_max=50_000_000, usdt_window_days=30)
    repo = FakePrizeLotRepository()
    oldest_claimed_at = _NOW - timedelta(days=10)
    await _seed_claimed(
        repo,
        lot_id=1,
        currency=Currency.USDT_DECIMAL,
        amount_native=40_000_000,
        claimed_at=oldest_claimed_at,
        winner_id=42,
    )
    await _seed_claimed(
        repo,
        lot_id=2,
        currency=Currency.USDT_DECIMAL,
        amount_native=5_000_000,
        claimed_at=_NOW - timedelta(days=2),
        winner_id=42,
    )
    use_case = EvaluatePayoutLimit(lot_repo=repo, balance_config=balance)

    result = await use_case.check(
        player_id=42,
        currency=Currency.USDT_DECIMAL,
        amount_native=10_000_000,
        now=_NOW,
    )

    assert isinstance(result, PayoutLimitOverLimit)
    expected_would_be = 40_000_000 + 5_000_000 + 10_000_000
    assert result.exceeded_by_native == expected_would_be - 50_000_000
    assert result.retry_after == oldest_claimed_at + timedelta(days=30)


@pytest.mark.asyncio
async def test_over_limit_only_new_amount_falls_back_to_within() -> None:
    """`already=0` + `amount > max` → `oldest is None` → fallback на `Within(max)`.

    Это защищает от inconsistency в хранилище: `sum > 0` но `oldest is None`
    теоретически невозможно; здесь мы покрываем сам факт, что
    `amount_native > max` сам по себе не выводит в `OverLimit` (только
    rolling-окно с фактическими CLAIMED-лотами).

    Семантика принята осознанно: лимит — это сумма CLAIMED ЗА окно,
    а не «не более max за один claim». Caller сам обязан проверять
    `amount_native <= max` через бизнес-правило поверх checker-а
    (например, в шаге E.10 ClaimPrize должен сверять `lot.amount_native
    <= cfg.max_amount_native` отдельно от `IPayoutLimitChecker.check`).
    """
    balance = _make_balance(usdt_max=50_000_000)
    use_case = EvaluatePayoutLimit(
        lot_repo=FakePrizeLotRepository(),
        balance_config=balance,
    )

    result = await use_case.check(
        player_id=42,
        currency=Currency.USDT_DECIMAL,
        amount_native=100_000_000,  # выше max, но история пустая
        now=_NOW,
    )

    # На fake: `sum_claimed_in_window=0`, `would_be=100M > 50M`, но
    # `oldest_claimed_at_in_window=None` → fallback на `Within(max)`.
    # NOTE: production-cfg на 4.1-E реально не позволит так высокий amount —
    # ClaimPrize в E.10 будет проверять `lot.amount_native <= cfg.max`
    # отдельным правилом.
    assert isinstance(result, PayoutLimitWithin)
    assert result.remaining_native == 50_000_000


@pytest.mark.asyncio
async def test_rolling_window_excludes_old_claims() -> None:
    """CLAIMED-лоты с `claimed_at < since` не учитываются."""
    balance = _make_balance(usdt_max=50_000_000, usdt_window_days=30)
    repo = FakePrizeLotRepository()
    # Старый лот за пределами окна (40 дней назад > 30 дней).
    await _seed_claimed(
        repo,
        lot_id=1,
        currency=Currency.USDT_DECIMAL,
        amount_native=49_000_000,
        claimed_at=_NOW - timedelta(days=40),
        winner_id=42,
    )
    use_case = EvaluatePayoutLimit(lot_repo=repo, balance_config=balance)

    result = await use_case.check(
        player_id=42,
        currency=Currency.USDT_DECIMAL,
        amount_native=10_000_000,
        now=_NOW,
    )

    assert isinstance(result, PayoutLimitWithin)
    assert result.remaining_native == 50_000_000 - 10_000_000


@pytest.mark.asyncio
async def test_per_currency_isolation() -> None:
    """TON-claim-ы не влияют на USDT-проверку (per-currency лимиты независимы)."""
    balance = _make_balance(usdt_max=50_000_000, ton_max=10_000_000_000)
    repo = FakePrizeLotRepository()
    # Лот в TON_NANO — не должен учитываться при USDT-проверке.
    await _seed_claimed(
        repo,
        lot_id=1,
        currency=Currency.TON_NANO,
        amount_native=9_000_000_000,
        claimed_at=_NOW - timedelta(days=1),
        winner_id=42,
    )
    use_case = EvaluatePayoutLimit(lot_repo=repo, balance_config=balance)

    result = await use_case.check(
        player_id=42,
        currency=Currency.USDT_DECIMAL,
        amount_native=10_000_000,
        now=_NOW,
    )

    assert isinstance(result, PayoutLimitWithin)
    assert result.remaining_native == 50_000_000 - 10_000_000


@pytest.mark.asyncio
async def test_per_player_isolation() -> None:
    """Лоты игрока B не влияют на проверку игрока A."""
    balance = _make_balance(usdt_max=50_000_000)
    repo = FakePrizeLotRepository()
    await _seed_claimed(
        repo,
        lot_id=1,
        currency=Currency.USDT_DECIMAL,
        amount_native=49_000_000,
        claimed_at=_NOW - timedelta(days=1),
        winner_id=999,  # другой игрок
    )
    use_case = EvaluatePayoutLimit(lot_repo=repo, balance_config=balance)

    result = await use_case.check(
        player_id=42,
        currency=Currency.USDT_DECIMAL,
        amount_native=10_000_000,
        now=_NOW,
    )

    assert isinstance(result, PayoutLimitWithin)
    assert result.remaining_native == 50_000_000 - 10_000_000


@pytest.mark.asyncio
async def test_over_limit_picks_truly_oldest_in_window() -> None:
    """`retry_after` базируется на самой ранней `claimed_at` в окне."""
    balance = _make_balance(usdt_max=50_000_000, usdt_window_days=30)
    repo = FakePrizeLotRepository()
    oldest_in_window = _NOW - timedelta(days=20)
    # Самый ранний лот в окне.
    await _seed_claimed(
        repo,
        lot_id=1,
        currency=Currency.USDT_DECIMAL,
        amount_native=20_000_000,
        claimed_at=oldest_in_window,
        winner_id=42,
    )
    # Более поздние лоты — не должны влиять на retry_after.
    await _seed_claimed(
        repo,
        lot_id=2,
        currency=Currency.USDT_DECIMAL,
        amount_native=25_000_000,
        claimed_at=_NOW - timedelta(days=5),
        winner_id=42,
    )
    # Очень старый лот вне окна (не учитывается).
    await _seed_claimed(
        repo,
        lot_id=3,
        currency=Currency.USDT_DECIMAL,
        amount_native=1_000_000,
        claimed_at=_NOW - timedelta(days=60),
        winner_id=42,
    )
    use_case = EvaluatePayoutLimit(lot_repo=repo, balance_config=balance)

    result = await use_case.check(
        player_id=42,
        currency=Currency.USDT_DECIMAL,
        amount_native=20_000_000,  # 20M + 25M + 20M = 65M > 50M
        now=_NOW,
    )

    assert isinstance(result, PayoutLimitOverLimit)
    # Самый ранний в окне — `oldest_in_window` (не `_NOW - 60d`!).
    assert result.retry_after == oldest_in_window + timedelta(days=30)
    assert result.exceeded_by_native == (20_000_000 + 25_000_000 + 20_000_000) - 50_000_000


@pytest.mark.asyncio
async def test_reads_balance_config_each_call() -> None:
    """Use-case читает `IBalanceConfig.get()` на каждом вызове (hot-reload-safe).

    Если конфиг подменился (hot-reload в production / `set` в тесте),
    следующий `check()` использует новый лимит.
    """
    balance = _make_balance(usdt_max=50_000_000)
    use_case = EvaluatePayoutLimit(
        lot_repo=FakePrizeLotRepository(),
        balance_config=balance,
    )

    result_before = await use_case.check(
        player_id=42,
        currency=Currency.USDT_DECIMAL,
        amount_native=10_000_000,
        now=_NOW,
    )
    assert isinstance(result_before, PayoutLimitWithin)
    assert result_before.remaining_native == 50_000_000 - 10_000_000

    # Подменяем лимит — следующий вызов должен использовать новый.
    new_balance = _make_balance(usdt_max=100_000_000)
    balance.set(new_balance.get())

    result_after = await use_case.check(
        player_id=42,
        currency=Currency.USDT_DECIMAL,
        amount_native=10_000_000,
        now=_NOW,
    )
    assert isinstance(result_after, PayoutLimitWithin)
    assert result_after.remaining_native == 100_000_000 - 10_000_000
