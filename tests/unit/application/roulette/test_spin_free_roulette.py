"""Unit-тесты use-case-а `SpinFreeRoulette` (Спринт 3.5-C, ГДД §12.4).

Покрытие 8-шагового flow:

* **Idempotency** (2 теста): первый вызов пишет mark; второй с тем же
  `idempotency_key` возвращает `idempotent=True` без побочных эффектов
  (ни списания, ни записи в `roulette_spins`, ни audit).
* **Player-not-found** (1) — `PlayerNotFoundError` при отсутствии игрока.
* **Thickness-гейт** (1) — `RouletteThicknessGateError` без побочных
  эффектов, если `player.thickness.level < min_thickness_level`.
* **Длиновой гейт** (1) — `InsufficientLengthForRouletteError` без
  побочных эффектов, если `length.cm < cost_cm`.
* **Happy path LENGTH-исхода** (1) — полный flow: `length.cm -=
  cost_cm`, audit `LENGTH_GRANT(source=ROULETTE_FREE_COST)`,
  `RouletteSpin` в event-log, audit `ROULETTE_SPIN`,
  `ILengthGranter.grant(source=ROULETTE_FREE_REWARD)` для приза.
* **Happy path не-LENGTH** (3 параметризованных: ITEM,
  SCROLL_REGULAR, SCROLL_BLESSED): cost списан, spin записан, audit
  `ROULETTE_SPIN` со ссылкой на kind, **НЕТ** второго audit
  `LENGTH_GRANT`-а от reward-grant-а.
* **Crypto-pool empty drains crypto_lot weight to length** (1) —
  use-case передаёт `active_lots=()` в picker, что в Спринте
  3.5-C сводится к перетеканию веса `CRYPTO_LOT → LENGTH` (см.
  `domain/roulette/services.py::_roll_kind`).
* **Audit-payload `ROULETTE_SPIN`** (1) — `target_kind`, `target_id`,
  `idempotency_key`, `after.kind`, `after.length_cm` (только для
  LENGTH).
* **`spin.idempotency_key` == `command.idempotency_key`** (1) —
  идемпотентный ключ комманды напрямую кладётся в event-log
  (DB-уровневая UNIQUE-дедупликация).
* **UoW commit/rollback** (1) — на gate-ошибке UoW откатывает
  транзакцию (`rollbacks==1, commits==0`). На happy-path —
  `commits==1, rollbacks==0`.

Итого: 13 тестов (включая 1 параметризованный с 3 случаями).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TypeVar

import pytest

from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.roulette import (
    SpinFreeRoulette,
    SpinFreeRouletteCommand,
)
from pipirik_wars.domain.balance.config import (
    BalanceConfig,
    RouletteOutcomeKind,
)
from pipirik_wars.domain.monetization.entities import PrizeLot, PrizeLotStatus
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    FeeBufferAmount,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    Thickness,
    Username,
)
from pipirik_wars.domain.roulette import RouletteOutcome
from pipirik_wars.domain.roulette.errors import (
    InsufficientLengthForRouletteError,
    RouletteThicknessGateError,
)
from pipirik_wars.domain.shared.ports import AuditAction, IRandom
from pipirik_wars.domain.shared.ports.audit import AuditSource
from tests.fakes import (
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeIdempotencyKey,
    FakePlayerRepository,
    FakePrizeLotRepository,
    FakeRouletteSpinRepository,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance, valid_balance_payload

_T = TypeVar("_T")
_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #


class _ScriptedRandom(IRandom):
    """Стаб `IRandom` для тестов use-case-а: форсит конкретный исход.

    Используется в паре с balance-конфигом, где у нужного исхода
    `weight=1.0`, остальные `0.0` (см. `_balance_with_only_kind`):
    `weighted_choice` валидирует `all weights > 0`, поэтому picker
    отфильтровывает нулевые до вызова. Так стаб видит только items
    с одним вариантом — выбор тривиален.

    Для LENGTH: `randint(low, high)` возвращает фиксированный
    `length_cm`. Для других методов `IRandom` (uniform, choice,
    deterministic_uint, shuffle) — `NotImplementedError`: use-case-у
    они не нужны.
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
        # У нас всегда ровно один вариант с положительным весом, picker
        # его уже отфильтровал — берём первый.
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


def _balance_with_only_kind(kind: RouletteOutcomeKind) -> FakeBalanceConfig:
    """`BalanceConfig` с `roulette.free.outcomes`, где `weight=1.0` только у `kind`."""
    payload = valid_balance_payload()
    payload["roulette"] = {
        **payload["roulette"],
        "free": {
            **payload["roulette"]["free"],
            "outcomes": [
                {"kind": k.value, "weight": 1.0 if k is kind else 0.0} for k in RouletteOutcomeKind
            ],
            # Один бакет с узким диапазоном, чтобы randint всегда мог
            # вернуть _ScriptedRandom._fixed_length_cm=50.
            "length_buckets": [
                {"name": "only", "min_cm": 1, "max_cm": 100, "weight": 1.0},
            ],
        },
    }
    return FakeBalanceConfig(BalanceConfig.model_validate(payload))


def _build_use_case(
    *,
    balance: FakeBalanceConfig | None = None,
    random: IRandom | None = None,
    prize_lots: FakePrizeLotRepository | None = None,
) -> tuple[
    SpinFreeRoulette,
    FakePlayerRepository,
    FakeRouletteSpinRepository,
    FakeAuditLogger,
    FakeIdempotencyKey,
    FakeUnitOfWork,
    FakeClock,
    FakePrizeLotRepository,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    spins = FakeRouletteSpinRepository()
    audit = FakeAuditLogger()
    idempotency = FakeIdempotencyKey()
    clock = FakeClock(_NOW)
    used_balance = balance or FakeBalanceConfig(build_valid_balance())
    used_random = random or _ScriptedRandom()
    used_prize_lots = prize_lots or FakePrizeLotRepository()
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
    use_case = SpinFreeRoulette(
        uow=uow,
        players=players,
        roulette_spins=spins,
        prize_lots=used_prize_lots,
        length_granter=length_granter,
        balance=used_balance,
        audit=audit,
        idempotency=idempotency,
        random=used_random,
        clock=clock,
    )
    return use_case, players, spins, audit, idempotency, uow, clock, used_prize_lots


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


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_first_call_marks_idempotency_and_writes_spin(self) -> None:
        balance = _balance_with_only_kind(RouletteOutcomeKind.ITEM)
        use_case, players, spins, audit, idempotency, _, _, _ = _build_use_case(balance=balance)
        await _seed_player(players)

        result = await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:42"),
        )

        assert result.idempotent is False
        assert result.spent_cm == 100
        assert result.outcome == RouletteOutcome(kind=RouletteOutcomeKind.ITEM)
        assert len(spins.rows) == 1
        # Проверяем, что mark действительно проставлен.
        assert await idempotency.is_seen("roulette_free:1|msg:42")
        # Audit должен содержать LENGTH_GRANT (cost) + ROULETTE_SPIN.
        actions = [e.action for e in audit.entries]
        assert AuditAction.LENGTH_GRANT in actions
        assert AuditAction.ROULETTE_SPIN in actions

    @pytest.mark.asyncio
    async def test_replay_with_same_key_is_no_op(self) -> None:
        balance = _balance_with_only_kind(RouletteOutcomeKind.ITEM)
        use_case, players, spins, audit, _, uow, _, _ = _build_use_case(balance=balance)
        player = await _seed_player(players)
        length_before_replay = player.length.cm

        # Первый — реальный вызов, заплатили cost и записали spin.
        first = await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:42"),
        )
        assert first.idempotent is False
        snapshot_after_first = await players.get_by_id(player_id=1)
        assert snapshot_after_first is not None
        length_after_first = snapshot_after_first.length.cm
        spins_after_first = list(spins.rows)
        audit_after_first = list(audit.entries)

        # Второй — повтор того же ключа, должен быть no-op.
        second = await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:42"),
        )
        assert second.idempotent is True
        assert second.spent_cm == 0
        assert second.outcome is None

        # Никакого нового списания, нового spin-а или audit-записи.
        snapshot_after_second = await players.get_by_id(player_id=1)
        assert snapshot_after_second is not None
        assert snapshot_after_second.length.cm == length_after_first
        assert spins.rows == spins_after_first
        assert audit.entries == audit_after_first

        # Идемпотентный путь всё равно открыл/закрыл UoW (commit без mutate).
        assert uow.commits == 2
        assert uow.rollbacks == 0
        # И длина изменилась только один раз — на cost первого вызова.
        assert length_after_first == length_before_replay - 100


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class TestErrors:
    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        use_case, _, spins, audit, idempotency, uow, _, _ = _build_use_case()

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(
                SpinFreeRouletteCommand(player_id=999, idempotency_key="msg:42"),
            )

        # Никаких побочных эффектов.
        assert spins.rows == []
        assert audit.entries == []
        assert not await idempotency.is_seen("roulette_free:999|msg:42")
        # UoW откатился.
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_thickness_gate_below_min_raises(self) -> None:
        use_case, players, spins, audit, idempotency, uow, _, _ = _build_use_case()
        # min_thickness_level=2 в дефолтном балансе → засеваем уровень 1.
        player = await _seed_player(players, thickness_level=1)

        with pytest.raises(RouletteThicknessGateError) as exc_info:
            await use_case.execute(
                SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:42"),
            )

        err = exc_info.value
        assert err.player_id == 1
        assert err.thickness_level == 1
        assert err.required_level == 2
        # Никаких побочных эффектов: spin/audit/idempotency пусты, длина та же.
        assert spins.rows == []
        assert audit.entries == []
        assert not await idempotency.is_seen("roulette_free:1|msg:42")
        snapshot = await players.get_by_id(player_id=1)
        assert snapshot is not None
        assert snapshot.length.cm == player.length.cm
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_insufficient_length_below_cost_raises(self) -> None:
        use_case, players, spins, audit, idempotency, uow, _, _ = _build_use_case()
        # cost_cm=100, длину ставим 50.
        player = await _seed_player(players, length_cm=50, thickness_level=5)

        with pytest.raises(InsufficientLengthForRouletteError) as exc_info:
            await use_case.execute(
                SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:42"),
            )

        err = exc_info.value
        assert err.player_id == 1
        assert err.length_cm == 50
        assert err.cost_cm == 100
        # Никаких побочных эффектов.
        assert spins.rows == []
        assert audit.entries == []
        assert not await idempotency.is_seen("roulette_free:1|msg:42")
        snapshot = await players.get_by_id(player_id=1)
        assert snapshot is not None
        assert snapshot.length.cm == player.length.cm
        assert uow.commits == 0
        assert uow.rollbacks == 1


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_length_outcome_deducts_cost_and_grants_reward(self) -> None:
        balance = _balance_with_only_kind(RouletteOutcomeKind.LENGTH)
        random = _ScriptedRandom(fixed_length_cm=50)
        use_case, players, spins, audit, _, uow, _, _ = _build_use_case(
            balance=balance, random=random
        )
        player = await _seed_player(players, length_cm=500)

        result = await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:42"),
        )

        assert result.idempotent is False
        assert result.spent_cm == 100
        assert result.outcome == RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=50)

        # Финальная длина: 500 - 100 (cost) + 50 (reward) = 450.
        snapshot = await players.get_by_id(player_id=1)
        assert snapshot is not None
        assert snapshot.length.cm == player.length.cm - 100 + 50

        # Один spin в event-log.
        assert len(spins.rows) == 1
        spin = spins.rows[0]
        assert spin.player_id == 1
        assert spin.outcome == RouletteOutcome(kind=RouletteOutcomeKind.LENGTH, length_cm=50)
        assert spin.idempotency_key == "msg:42"
        assert spin.occurred_at == _NOW

        # Audit: 3 записи — LENGTH_GRANT(cost), ROULETTE_SPIN, LENGTH_GRANT(reward).
        actions = [e.action for e in audit.entries]
        assert actions.count(AuditAction.LENGTH_GRANT) == 2
        assert actions.count(AuditAction.ROULETTE_SPIN) == 1

        cost_entry = next(
            e
            for e in audit.entries
            if e.action is AuditAction.LENGTH_GRANT and e.source is AuditSource.ROULETTE_FREE_COST
        )
        assert cost_entry.delta_cm == -100
        reward_entry = next(
            e
            for e in audit.entries
            if e.action is AuditAction.LENGTH_GRANT and e.source is AuditSource.ROULETTE_FREE_REWARD
        )
        assert reward_entry.delta_cm == 50

        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kind",
        [
            RouletteOutcomeKind.ITEM,
            RouletteOutcomeKind.SCROLL_REGULAR,
            RouletteOutcomeKind.SCROLL_BLESSED,
        ],
    )
    async def test_non_length_outcome_deducts_cost_and_skips_reward(
        self, kind: RouletteOutcomeKind
    ) -> None:
        balance = _balance_with_only_kind(kind)
        use_case, players, spins, audit, _, _, _, _ = _build_use_case(balance=balance)
        player = await _seed_player(players, length_cm=500)

        result = await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:42"),
        )

        assert result.idempotent is False
        assert result.spent_cm == 100
        assert result.outcome == RouletteOutcome(kind=kind)

        # Длина уменьшилась только на cost, никакого reward-grant-а.
        snapshot = await players.get_by_id(player_id=1)
        assert snapshot is not None
        assert snapshot.length.cm == player.length.cm - 100

        # Один spin в event-log.
        assert len(spins.rows) == 1
        assert spins.rows[0].outcome.kind is kind
        assert spins.rows[0].outcome.length_cm is None

        # Audit: ровно один LENGTH_GRANT (cost) + один ROULETTE_SPIN.
        actions = [e.action for e in audit.entries]
        assert actions.count(AuditAction.LENGTH_GRANT) == 1
        assert actions.count(AuditAction.ROULETTE_SPIN) == 1
        cost_entry = next(e for e in audit.entries if e.action is AuditAction.LENGTH_GRANT)
        assert cost_entry.source is AuditSource.ROULETTE_FREE_COST
        assert cost_entry.delta_cm == -100

    @pytest.mark.asyncio
    async def test_audit_payload_for_roulette_spin_entry(self) -> None:
        balance = _balance_with_only_kind(RouletteOutcomeKind.LENGTH)
        random = _ScriptedRandom(fixed_length_cm=42)
        use_case, players, _, audit, _, _, _, _ = _build_use_case(balance=balance, random=random)
        await _seed_player(players, tg_id=99, length_cm=500)

        await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:7"),
        )

        spin_entry = next(e for e in audit.entries if e.action is AuditAction.ROULETTE_SPIN)
        assert spin_entry.target_kind == "roulette_spin"
        assert spin_entry.target_id == "msg:7"
        assert spin_entry.idempotency_key == "roulette_free:1|msg:7"
        assert spin_entry.actor_id == 99  # tg_id игрока
        assert spin_entry.reason == "free_roulette_spin"
        assert spin_entry.before is None
        assert spin_entry.after == {
            "kind": RouletteOutcomeKind.LENGTH.value,
            "length_cm": 42,
        }
        assert spin_entry.occurred_at == _NOW

    @pytest.mark.asyncio
    async def test_spin_idempotency_key_matches_command(self) -> None:
        balance = _balance_with_only_kind(RouletteOutcomeKind.ITEM)
        use_case, players, spins, _, _, _, _, _ = _build_use_case(balance=balance)
        await _seed_player(players)

        await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:42"),
        )

        # Сырой `command.idempotency_key` (а не root_key с namespace)
        # кладётся в `RouletteSpin.idempotency_key` для DB-уровневой
        # UNIQUE-дедупликации.
        assert spins.rows[0].idempotency_key == "msg:42"


# --------------------------------------------------------------------------- #
# Crypto-pool drainage (3.5-C: всегда True)
# --------------------------------------------------------------------------- #


class TestCryptoPoolDrainage:
    @pytest.mark.asyncio
    async def test_use_case_drains_crypto_to_length_via_picker(self) -> None:
        """Пустой `FakePrizeLotRepository` → picker перевыронит CRYPTO_LOT → LENGTH.

        Конфиг ставим: `CRYPTO_LOT.weight=0.5`, `LENGTH.weight=0.5`.
        Use-case (C.6.b) вызывает `prize_lots.list_active(STARS)` —
        дефолтный `FakePrizeLotRepository` пуст, поэтому `active_lots=()`
        достигает picker-а, вес `CRYPTO_LOT` перетекает в `LENGTH`,
        итоговый вес `LENGTH = 1.0`. Стаб `_ScriptedRandom` с одним
        non-zero вариантом → всегда `LENGTH`. Если бы use-case передал
        непустой `active_lots`, picker оставил бы оба варианта в
        `weighted_choice`, и стаб вернул бы первый non-zero — но тогда
        первый был бы `CRYPTO_LOT` (порядок enum: LENGTH, ITEM,
        SCROLL_REGULAR, SCROLL_BLESSED, CRYPTO_LOT). Ниже мы пропускаем
        CRYPTO_LOT именно проверкой kind=LENGTH в outcome.
        """
        payload = valid_balance_payload()
        payload["roulette"] = {
            **payload["roulette"],
            "free": {
                **payload["roulette"]["free"],
                "outcomes": [
                    {"kind": "length", "weight": 0.5},
                    {"kind": "item", "weight": 0.0},
                    {"kind": "scroll_regular", "weight": 0.0},
                    {"kind": "scroll_blessed", "weight": 0.0},
                    {"kind": "crypto_lot", "weight": 0.5},
                ],
                "length_buckets": [
                    {"name": "only", "min_cm": 1, "max_cm": 100, "weight": 1.0},
                ],
            },
        }
        balance = FakeBalanceConfig(BalanceConfig.model_validate(payload))
        random = _ScriptedRandom(fixed_length_cm=50)
        use_case, players, _, _, _, _, _, _ = _build_use_case(balance=balance, random=random)
        await _seed_player(players, length_cm=500)

        result = await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:42"),
        )

        # Use-case передаёт active_lots=() → CRYPTO_LOT исключён,
        # остался только LENGTH с весом 1.0.
        assert result.outcome is not None
        assert result.outcome.kind is RouletteOutcomeKind.LENGTH
        assert result.outcome.length_cm == 50

    @pytest.mark.asyncio
    async def test_use_case_passes_active_lots_from_repository_to_picker(self) -> None:
        """C.6.b: непустой `FakePrizeLotRepository` → picker возвращает CRYPTO_LOT.

        В пуле один STARS-лот (id=1). Конфиг — `CRYPTO_LOT.weight=1.0`,
        остальные `0.0`; picker сразу пойдёт по ветке `_roll_crypto_lot`,
        выберет лот через `_ChoiceRandom.choice` и вернёт
        `RouletteOutcome.crypto_lot(lot_id=1)`. Резервирование лота
        (`update_status` + audit `PRIZE_LOT_RESERVED`) ещё **не**
        вызывается — это C.6.c; use-case на C.6.b пишет только
        `RouletteSpin.outcome` + audit `ROULETTE_SPIN.after.lot_id`.
        """
        balance = _balance_with_only_kind(RouletteOutcomeKind.CRYPTO_LOT)

        class _ChoiceRandom(_ScriptedRandom):
            def choice(self, items: Sequence[_T]) -> _T:
                if not items:
                    raise ValueError("choice from empty sequence")
                return items[0]

        random = _ChoiceRandom()
        prize_lots = FakePrizeLotRepository()
        stored = await prize_lots.add(
            lot=PrizeLot.freshly_generated(
                currency=Currency.STARS,
                amount_native=100,
                fee_buffer_native=FeeBufferAmount(0),
                created_at=_NOW,
            )
        )
        use_case, players, spins, audit, _, _, _, _ = _build_use_case(
            balance=balance, random=random, prize_lots=prize_lots
        )
        await _seed_player(players, length_cm=500)

        result = await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:42"),
        )

        assert result.outcome is not None
        assert result.outcome.kind is RouletteOutcomeKind.CRYPTO_LOT
        assert result.outcome.lot_id == stored.id
        # audit `ROULETTE_SPIN.after.lot_id` пробрасывается.
        spin_audit = next(e for e in audit.entries if e.action is AuditAction.ROULETTE_SPIN)
        assert spin_audit.after is not None
        assert spin_audit.after["lot_id"] == stored.id
        # C.6.c: резервирование вызвано один раз с (lot_id, RESERVED).
        assert prize_lots.update_status_calls == [
            (stored.id, PrizeLotStatus.RESERVED, None),
        ]
        # spin записан в event-log с CRYPTO_LOT-исходом.
        assert len(spins.rows) == 1

    @pytest.mark.asyncio
    async def test_crypto_lot_outcome_reserves_lot_and_writes_audit(self) -> None:
        """C.6.c: CRYPTO_LOT-исход → `update_status(lot_id, RESERVED)` + audit `PRIZE_LOT_RESERVED`.

        Конфиг: `CRYPTO_LOT.weight=1.0`. Пул: один STARS-лот (id=1).
        Picker возвращает `RouletteOutcome.crypto_lot(lot_id=1)`,
        use-case **в той же UoW** делает резервирование лота через
        `IPrizeLotRepository.update_status(lot_id=1, RESERVED)` и пишет
        audit `PRIZE_LOT_RESERVED` с full shape по C.6.a.
        """
        balance = _balance_with_only_kind(RouletteOutcomeKind.CRYPTO_LOT)

        class _ChoiceRandom(_ScriptedRandom):
            def choice(self, items: Sequence[_T]) -> _T:
                if not items:
                    raise ValueError("choice from empty sequence")
                return items[0]

        random = _ChoiceRandom()
        prize_lots = FakePrizeLotRepository()
        stored = await prize_lots.add(
            lot=PrizeLot.freshly_generated(
                currency=Currency.STARS,
                amount_native=500,
                fee_buffer_native=FeeBufferAmount(0),
                created_at=_NOW,
            )
        )
        use_case, players, _, audit, _, _, _, _ = _build_use_case(
            balance=balance, random=random, prize_lots=prize_lots
        )
        player = await _seed_player(players, length_cm=500)
        assert player.id is not None

        result = await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:99"),
        )

        # Резервирование выполнено.
        assert result.outcome is not None
        assert result.outcome.kind is RouletteOutcomeKind.CRYPTO_LOT
        assert prize_lots.update_status_calls == [
            (stored.id, PrizeLotStatus.RESERVED, None),
        ]
        reserved = await prize_lots.get_by_id(lot_id=stored.id or 0)
        assert reserved is not None
        assert reserved.status is PrizeLotStatus.RESERVED

        # audit `PRIZE_LOT_RESERVED` записан с правильным shape.
        reserve_audit = next(e for e in audit.entries if e.action is AuditAction.PRIZE_LOT_RESERVED)
        assert reserve_audit.actor_id == player.tg_id
        assert reserve_audit.target_kind == "prize_lot"
        assert reserve_audit.target_id == f"{stored.id}:reserved"
        assert reserve_audit.before is None
        assert reserve_audit.after == {
            "lot_id": stored.id,
            "currency": Currency.STARS.value,
            "amount_native": 500,
            "prev_status": PrizeLotStatus.ACTIVE.value,
            "reserved_at": _NOW.isoformat(),
            "player_id": player.id,
            "spin_kind": "free",
        }
        assert reserve_audit.reason == "free_roulette_reserve_lot"
        assert reserve_audit.idempotency_key == f"roulette_free:1|msg:99:reserve:{stored.id}"
        assert reserve_audit.source is AuditSource.PRIZE_LOT_RESERVED

    @pytest.mark.asyncio
    async def test_race_fallback_substitutes_length_outcome_when_update_status_raises(
        self,
    ) -> None:
        """C.6.d: `PrizeLotStatusTransitionError` из `update_status` → LengthGain-fallback.

        Сценарий: пул содержит 1 STARS-лот, picker возвращает CRYPTO_LOT,
        но между `list_active()` и `update_status()` другой игрок забронировал
        тот же лот первым. `FakePrizeLotRepository.raise_status_transition_on_update=True`
        имитирует это поведение. Use-case подменяет outcome на
        `pick_length_only_outcome(...)` (LENGTH-исход), audit
        `PRIZE_LOT_RESERVED` **не** пишется, `RouletteSpin.outcome.kind`
        == `LENGTH` + `LengthGranter.grant(...)` вызывается.
        """
        balance = _balance_with_only_kind(RouletteOutcomeKind.CRYPTO_LOT)

        class _RaceRandom(_ScriptedRandom):
            def choice(self, items: Sequence[_T]) -> _T:
                if not items:
                    raise ValueError("choice from empty sequence")
                return items[0]

        random = _RaceRandom(fixed_length_cm=42)
        prize_lots = FakePrizeLotRepository(raise_status_transition_on_update=True)
        await prize_lots.add(
            lot=PrizeLot.freshly_generated(
                currency=Currency.STARS,
                amount_native=500,
                fee_buffer_native=FeeBufferAmount(0),
                created_at=_NOW,
            )
        )
        use_case, players, spins, audit, _, _, _, _ = _build_use_case(
            balance=balance, random=random, prize_lots=prize_lots
        )
        player = await _seed_player(players, length_cm=500)

        result = await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:race"),
        )

        # Outcome подменён на LENGTH с fallback_cm.
        assert result.outcome is not None
        assert result.outcome.kind is RouletteOutcomeKind.LENGTH
        assert result.outcome.length_cm == 42
        assert result.outcome.lot_id is None

        # update_status был вызван ровно один раз (без retry-loop).
        assert len(prize_lots.update_status_calls) == 1

        # audit `PRIZE_LOT_RESERVED` **не** записан (резервирование провалилось).
        actions = [e.action for e in audit.entries]
        assert AuditAction.PRIZE_LOT_RESERVED not in actions

        # spin записан в event-log с LENGTH-исходом.
        assert len(spins.rows) == 1
        assert spins.rows[0].outcome.kind is RouletteOutcomeKind.LENGTH

        # Игрок получил длину через LengthGranter (player.length увеличен на 42).
        updated = await players.get_by_id(player_id=player.id or 0)
        assert updated is not None
        assert updated.length.cm == 500 - 100 + 42  # cost - reward


# --------------------------------------------------------------------------- #
# UoW transactional behaviour
# --------------------------------------------------------------------------- #


class TestUowTransactional:
    @pytest.mark.asyncio
    async def test_happy_path_commits_uow_once(self) -> None:
        balance = _balance_with_only_kind(RouletteOutcomeKind.ITEM)
        use_case, players, _, _, _, uow, _, _ = _build_use_case(balance=balance)
        await _seed_player(players)

        await use_case.execute(
            SpinFreeRouletteCommand(player_id=1, idempotency_key="msg:42"),
        )

        assert uow.commits == 1
        assert uow.rollbacks == 0
