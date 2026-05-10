"""Unit-тесты use-case-а `RecordDonation` (Спринт 4.1-B / Шаг B.2, ГДД §12.6).

Покрытие:

* **Floor-округление** (3 кейса): 100⋆ → +10⋆, 19⋆ → +1⋆, 9⋆ → 0⋆ (фильтруется).
  ГДД §12.6.1 — `donation = payment_amount_native // 10`.
* **Все 3 валюты** (3 кейса в параметризованном тесте): STARS, TON_NANO,
  USDT_DECIMAL — каждый с 100 native-юнитов на входе → +10 в нужной
  валюте, остальные не меняются.
* **Result-shape** (3 кейса): поле `applied=True/False`, `donation_amount_native`,
  `pool_after` указывают на ровно один свежесобранный снапшот.
* **0-фильтр** (2 кейса): при `payment_amount_native < 10` — `apply_increment`
  не вызывается, `get_current` вызывается ровно один раз для снапшота;
  `payment_amount_native == 0` — то же самое.
* **Накопление** (1 кейс): два последовательных вызова `execute(...)` в
  одной валюте → пул растёт линейно.
* **Изоляция валют** (1 кейс): инкременты в разных валютах не сходятся —
  `STARS += 10` не трогает `TON_NANO`/`USDT_DECIMAL`.

Итого: 14 тестов (часть параметризованных).
"""

from __future__ import annotations

import pytest

from pipirik_wars.application.monetization import (
    RecordDonation,
    RecordDonationCommand,
    RecordDonationResult,
)
from pipirik_wars.domain.monetization import (
    Currency,
    IdempotencyKey,
    PrizePool,
    StarsPoolBalance,
    TonNanoAmount,
    UsdtDecimalAmount,
)
from tests.fakes import FakePrizePoolRepository

_KEY = IdempotencyKey("paid_roulette:42:tg-charge-001")


# --------------------------------------------------------------------------- #
# Floor-округление (ГДД §12.6.1)
# --------------------------------------------------------------------------- #


class TestFloorRounding:
    """`donation = payment_amount_native // 10` — `floor`-округление в пользу платформы."""

    @pytest.mark.asyncio
    async def test_100_stars_yields_10_stars_donation(self) -> None:
        repo = FakePrizePoolRepository()
        use_case = RecordDonation(prize_pool_repository=repo)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=100,
                idempotency_key=_KEY,
            )
        )

        assert result.donation_amount_native == 10
        assert result.applied is True
        assert result.pool_after.stars.value == 10

    @pytest.mark.asyncio
    async def test_19_stars_yields_1_star_donation_floor(self) -> None:
        repo = FakePrizePoolRepository()
        use_case = RecordDonation(prize_pool_repository=repo)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=19,
                idempotency_key=_KEY,
            )
        )

        # 19 // 10 == 1 (floor)
        assert result.donation_amount_native == 1
        assert result.applied is True
        assert result.pool_after.stars.value == 1

    @pytest.mark.asyncio
    async def test_9_stars_yields_zero_donation_filtered(self) -> None:
        repo = FakePrizePoolRepository()
        use_case = RecordDonation(prize_pool_repository=repo)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=9,
                idempotency_key=_KEY,
            )
        )

        # 9 // 10 == 0 — фильтруется, apply_increment не вызывается.
        assert result.donation_amount_native == 0
        assert result.applied is False
        assert result.pool_after.stars.value == 0
        assert repo.calls == []
        # При 0-фильтре pool-снапшот берётся через get_current.
        assert repo.get_current_calls == 1


# --------------------------------------------------------------------------- #
# Все 3 валюты
# --------------------------------------------------------------------------- #


class TestAllCurrencies:
    """100 native-юнитов → +10 в нужной валюте, остальные не трогаем."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("currency", "expected_field"),
        [
            (Currency.STARS, "stars"),
            (Currency.TON_NANO, "ton_nano"),
            (Currency.USDT_DECIMAL, "usdt_decimal"),
        ],
        ids=["STARS", "TON_NANO", "USDT_DECIMAL"],
    )
    async def test_increment_applies_to_correct_currency_only(
        self,
        currency: Currency,
        expected_field: str,
    ) -> None:
        repo = FakePrizePoolRepository()
        use_case = RecordDonation(prize_pool_repository=repo)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=currency,
                payment_amount_native=100,
                idempotency_key=_KEY,
            )
        )

        assert result.donation_amount_native == 10
        assert result.applied is True

        # +10 в нужной валюте.
        target = getattr(result.pool_after, expected_field)
        assert target.value == 10

        # Остальные валюты — нули.
        for other_field in ("stars", "ton_nano", "usdt_decimal"):
            if other_field != expected_field:
                other = getattr(result.pool_after, other_field)
                assert other.value == 0


# --------------------------------------------------------------------------- #
# Result-shape (форма ответа)
# --------------------------------------------------------------------------- #


class TestResultShape:
    """`RecordDonationResult` — `(donation_amount_native, pool_after, applied)`."""

    @pytest.mark.asyncio
    async def test_result_is_frozen_dataclass(self) -> None:
        repo = FakePrizePoolRepository()
        use_case = RecordDonation(prize_pool_repository=repo)
        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=100,
                idempotency_key=_KEY,
            )
        )

        assert isinstance(result, RecordDonationResult)
        with pytest.raises(AttributeError):
            result.applied = False

    @pytest.mark.asyncio
    async def test_pool_after_reflects_post_increment_state(self) -> None:
        repo = FakePrizePoolRepository(
            state=PrizePool(
                stars=StarsPoolBalance(50),
                ton_nano=TonNanoAmount(0),
                usdt_decimal=UsdtDecimalAmount(0),
            )
        )
        use_case = RecordDonation(prize_pool_repository=repo)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=100,  # +10
                idempotency_key=_KEY,
            )
        )

        # 50 (start) + 10 (delta) == 60.
        assert result.pool_after.stars.value == 60
        assert result.applied is True
        assert result.donation_amount_native == 10

    @pytest.mark.asyncio
    async def test_pool_after_is_immutable_aggregate(self) -> None:
        repo = FakePrizePoolRepository()
        use_case = RecordDonation(prize_pool_repository=repo)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=100,
                idempotency_key=_KEY,
            )
        )

        # PrizePool — frozen+slots → AttributeError при попытке мутации.
        with pytest.raises(AttributeError):
            result.pool_after.stars = StarsPoolBalance(999)


# --------------------------------------------------------------------------- #
# 0-фильтр (донат < 10 native-юнитов)
# --------------------------------------------------------------------------- #


class TestZeroDonationFilter:
    """При `payment_amount_native < 10` — `apply_increment` не вызывается."""

    @pytest.mark.asyncio
    async def test_payment_below_threshold_does_not_call_apply_increment(self) -> None:
        repo = FakePrizePoolRepository()
        use_case = RecordDonation(prize_pool_repository=repo)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=5,
                idempotency_key=_KEY,
            )
        )

        assert result.applied is False
        assert result.donation_amount_native == 0
        assert repo.calls == []
        # get_current — ровно один (для снапшота в результате).
        assert repo.get_current_calls == 1

    @pytest.mark.asyncio
    async def test_zero_payment_filtered(self) -> None:
        repo = FakePrizePoolRepository()
        use_case = RecordDonation(prize_pool_repository=repo)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=0,
                idempotency_key=_KEY,
            )
        )

        assert result.applied is False
        assert result.donation_amount_native == 0
        assert repo.calls == []

    @pytest.mark.asyncio
    async def test_zero_filter_returns_current_pool_snapshot(self) -> None:
        # Если в репозитории уже есть какой-то стейт — 0-фильтр должен
        # вернуть тот же стейт (а не PrizePool.empty()).
        existing_state = PrizePool(
            stars=StarsPoolBalance(100),
            ton_nano=TonNanoAmount(50),
            usdt_decimal=UsdtDecimalAmount(25),
        )
        repo = FakePrizePoolRepository(state=existing_state)
        use_case = RecordDonation(prize_pool_repository=repo)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=9,
                idempotency_key=_KEY,
            )
        )

        assert result.applied is False
        assert result.pool_after == existing_state


# --------------------------------------------------------------------------- #
# Накопление
# --------------------------------------------------------------------------- #


class TestAccumulation:
    """Два последовательных вызова в одной валюте — пул растёт линейно."""

    @pytest.mark.asyncio
    async def test_two_calls_accumulate_into_same_currency(self) -> None:
        repo = FakePrizePoolRepository()
        use_case = RecordDonation(prize_pool_repository=repo)

        result_1 = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=100,
                idempotency_key=IdempotencyKey("paid_roulette:42:tg-charge-001"),
            )
        )
        result_2 = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=200,
                idempotency_key=IdempotencyKey("paid_roulette:42:tg-charge-002"),
            )
        )

        assert result_1.pool_after.stars.value == 10
        assert result_2.pool_after.stars.value == 30  # 10 + 20
        assert len(repo.calls) == 2
        assert repo.calls[0].amount_native == 10
        assert repo.calls[1].amount_native == 20


# --------------------------------------------------------------------------- #
# Изоляция валют
# --------------------------------------------------------------------------- #


class TestCurrencyIsolation:
    """Инкремент в одной валюте не трогает остальные."""

    @pytest.mark.asyncio
    async def test_three_currencies_increment_independently(self) -> None:
        repo = FakePrizePoolRepository()
        use_case = RecordDonation(prize_pool_repository=repo)

        await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=100,  # +10 STARS
                idempotency_key=IdempotencyKey("paid_roulette:1:a"),
            )
        )
        await use_case.execute(
            RecordDonationCommand(
                currency=Currency.TON_NANO,
                payment_amount_native=1_000_000_000,  # +100_000_000 TON_NANO
                idempotency_key=IdempotencyKey("ton_donation:2:b"),
            )
        )
        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.USDT_DECIMAL,
                payment_amount_native=5_000_000,  # +500_000 USDT_DECIMAL
                idempotency_key=IdempotencyKey("usdt_donation:3:c"),
            )
        )

        assert result.pool_after.stars.value == 10
        assert result.pool_after.ton_nano.value == 100_000_000
        assert result.pool_after.usdt_decimal.value == 500_000


# --------------------------------------------------------------------------- #
# Команда — frozen dataclass
# --------------------------------------------------------------------------- #


class TestCommandShape:
    """`RecordDonationCommand` — frozen+slots, поля заданы in-order."""

    def test_command_is_frozen(self) -> None:
        cmd = RecordDonationCommand(
            currency=Currency.STARS,
            payment_amount_native=100,
            idempotency_key=_KEY,
        )
        with pytest.raises(AttributeError):
            cmd.payment_amount_native = 999

    def test_command_fields(self) -> None:
        cmd = RecordDonationCommand(
            currency=Currency.TON_NANO,
            payment_amount_native=1_000_000_000,
            idempotency_key=_KEY,
        )
        assert cmd.currency is Currency.TON_NANO
        assert cmd.payment_amount_native == 1_000_000_000
        assert cmd.idempotency_key == _KEY
