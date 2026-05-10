"""Unit-тесты use-case-а `SpinPaidRoulette` (Спринт 4.1-A, ГДД §12.5).

Покрытие 10-шагового flow:

* **Idempotency** (2): первый вызов помечает root-key и пишет
  `Payment` + `n_spins` спинов; второй с тем же `IdempotencyKey`
  возвращает `idempotent=True` без побочных эффектов.
* **Errors** (2): `PlayerNotFoundError`, `RouletteThicknessGateError`.
  Оба — без побочных эффектов и с откатом UoW.
* **Charge через `IPaymentLedger`** (3): single-pack (1 ⭐, 1 спин),
  10-pack (9 ⭐, 10 спинов), `IdempotencyConflictError` при коллизии
  (тот же ключ — другая сумма, антифрод 4.1.4).
* **Audit** (3): `PAYMENT_RECORDED` (один на платёж), `ROULETTE_SPIN`
  (по одному на каждый спин), `LENGTH_GRANT` reward только для
  LENGTH-исхода; cost-side `LENGTH_GRANT` **отсутствует** (стоимость
  списана в Stars, а не в см).
* **Outcome × LENGTH-reward** (1 параметризованный): для LENGTH-исхода
  `ILengthGranter.grant(...)` вызывается с `source=ROULETTE_PAID_REWARD`;
  для не-LENGTH (ITEM, SCROLL_REGULAR, SCROLL_BLESSED) — не вызывается.
* **Spin idempotency keys** (1): каждый из `n_spins` получает суффикс
  `:i` к корневому `IdempotencyKey`; DB-уровневая UNIQUE-дедупликация.
* **UoW commit/rollback** (1): на gate-ошибке UoW откатывает
  транзакцию (`rollbacks==1, commits==0`); на happy-path —
  `commits==1, rollbacks==0`.

Итого: 14 тестов (включая 1 параметризованный с 3 случаями).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TypeVar

import pytest

from pipirik_wars.application.monetization import (
    PaidRoulettePack,
    RecordDonation,
    SpinPaidRoulette,
    SpinPaidRouletteCommand,
)
from pipirik_wars.application.progression import AddLength
from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    RouletteOutcomeKind,
)
from pipirik_wars.domain.monetization import (
    Currency,
    IdempotencyConflictError,
    IdempotencyKey,
    Payment,
    PaymentStatus,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    Thickness,
    Username,
)
from pipirik_wars.domain.roulette import RouletteOutcome
from pipirik_wars.domain.roulette.errors import RouletteThicknessGateError
from pipirik_wars.domain.shared.ports import AuditAction, IRandom
from pipirik_wars.domain.shared.ports.audit import AuditSource
from tests.fakes import (
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeIdempotencyKey,
    FakePaymentLedger,
    FakePlayerRepository,
    FakePrizePoolApplyIncrementCall,
    FakePrizePoolRepository,
    FakeRouletteSpinRepository,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import valid_balance_payload

_T = TypeVar("_T")
_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #


class _ScriptedRandom(IRandom):
    """Стаб `IRandom` для тестов use-case-а: форсит конкретный исход.

    Используется в паре с balance-конфигом, где у нужного исхода
    `weight=1.0`, остальные `0.0` (см. `_balance_with_only_paid_kind`):
    `weighted_choice` валидирует `all weights > 0`, поэтому picker
    отфильтровывает нулевые до вызова. Так стаб видит только items
    с одним вариантом — выбор тривиален.

    Для LENGTH: `randint(low, high)` возвращает фиксированный
    `length_cm`. Для других методов `IRandom` — `NotImplementedError`.
    """

    __slots__ = ("_fixed_length_cm",)

    def __init__(self, *, fixed_length_cm: int = 50) -> None:
        self._fixed_length_cm = fixed_length_cm

    def randint(self, low: int, high: int) -> int:
        if low > high:
            raise ValueError("randint: low > high")
        if not low <= self._fixed_length_cm <= high:
            raise ValueError(
                f"_ScriptedRandom.randint({low}, {high}) cannot return "
                f"fixed_length_cm={self._fixed_length_cm} (out of range)",
            )
        return self._fixed_length_cm

    def weighted_choice(self, items: Sequence[_T], weights: Sequence[int]) -> _T:
        if not items:
            raise ValueError("weighted_choice from empty sequence")
        return items[0]

    def uniform(self, low: float, high: float) -> float:
        raise NotImplementedError

    def choice(self, items: Sequence[_T]) -> _T:
        raise NotImplementedError

    def deterministic_uint(self, seed: str, modulo: int) -> int:
        raise NotImplementedError

    def shuffle(self, items: Sequence[_T]) -> tuple[_T, ...]:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _balance_payload_with_paid_block(
    *,
    only_kind: RouletteOutcomeKind | None = None,
    cost_stars_single: int = 1,
    cost_stars_pack10: int = 9,
    pack10_spins: int = 10,
    min_thickness_level: int = 1,
) -> dict[str, object]:
    """Базовый payload `BalanceConfig` с прокинутым `roulette.paid`-блоком.

    Если `only_kind` задан — `weight=1.0` только у него, остальные `0.0`.
    Если `None` — все `weight=1.0` (используется для idempotency-теста,
    где исход не важен).
    """
    payload: dict[str, object] = valid_balance_payload()
    if only_kind is None:
        outcomes = [{"kind": k.value, "weight": 1.0} for k in RouletteOutcomeKind]
    else:
        outcomes = [
            {"kind": k.value, "weight": 1.0 if k is only_kind else 0.0} for k in RouletteOutcomeKind
        ]
    roulette = payload["roulette"]
    assert isinstance(roulette, dict)
    roulette["paid"] = {
        "cost_stars_single": cost_stars_single,
        "cost_stars_pack10": cost_stars_pack10,
        "pack10_spins": pack10_spins,
        "min_thickness_level": min_thickness_level,
        "outcomes": outcomes,
        "length_buckets": [
            {"name": "only", "min_cm": 1, "max_cm": 100, "weight": 1.0},
        ],
    }
    return payload


def _balance_with_paid_kind(
    kind: RouletteOutcomeKind,
    *,
    cost_stars_single: int = 1,
    cost_stars_pack10: int = 9,
    pack10_spins: int = 10,
    min_thickness_level: int = 1,
) -> FakeBalanceConfig:
    """`BalanceConfig` с `roulette.paid.outcomes`, где `weight=1.0` только у `kind`."""
    payload = _balance_payload_with_paid_block(
        only_kind=kind,
        cost_stars_single=cost_stars_single,
        cost_stars_pack10=cost_stars_pack10,
        pack10_spins=pack10_spins,
        min_thickness_level=min_thickness_level,
    )
    return FakeBalanceConfig(BalanceConfig.model_validate(payload))


def _build_use_case(
    *,
    balance: FakeBalanceConfig | None = None,
    random: IRandom | None = None,
    prize_pool: FakePrizePoolRepository | None = None,
) -> tuple[
    SpinPaidRoulette,
    FakePlayerRepository,
    FakeRouletteSpinRepository,
    FakePaymentLedger,
    FakeAuditLogger,
    FakeIdempotencyKey,
    FakeUnitOfWork,
    FakeClock,
    FakePrizePoolRepository,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    spins = FakeRouletteSpinRepository()
    payments = FakePaymentLedger()
    audit = FakeAuditLogger()
    idempotency = FakeIdempotencyKey()
    clock = FakeClock(_NOW)
    used_balance = balance or _balance_with_paid_kind(RouletteOutcomeKind.ITEM)
    used_random = random or _ScriptedRandom()
    used_prize_pool = prize_pool or FakePrizePoolRepository()
    length_granter = AddLength(
        uow=uow,
        players=players,
        anticheat=FakeAnticheatRepository(),
        audit=audit,
        balance=used_balance,
        clock=clock,
        idempotency=idempotency,
        admin_alerter=FakeAnticheatAdminAlerter(),
    )
    record_donation = RecordDonation(
        prize_pool_repository=used_prize_pool,
        audit_logger=audit,
        clock=clock,
    )
    use_case = SpinPaidRoulette(
        uow=uow,
        players=players,
        roulette_spins=spins,
        payments=payments,
        length_granter=length_granter,
        balance=used_balance,
        audit=audit,
        idempotency=idempotency,
        random=used_random,
        clock=clock,
        record_donation=record_donation,
    )
    return (
        use_case,
        players,
        spins,
        payments,
        audit,
        idempotency,
        uow,
        clock,
        used_prize_pool,
    )


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int = 42,
    length_cm: int = 500,
    thickness_level: int = 5,
) -> Player:
    """Засевает игрока. Толщина и длина выставляются через идиоматические `with_*`."""
    fresh = Player.new(tg_id=tg_id, username=Username(value="alice"), now=_NOW)
    persisted = await players.add(fresh)
    upgraded = persisted.with_thickness(Thickness(level=thickness_level), now=_NOW).with_length(
        Length(cm=length_cm), now=_NOW
    )
    return await players.save(upgraded)


def _key(value: str) -> IdempotencyKey:
    return IdempotencyKey(value)


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_first_call_marks_idempotency_and_writes_payment_and_spin(self) -> None:
        balance = _balance_with_paid_kind(RouletteOutcomeKind.ITEM)
        use_case, players, spins, payments, audit, idempotency, _, _, _ = _build_use_case(
            balance=balance,
        )
        await _seed_player(players)

        result = await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )

        assert result.idempotent is False
        assert result.spent_stars == 1
        assert result.pack is PaidRoulettePack.SINGLE
        assert len(result.outcomes) == 1
        assert result.outcomes[0] == RouletteOutcome(kind=RouletteOutcomeKind.ITEM)
        assert isinstance(result.payment, Payment)
        assert result.payment.amount_native == 1
        assert result.payment.currency is Currency.STARS

        assert len(payments.rows) == 1
        assert len(spins.rows) == 1
        assert await idempotency.is_seen(
            "roulette_paid:1|paid_roulette:1:tg-charge-001",
        )
        actions = [e.action for e in audit.entries]
        assert AuditAction.PAYMENT_RECORDED in actions
        assert AuditAction.ROULETTE_SPIN in actions

    @pytest.mark.asyncio
    async def test_replay_with_same_root_key_is_no_op(self) -> None:
        balance = _balance_with_paid_kind(RouletteOutcomeKind.ITEM)
        use_case, players, spins, payments, audit, _, uow, _, _ = _build_use_case(
            balance=balance,
        )
        await _seed_player(players)

        first = await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )
        assert first.idempotent is False
        payments_after_first = list(payments.rows)
        spins_after_first = list(spins.rows)
        audit_after_first = list(audit.entries)

        second = await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )
        assert second.idempotent is True
        assert second.spent_stars == 0
        assert second.outcomes == ()
        assert second.payment is None

        # Никаких новых вставок: ledger / spin / audit идентичны первому проходу.
        assert payments.rows == payments_after_first
        assert spins.rows == spins_after_first
        assert audit.entries == audit_after_first

        # Идемпотентный путь всё равно открыл/закрыл UoW.
        assert uow.commits == 2
        assert uow.rollbacks == 0


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class TestErrors:
    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        use_case, _, spins, payments, audit, idempotency, uow, _, _ = _build_use_case()

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(
                SpinPaidRouletteCommand(
                    player_id=999,
                    pack=PaidRoulettePack.SINGLE,
                    idempotency_key=_key("paid_roulette:999:tg-charge-001"),
                    provider_payment_id="tg-charge-001",
                ),
            )

        # Никаких побочных эффектов.
        assert payments.rows == []
        assert spins.rows == []
        assert audit.entries == []
        assert not await idempotency.is_seen(
            "roulette_paid:999|paid_roulette:999:tg-charge-001",
        )
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_thickness_gate_below_min_raises(self) -> None:
        balance = _balance_with_paid_kind(
            RouletteOutcomeKind.ITEM,
            min_thickness_level=3,
        )
        use_case, players, spins, payments, audit, idempotency, uow, _, _ = _build_use_case(
            balance=balance,
        )
        # min=3 → засеваем 1 → ниже гейта.
        player = await _seed_player(players, thickness_level=1)

        with pytest.raises(RouletteThicknessGateError) as exc_info:
            await use_case.execute(
                SpinPaidRouletteCommand(
                    player_id=1,
                    pack=PaidRoulettePack.SINGLE,
                    idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                    provider_payment_id="tg-charge-001",
                ),
            )

        err = exc_info.value
        assert err.player_id == 1
        assert err.thickness_level == 1
        assert err.required_level == 3

        # Никаких побочных эффектов.
        assert payments.rows == []
        assert spins.rows == []
        assert audit.entries == []
        assert not await idempotency.is_seen(
            "roulette_paid:1|paid_roulette:1:tg-charge-001",
        )
        snapshot = await players.get_by_id(player_id=1)
        assert snapshot is not None
        assert snapshot.length.cm == player.length.cm
        assert uow.commits == 0
        assert uow.rollbacks == 1


# --------------------------------------------------------------------------- #
# Charge через `IPaymentLedger`
# --------------------------------------------------------------------------- #


class TestCharge:
    @pytest.mark.asyncio
    async def test_single_pack_charges_cost_stars_single(self) -> None:
        balance = _balance_with_paid_kind(
            RouletteOutcomeKind.ITEM,
            cost_stars_single=1,
            cost_stars_pack10=9,
            pack10_spins=10,
        )
        use_case, players, _, payments, _, _, _, _, _ = _build_use_case(balance=balance)
        await _seed_player(players)

        result = await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )

        assert result.spent_stars == 1
        assert len(result.outcomes) == 1
        assert len(payments.rows) == 1
        payment = payments.rows[0]
        assert payment.amount_native == 1
        assert payment.currency is Currency.STARS
        assert payment.player_id == 1
        assert payment.status is PaymentStatus.CONFIRMED
        assert payment.confirmed_at == _NOW
        assert payment.provider_payment_id == "tg-charge-001"
        assert payment.idempotency_key == _key("paid_roulette:1:tg-charge-001")
        assert payment.payload["pack"] == "single"
        assert payment.payload["n_spins"] == "1"

    @pytest.mark.asyncio
    async def test_pack_10_charges_cost_stars_pack10_and_writes_n_spins(self) -> None:
        balance = _balance_with_paid_kind(
            RouletteOutcomeKind.ITEM,
            cost_stars_single=1,
            cost_stars_pack10=9,
            pack10_spins=10,
        )
        use_case, players, spins, payments, audit, _, _, _, _ = _build_use_case(balance=balance)
        await _seed_player(players)

        result = await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.PACK_10,
                idempotency_key=_key("paid_roulette:1:tg-charge-pack-001"),
                provider_payment_id="tg-charge-pack-001",
            ),
        )

        assert result.spent_stars == 9
        assert result.pack is PaidRoulettePack.PACK_10
        assert len(result.outcomes) == 10
        # 10-pack — одна транзакция в ledger-е.
        assert len(payments.rows) == 1
        payment = payments.rows[0]
        assert payment.amount_native == 9
        assert payment.payload["pack"] == "pack_10"
        assert payment.payload["n_spins"] == "10"
        # Ровно 10 строк в `roulette_spins`.
        assert len(spins.rows) == 10
        # И ровно 10 audit-записей `ROULETTE_SPIN` + 1 `PAYMENT_RECORDED`.
        spin_audits = [e for e in audit.entries if e.action is AuditAction.ROULETTE_SPIN]
        payment_audits = [e for e in audit.entries if e.action is AuditAction.PAYMENT_RECORDED]
        assert len(spin_audits) == 10
        assert len(payment_audits) == 1

    @pytest.mark.asyncio
    async def test_idempotency_conflict_on_different_amount_with_same_key(self) -> None:
        """Антифрод 4.1.4: тот же ключ — разная сумма → `IdempotencyConflictError`."""
        balance = _balance_with_paid_kind(RouletteOutcomeKind.ITEM)
        use_case, players, _, payments, _, _, _, _, _ = _build_use_case(balance=balance)
        await _seed_player(players)

        # Засеваем «фейковый» платёж 9 ⭐ под ключом, который use-case будет
        # пытаться использовать как 1 ⭐ для SINGLE-pack-а — антифрод-конфликт.
        existing = Payment(
            player_id=1,
            currency=Currency.STARS,
            amount_native=9,
            idempotency_key=_key("paid_roulette:1:tg-charge-collision"),
            status=PaymentStatus.CONFIRMED,
            created_at=_NOW,
            confirmed_at=_NOW,
            provider_payment_id="tg-charge-other",
        )
        payments.rows.append(existing)

        with pytest.raises(IdempotencyConflictError) as exc_info:
            await use_case.execute(
                SpinPaidRouletteCommand(
                    player_id=1,
                    pack=PaidRoulettePack.SINGLE,
                    idempotency_key=_key("paid_roulette:1:tg-charge-collision"),
                    provider_payment_id="tg-charge-001",
                ),
            )

        err = exc_info.value
        assert err.idempotency_key == "paid_roulette:1:tg-charge-collision"
        assert err.existing_amount_native == 9
        assert err.attempted_amount_native == 1


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


class TestAudit:
    @pytest.mark.asyncio
    async def test_payment_recorded_audit_payload(self) -> None:
        balance = _balance_with_paid_kind(RouletteOutcomeKind.ITEM)
        use_case, players, _, _, audit, _, _, _, _ = _build_use_case(balance=balance)
        await _seed_player(players, tg_id=99)

        await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )

        payment_entry = next(e for e in audit.entries if e.action is AuditAction.PAYMENT_RECORDED)
        assert payment_entry.target_kind == "payment"
        assert payment_entry.target_id == "paid_roulette:1:tg-charge-001"
        assert payment_entry.actor_id == 99
        assert payment_entry.source is AuditSource.STARS_PAYMENT
        assert payment_entry.before is None
        assert payment_entry.after == {
            "currency": "stars",
            "amount_native": 1,
            "status": "confirmed",
            "pack": "single",
            "n_spins": 1,
        }
        assert payment_entry.reason == "paid_roulette_charge"
        assert payment_entry.occurred_at == _NOW

    @pytest.mark.asyncio
    async def test_roulette_spin_audit_payload_for_length_outcome(self) -> None:
        balance = _balance_with_paid_kind(RouletteOutcomeKind.LENGTH)
        random = _ScriptedRandom(fixed_length_cm=42)
        use_case, players, _, _, audit, _, _, _, _ = _build_use_case(
            balance=balance,
            random=random,
        )
        await _seed_player(players, tg_id=99)

        await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )

        spin_entry = next(e for e in audit.entries if e.action is AuditAction.ROULETTE_SPIN)
        assert spin_entry.target_kind == "roulette_spin"
        assert spin_entry.target_id == "paid_roulette:1:tg-charge-001:0"
        assert spin_entry.actor_id == 99
        assert spin_entry.before is None
        assert spin_entry.after == {
            "kind": RouletteOutcomeKind.LENGTH.value,
            "length_cm": 42,
        }
        assert spin_entry.reason == "paid_roulette_spin"
        assert spin_entry.occurred_at == _NOW

    @pytest.mark.asyncio
    async def test_no_cost_length_grant_audit_entry_emitted(self) -> None:
        """Cost списан в Stars (не в см) → нет cost-side `LENGTH_GRANT` entry-а.

        Контр-пример к free-варианту, где free-cost пишется audit-записью
        `LENGTH_GRANT(source=ROULETTE_FREE_COST, delta_cm=-cost_cm)`.
        """
        balance = _balance_with_paid_kind(RouletteOutcomeKind.ITEM)
        use_case, players, _, _, audit, _, _, _, _ = _build_use_case(balance=balance)
        await _seed_player(players)

        await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )

        cost_entries = [
            e
            for e in audit.entries
            if e.action is AuditAction.LENGTH_GRANT and e.source is AuditSource.ROULETTE_FREE_COST
        ]
        assert cost_entries == []
        # И PAID-варианта `cost`-источника тоже нет в enum-е (см. `audit.py`).
        # ITEM-исход не даёт reward-grant-а — итого никаких `LENGTH_GRANT` записей.
        length_grants = [e for e in audit.entries if e.action is AuditAction.LENGTH_GRANT]
        assert length_grants == []


# --------------------------------------------------------------------------- #
# Outcome → reward
# --------------------------------------------------------------------------- #


class TestRewardGrant:
    @pytest.mark.asyncio
    async def test_length_outcome_grants_reward_via_length_granter(self) -> None:
        balance = _balance_with_paid_kind(RouletteOutcomeKind.LENGTH)
        random = _ScriptedRandom(fixed_length_cm=50)
        use_case, players, _, _, audit, _, _, _, _ = _build_use_case(
            balance=balance,
            random=random,
        )
        player = await _seed_player(players, length_cm=500)

        result = await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )

        assert result.outcomes[0] == RouletteOutcome(
            kind=RouletteOutcomeKind.LENGTH,
            length_cm=50,
        )

        # Длина — `+50 см` (cost списан в Stars, а не в см).
        snapshot = await players.get_by_id(player_id=1)
        assert snapshot is not None
        assert snapshot.length.cm == player.length.cm + 50

        # Audit reward-grant-а — `source=ROULETTE_PAID_REWARD`.
        reward_entry = next(
            e
            for e in audit.entries
            if e.action is AuditAction.LENGTH_GRANT and e.source is AuditSource.ROULETTE_PAID_REWARD
        )
        assert reward_entry.delta_cm == 50

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kind",
        [
            RouletteOutcomeKind.ITEM,
            RouletteOutcomeKind.SCROLL_REGULAR,
            RouletteOutcomeKind.SCROLL_BLESSED,
        ],
    )
    async def test_non_length_outcome_does_not_call_length_granter(
        self,
        kind: RouletteOutcomeKind,
    ) -> None:
        balance = _balance_with_paid_kind(kind)
        use_case, players, _, _, audit, _, _, _, _ = _build_use_case(balance=balance)
        player = await _seed_player(players, length_cm=500)

        result = await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )

        assert result.outcomes[0] == RouletteOutcome(kind=kind)
        # Длина не изменилась.
        snapshot = await players.get_by_id(player_id=1)
        assert snapshot is not None
        assert snapshot.length.cm == player.length.cm

        # Никаких `LENGTH_GRANT`-аудит-записей.
        length_grants = [e for e in audit.entries if e.action is AuditAction.LENGTH_GRANT]
        assert length_grants == []


# --------------------------------------------------------------------------- #
# Spin idempotency keys
# --------------------------------------------------------------------------- #


class TestSpinIdempotencyKeys:
    @pytest.mark.asyncio
    async def test_pack_10_writes_unique_idempotency_keys_per_spin(self) -> None:
        balance = _balance_with_paid_kind(
            RouletteOutcomeKind.ITEM,
            pack10_spins=10,
        )
        use_case, players, spins, _, _, _, _, _, _ = _build_use_case(balance=balance)
        await _seed_player(players)

        await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.PACK_10,
                idempotency_key=_key("paid_roulette:1:tg-charge-pack"),
                provider_payment_id="tg-charge-pack",
            ),
        )

        keys = [s.idempotency_key for s in spins.rows]
        assert keys == [f"paid_roulette:1:tg-charge-pack:{i}" for i in range(10)]


# --------------------------------------------------------------------------- #
# UoW transactional behaviour
# --------------------------------------------------------------------------- #


class TestUowTransactional:
    @pytest.mark.asyncio
    async def test_happy_path_commits_uow_once(self) -> None:
        balance = _balance_with_paid_kind(RouletteOutcomeKind.ITEM)
        use_case, players, _, _, _, _, uow, _, _ = _build_use_case(balance=balance)
        await _seed_player(players)

        await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )

        assert uow.commits == 1
        assert uow.rollbacks == 0


# --------------------------------------------------------------------------- #
# Prize pool donation (Спринт 4.1-B / Шаг B.5, ГДД §12.6)
# --------------------------------------------------------------------------- #


class TestPrizePoolDonation:
    """Step 5b 10-step flow-а: 10% от подтверждённого Stars-платежа → пул.

    Покрытие:
    * single-pack `1 ⭐` → донат `0` (`floor(1/10)`), `apply_increment` не
      вызван, audit `PRIZE_POOL_INCREMENT` не пишется.
    * 10-pack `9 ⭐` → донат `0` (`floor(9/10)`), `apply_increment` не вызван.
    * `cost_stars_single = 100` → донат `10`, пул вырос на 10 ⭐, audit
      `PRIZE_POOL_INCREMENT` записан с правильными `target_id` / `idempotency_key`.
    * idempotent-replay (тот же root-key) — `apply_increment` за весь
      flow вызван ровно один раз (на первой итерации).
    """

    @pytest.mark.asyncio
    async def test_single_pack_1_star_does_not_increment_pool(self) -> None:
        """`1 ⭐` < 10 → донат `0` → `apply_increment` не вызывается."""
        balance = _balance_with_paid_kind(
            RouletteOutcomeKind.ITEM,
            cost_stars_single=1,
        )
        use_case, players, _, _, audit, _, _, _, prize_pool = _build_use_case(
            balance=balance,
        )
        await _seed_player(players)

        await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )

        assert prize_pool.calls == []
        assert prize_pool.state.stars.value == 0
        # PRIZE_POOL_INCREMENT-audit-а не было.
        actions = [e.action for e in audit.entries]
        assert AuditAction.PRIZE_POOL_INCREMENT not in actions

    @pytest.mark.asyncio
    async def test_pack_10_9_stars_does_not_increment_pool(self) -> None:
        """`9 ⭐` < 10 → донат `0` → `apply_increment` не вызывается."""
        balance = _balance_with_paid_kind(
            RouletteOutcomeKind.ITEM,
            cost_stars_pack10=9,
            pack10_spins=10,
        )
        use_case, players, _, _, audit, _, _, _, prize_pool = _build_use_case(
            balance=balance,
        )
        await _seed_player(players)

        await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.PACK_10,
                idempotency_key=_key("paid_roulette:1:tg-charge-pack"),
                provider_payment_id="tg-charge-pack",
            ),
        )

        assert prize_pool.calls == []
        assert prize_pool.state.stars.value == 0
        actions = [e.action for e in audit.entries]
        assert AuditAction.PRIZE_POOL_INCREMENT not in actions

    @pytest.mark.asyncio
    async def test_single_pack_100_stars_increments_pool_by_10(self) -> None:
        """`100 ⭐` → донат `10 ⭐` → `apply_increment(STARS, 10)` + audit."""
        balance = _balance_with_paid_kind(
            RouletteOutcomeKind.ITEM,
            cost_stars_single=100,
        )
        use_case, players, _, _, audit, _, _, _, prize_pool = _build_use_case(
            balance=balance,
        )
        await _seed_player(players)

        await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.SINGLE,
                idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                provider_payment_id="tg-charge-001",
            ),
        )

        # Ровно один вызов apply_increment с правильными аргументами.
        assert prize_pool.calls == [
            FakePrizePoolApplyIncrementCall(
                currency=Currency.STARS,
                amount_native=10,
            )
        ]
        assert prize_pool.state.stars.value == 10
        assert prize_pool.state.ton_nano.value == 0
        assert prize_pool.state.usdt_decimal.value == 0

        # Audit: PRIZE_POOL_INCREMENT-запись с правильным target/idempotency.
        donation_entries = [
            e for e in audit.entries if e.action is AuditAction.PRIZE_POOL_INCREMENT
        ]
        assert len(donation_entries) == 1
        donation = donation_entries[0]
        assert donation.actor_id is None
        assert donation.target_kind == "prize_pool"
        assert donation.target_id == "paid_roulette:1:tg-charge-001:donation"
        assert donation.idempotency_key == "paid_roulette:1:tg-charge-001:prize_pool"
        assert donation.source is AuditSource.PRIZE_POOL_INCREMENT
        assert donation.after == {
            "currency": Currency.STARS.value,
            "amount_native": 10,
            "pool_after_native": 10,
        }

    @pytest.mark.asyncio
    async def test_pack_10_100_stars_increments_pool_by_10_once(self) -> None:
        """10-pack `100 ⭐` за всю транзакцию → ровно один `apply_increment(10)`.

        10-pack списывает `cost_stars_pack10` один раз (не 10 раз
        per-spin). Донат вычисляется от полного `cost_stars`, а не от
        per-spin ставки. Защищает от регрессии «N-кратный донат
        per-pack» (баг при наивной интеграции внутри спин-цикла).
        """
        balance = _balance_with_paid_kind(
            RouletteOutcomeKind.ITEM,
            cost_stars_single=20,
            cost_stars_pack10=100,
            pack10_spins=10,
        )
        use_case, players, _, _, _, _, _, _, prize_pool = _build_use_case(
            balance=balance,
        )
        await _seed_player(players)

        await use_case.execute(
            SpinPaidRouletteCommand(
                player_id=1,
                pack=PaidRoulettePack.PACK_10,
                idempotency_key=_key("paid_roulette:1:tg-charge-pack"),
                provider_payment_id="tg-charge-pack",
            ),
        )

        assert prize_pool.calls == [
            FakePrizePoolApplyIncrementCall(
                currency=Currency.STARS,
                amount_native=10,
            )
        ]
        assert prize_pool.state.stars.value == 10

    @pytest.mark.asyncio
    async def test_replay_does_not_double_donate(self) -> None:
        """Idempotent-replay → второй `execute` не делает повторный донат."""
        balance = _balance_with_paid_kind(
            RouletteOutcomeKind.ITEM,
            cost_stars_single=100,
        )
        use_case, players, _, _, _, _, _, _, prize_pool = _build_use_case(
            balance=balance,
        )
        await _seed_player(players)

        cmd = SpinPaidRouletteCommand(
            player_id=1,
            pack=PaidRoulettePack.SINGLE,
            idempotency_key=_key("paid_roulette:1:tg-charge-001"),
            provider_payment_id="tg-charge-001",
        )
        first = await use_case.execute(cmd)
        assert first.idempotent is False
        calls_after_first = list(prize_pool.calls)
        state_after_first = prize_pool.state

        second = await use_case.execute(cmd)
        assert second.idempotent is True
        # Никакого нового apply_increment, пул тот же.
        assert prize_pool.calls == calls_after_first
        assert prize_pool.state == state_after_first
        assert prize_pool.state.stars.value == 10

    @pytest.mark.asyncio
    async def test_thickness_gate_does_not_increment_pool(self) -> None:
        """Гейт-ошибка → UoW rollback → пул не изменился."""
        balance = _balance_with_paid_kind(
            RouletteOutcomeKind.ITEM,
            cost_stars_single=100,
            min_thickness_level=3,
        )
        use_case, players, _, _, _, _, _, _, prize_pool = _build_use_case(
            balance=balance,
        )
        await _seed_player(players, thickness_level=1)

        with pytest.raises(RouletteThicknessGateError):
            await use_case.execute(
                SpinPaidRouletteCommand(
                    player_id=1,
                    pack=PaidRoulettePack.SINGLE,
                    idempotency_key=_key("paid_roulette:1:tg-charge-001"),
                    provider_payment_id="tg-charge-001",
                ),
            )

        assert prize_pool.calls == []
        assert prize_pool.state.stars.value == 0
