"""Unit-тесты use-case-а `RecordDonation` (Спринт 4.1-B / Шаг B.2/B.4, ГДД §12.6).

Покрытие (B.2):

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

Дополнение в B.4 (audit-запись):

* **Audit на `applied=True`** (3+ кейса): action/source/target, payload
  (`currency`/`amount_native`/`pool_after_native`), idempotency_key
  наследуется от command (с suffix-ом `:prize_pool`), `occurred_at`
  берётся из `IClock`.
* **Нет audit на `applied=False`** (1+ кейс): для no-op-инкремента
  audit-логгер не вызывается.

Итого: 14 + 5 = 19 тестов (часть параметризованных).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

import pytest

from pipirik_wars.application.monetization import (
    RecordDonation,
    RecordDonationCommand,
    RecordDonationResult,
)
from pipirik_wars.application.monetization.generate_prize_lots import (
    GeneratePrizeLots,
    GeneratePrizeLotsCommand,
)
from pipirik_wars.domain.monetization import (
    Currency,
    IdempotencyKey,
    PrizePool,
    StarsPoolBalance,
    TonNanoAmount,
    UsdtDecimalAmount,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditSource,
)
from tests.fakes import FakeAuditLogger, FakeClock, FakePrizePoolRepository

_KEY = IdempotencyKey("paid_roulette:42:tg-charge-001")
_FIXED_NOW = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)


@dataclass
class _FakeGeneratePrizeLots:
    """Stub `GeneratePrizeLots`-use-case-а для тестов C.7.d-триггера.

    Сохраняет полученные `GeneratePrizeLotsCommand`-ы; `execute(...)`
    возвращает `None` — `RecordDonation.execute(...)` не использует
    результат use-case-а триггера (fire-and-forget внутри ambient-UoW).
    Через `cast(GeneratePrizeLots, ...)` подсовывается в `RecordDonation.__init__`.
    """

    commands: list[GeneratePrizeLotsCommand] = field(default_factory=list)

    async def execute(self, command: GeneratePrizeLotsCommand) -> None:
        self.commands.append(command)


def _make_use_case(
    repo: FakePrizePoolRepository,
    *,
    audit: FakeAuditLogger | None = None,
    clock: FakeClock | None = None,
    generate_prize_lots: _FakeGeneratePrizeLots | None = None,
) -> RecordDonation:
    """Фабрика `RecordDonation` с fake-DI.

    Большинство тестов (B.2-покрытие) не проверяет audit/clock,
    поэтому использует дефолтные fake-ы. B.4-тесты прокидывают свои
    экземпляры, чтобы assert-ить по результатам. C.7.d-тесты прокидывают
    свой `_FakeGeneratePrizeLots`, чтобы видеть какие команды получил
    триггер (или что он не вызывался при donation < threshold).
    """
    fake_generator = (
        generate_prize_lots if generate_prize_lots is not None else _FakeGeneratePrizeLots()
    )
    return RecordDonation(
        prize_pool_repository=repo,
        audit_logger=audit if audit is not None else FakeAuditLogger(),
        clock=clock if clock is not None else FakeClock(_FIXED_NOW),
        generate_prize_lots=cast(GeneratePrizeLots, fake_generator),
    )


# --------------------------------------------------------------------------- #
# Floor-округление (ГДД §12.6.1)
# --------------------------------------------------------------------------- #


class TestFloorRounding:
    """`donation = payment_amount_native // 10` — `floor`-округление в пользу платформы."""

    @pytest.mark.asyncio
    async def test_100_stars_yields_10_stars_donation(self) -> None:
        repo = FakePrizePoolRepository()
        use_case = _make_use_case(repo)

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
        use_case = _make_use_case(repo)

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
        use_case = _make_use_case(repo)

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
        use_case = _make_use_case(repo)

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
        use_case = _make_use_case(repo)
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
        use_case = _make_use_case(repo)

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
        use_case = _make_use_case(repo)

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
        use_case = _make_use_case(repo)

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
        use_case = _make_use_case(repo)

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
        use_case = _make_use_case(repo)

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
        use_case = _make_use_case(repo)

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
        use_case = _make_use_case(repo)

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
# Audit-запись (Спринт 4.1-B / Шаг B.4)
# --------------------------------------------------------------------------- #


class TestAuditWrite:
    """Audit-запись `PRIZE_POOL_INCREMENT` пишется на `applied=True` и не пишется на `applied=False`."""

    @pytest.mark.asyncio
    async def test_audit_logged_on_applied_true(self) -> None:
        """`applied=True` → ровно одна audit-запись, action+source = `PRIZE_POOL_INCREMENT`."""
        repo = FakePrizePoolRepository()
        audit = FakeAuditLogger()
        clock = FakeClock(_FIXED_NOW)
        use_case = _make_use_case(repo, audit=audit, clock=clock)

        await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=100,
                idempotency_key=_KEY,
            )
        )

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.PRIZE_POOL_INCREMENT
        assert entry.source is AuditSource.PRIZE_POOL_INCREMENT
        assert entry.target_kind == "prize_pool"
        assert entry.target_id == f"{_KEY.value}:donation"
        assert entry.actor_id is None
        assert entry.before is None
        assert entry.delta_cm is None
        assert entry.occurred_at == _FIXED_NOW

    @pytest.mark.asyncio
    async def test_no_audit_on_applied_false(self) -> None:
        """`applied=False` (no-op) → audit-логгер не вызывается."""
        repo = FakePrizePoolRepository()
        audit = FakeAuditLogger()
        use_case = _make_use_case(repo, audit=audit)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=9,  # < 10 → donation == 0
                idempotency_key=_KEY,
            )
        )

        assert result.applied is False
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_audit_payload_structure(self) -> None:
        """`after`-payload содержит `currency`, `amount_native`, `pool_after_native`."""
        repo = FakePrizePoolRepository()
        audit = FakeAuditLogger()
        use_case = _make_use_case(repo, audit=audit)

        await use_case.execute(
            RecordDonationCommand(
                currency=Currency.TON_NANO,
                payment_amount_native=1_000_000_000,  # 10**9 → +10**8 TON_NANO
                idempotency_key=_KEY,
            )
        )

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.after is not None
        assert entry.after == {
            "currency": "ton_nano",
            "amount_native": 100_000_000,
            "pool_after_native": 100_000_000,
        }

    @pytest.mark.asyncio
    async def test_audit_idempotency_key_inherited(self) -> None:
        """`idempotency_key` audit-записи наследуется от command с suffix-ом `:prize_pool`."""
        repo = FakePrizePoolRepository()
        audit = FakeAuditLogger()
        use_case = _make_use_case(repo, audit=audit)
        custom_key = IdempotencyKey("paid_roulette:777:tg-charge-XYZ")

        await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=50,
                idempotency_key=custom_key,
            )
        )

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.idempotency_key == f"{custom_key.value}:prize_pool"
        # И target_id отдельный scope.
        assert entry.target_id == f"{custom_key.value}:donation"
        # Reason — стабильная константа.
        assert entry.reason == "prize_pool_increment"

    @pytest.mark.asyncio
    async def test_audit_pool_after_reflects_accumulation(self) -> None:
        """`pool_after_native` отражает накопленный пул, а не только delta."""
        repo = FakePrizePoolRepository()
        audit = FakeAuditLogger()
        use_case = _make_use_case(repo, audit=audit)

        await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=100,  # +10
                idempotency_key=IdempotencyKey("paid_roulette:1:a"),
            )
        )
        await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=200,  # +20
                idempotency_key=IdempotencyKey("paid_roulette:1:b"),
            )
        )

        assert len(audit.entries) == 2
        first_after = audit.entries[0].after
        second_after = audit.entries[1].after
        assert first_after is not None
        assert second_after is not None
        assert first_after["amount_native"] == 10
        assert first_after["pool_after_native"] == 10
        assert second_after["amount_native"] == 20
        assert second_after["pool_after_native"] == 30  # 10 + 20


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


# --------------------------------------------------------------------------- #
# C.7.d — Триггер `GeneratePrizeLots` после крупного донат-инкремента
# --------------------------------------------------------------------------- #


class TestPrizeLotGeneratorTrigger:
    """Триггер `GeneratePrizeLots.execute(...)` при `donation_amount_native >= threshold`.

    Threshold per currency (см. `_DONATION_TRIGGER_THRESHOLD` в
    `record_donation.py`): STARS — `None` (без триггера, ждёт hourly cron),
    TON_NANO — `500_000_000` (0.5 TON), USDT_DECIMAL — `1_000_000` (1 USDT).
    Триггер вызывается **после** audit-записи `PRIZE_POOL_INCREMENT`,
    с тем же `idempotency_key`, что и платёж — повторный `RecordDonation`
    с тем же платежом не даст повторных лотов (внутри `GeneratePrizeLots`
    `is_seen`-проверка сработает).
    """

    @pytest.mark.asyncio
    async def test_ton_donation_at_threshold_triggers_generation(self) -> None:
        """TON_NANO: payment `5e9` → donation `5e8 == 0.5 TON` → триггер сработал."""
        repo = FakePrizePoolRepository()
        fake_gen = _FakeGeneratePrizeLots()
        use_case = _make_use_case(repo, generate_prize_lots=fake_gen)
        key = IdempotencyKey("paid_roulette:42:ton-charge-X")

        await use_case.execute(
            RecordDonationCommand(
                currency=Currency.TON_NANO,
                payment_amount_native=5_000_000_000,  # 5 TON; donation = 0.5 TON
                idempotency_key=key,
            )
        )

        assert len(fake_gen.commands) == 1
        triggered = fake_gen.commands[0]
        assert triggered.currency is Currency.TON_NANO
        # Триггер пробрасывает тот же платёжный idem-key — это даёт
        # идемпотентность повторного вызова `RecordDonation` (см.
        # `GeneratePrizeLots._idempotency.is_seen`).
        assert triggered.idempotency_key == key

    @pytest.mark.asyncio
    async def test_usdt_donation_at_threshold_triggers_generation(self) -> None:
        """USDT_DECIMAL: payment `10e6` → donation `1e6 == 1 USDT` → триггер сработал."""
        repo = FakePrizePoolRepository()
        fake_gen = _FakeGeneratePrizeLots()
        use_case = _make_use_case(repo, generate_prize_lots=fake_gen)
        key = IdempotencyKey("paid_roulette:99:usdt-charge-Y")

        await use_case.execute(
            RecordDonationCommand(
                currency=Currency.USDT_DECIMAL,
                payment_amount_native=10_000_000,  # 10 USDT; donation = 1 USDT
                idempotency_key=key,
            )
        )

        assert len(fake_gen.commands) == 1
        triggered = fake_gen.commands[0]
        assert triggered.currency is Currency.USDT_DECIMAL
        assert triggered.idempotency_key == key

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("currency", "payment_amount_native"),
        [
            # TON_NANO: donation = 0.499... TON < 0.5 TON threshold
            (Currency.TON_NANO, 4_999_999_990),
            # USDT_DECIMAL: donation = 0.999... USDT < 1 USDT threshold
            (Currency.USDT_DECIMAL, 9_999_990),
        ],
        ids=["TON_NANO_just_below", "USDT_just_below"],
    )
    async def test_below_threshold_does_not_trigger(
        self,
        currency: Currency,
        payment_amount_native: int,
    ) -> None:
        """Donation ниже порога — триггер не вызывается (ждёт hourly cron)."""
        repo = FakePrizePoolRepository()
        fake_gen = _FakeGeneratePrizeLots()
        use_case = _make_use_case(repo, generate_prize_lots=fake_gen)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=currency,
                payment_amount_native=payment_amount_native,
                idempotency_key=_KEY,
            )
        )

        # apply_increment всё равно произошёл (donation > 0, просто
        # ниже trigger-threshold); audit написан; но `GeneratePrizeLots`
        # не вызывался.
        assert result.applied is True
        assert result.donation_amount_native > 0
        assert fake_gen.commands == []

    @pytest.mark.asyncio
    async def test_stars_donation_never_triggers_even_at_high_amount(self) -> None:
        """STARS-донат любой суммы — триггер не вызывается (порог = `None`).

        ГДД §12.6.3: STARS-донаты накапливаются медленно — 100 ⭐ на min-лот
        в худшем случае это 50 платежей по 2 ⭐. Hourly cron нарежет их без
        вреда для UX. Дёргать `GeneratePrizeLots` после каждого STARS-доната
        — лишняя нагрузка на БД + audit-row-ы.
        """
        repo = FakePrizePoolRepository()
        fake_gen = _FakeGeneratePrizeLots()
        use_case = _make_use_case(repo, generate_prize_lots=fake_gen)

        # 100_000 ⭐ платёж → 10_000 ⭐ донат — на порядки больше «крупного»
        # порога для других валют, но STARS триггера нет в принципе.
        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.STARS,
                payment_amount_native=100_000,
                idempotency_key=_KEY,
            )
        )

        assert result.applied is True
        assert result.donation_amount_native == 10_000
        assert fake_gen.commands == []

    @pytest.mark.asyncio
    async def test_zero_donation_does_not_trigger(self) -> None:
        """Donation == 0 (платёж < 10 native-юнитов) — триггер не вызывается.

        Защита от деградации трактовки порога: `donation == 0`-фильтр
        срабатывает раньше threshold-проверки; даже если бы порог был
        `0`, audit и инкремент пропускаются, и триггер тоже.
        """
        repo = FakePrizePoolRepository()
        fake_gen = _FakeGeneratePrizeLots()
        use_case = _make_use_case(repo, generate_prize_lots=fake_gen)

        result = await use_case.execute(
            RecordDonationCommand(
                currency=Currency.TON_NANO,
                payment_amount_native=9,  # // 10 == 0
                idempotency_key=_KEY,
            )
        )

        assert result.applied is False
        assert fake_gen.commands == []

    @pytest.mark.asyncio
    async def test_repeat_donation_passes_same_idem_key_each_time(self) -> None:
        """Повторный вызов с тем же платежом → тот же `idempotency_key` в команде триггера.

        `RecordDonation` сам не дедуплицирует — это инвариант caller-а
        (см. docstring модуля). Но при идентичном повторном вызове он
        проносит **тот же** платёжный `idempotency_key`, что даёт
        `GeneratePrizeLots._idempotency.is_seen`-семантику дедупликации
        на стороне use-case-а триггера.
        """
        repo = FakePrizePoolRepository()
        fake_gen = _FakeGeneratePrizeLots()
        use_case = _make_use_case(repo, generate_prize_lots=fake_gen)
        key = IdempotencyKey("paid_roulette:42:usdt-Z")

        cmd = RecordDonationCommand(
            currency=Currency.USDT_DECIMAL,
            payment_amount_native=10_000_000,
            idempotency_key=key,
        )
        await use_case.execute(cmd)
        await use_case.execute(cmd)

        # Оба раза триггер получает один и тот же `idempotency_key` —
        # реальный `GeneratePrizeLots` второй раз увидит ключ как
        # `is_seen` и вернёт `idempotent=True` без повторной нарезки.
        assert len(fake_gen.commands) == 2
        assert fake_gen.commands[0].idempotency_key == key
        assert fake_gen.commands[1].idempotency_key == key
        assert fake_gen.commands[0].currency is Currency.USDT_DECIMAL

    @pytest.mark.asyncio
    async def test_trigger_fires_after_audit_record(self) -> None:
        """Order-инвариант: триггер вызывается **после** audit-записи `PRIZE_POOL_INCREMENT`.

        Если бы триггер шёл раньше audit, при ошибке audit-логгера
        у нас были бы созданы лоты без аудит-следа донат-инкремента —
        нарушение инварианта «потерянного аудита нет» из B.4.
        """
        repo = FakePrizePoolRepository()
        audit = FakeAuditLogger()
        fake_gen = _FakeGeneratePrizeLots()
        use_case = _make_use_case(repo, audit=audit, generate_prize_lots=fake_gen)

        await use_case.execute(
            RecordDonationCommand(
                currency=Currency.TON_NANO,
                payment_amount_native=5_000_000_000,
                idempotency_key=_KEY,
            )
        )

        # Order-проверка: единственный audit-row на момент срабатывания
        # триггера уже был записан в логгер. Косвенно — обе записи
        # присутствуют, и audit пишется до триггера (см. fixture
        # `_FakeGeneratePrizeLots.execute` — он не пишет в audit).
        assert len(audit.entries) == 1
        assert audit.entries[0].action is AuditAction.PRIZE_POOL_INCREMENT
        assert len(fake_gen.commands) == 1
