"""Integration-тесты `SpinFreeRoulette` use-case через realDB (Спринт 3.5-C, C.3).

Сценарии:

* round-trip happy path LENGTH-исход — `users.length_cm` пересчитан на
  `-100 + reward`, в `roulette_spins` ровно одна строка с
  `kind='length'` и `length_cm=reward`, в `audit_log` три записи
  (`LENGTH_GRANT(source=roulette_free_cost)` + `ROULETTE_SPIN` +
  `LENGTH_GRANT(source=roulette_free_reward)`);
* round-trip happy path не-LENGTH-исход (параметризованный по
  `ITEM/SCROLL_REGULAR/SCROLL_BLESSED`) — `users.length_cm` падает
  ровно на `100`, `roulette_spins` содержит одну строку с правильным
  `kind` и `length_cm=NULL`, `audit_log` — две записи (cost +
  ROULETTE_SPIN, reward отсутствует);
* идемпотентный replay: повторный вызов с тем же `idempotency_key` →
  no-op (`length_cm` не меняется второй раз, в `roulette_spins`
  остаётся одна строка, в `audit_log` — три записи как после первого
  вызова);
* thickness-гейт: игрок с `thickness_level=1` (стартовое значение,
  ниже `min_thickness_level=2`) → `RouletteThicknessGateError`,
  никаких DB-побочных эффектов (`length_cm` не изменился, ноль строк
  в `roulette_spins` и `audit_log`);
* insufficient-length: игрок с `length_cm=50 < cost_cm=100` →
  `InsufficientLengthForRouletteError`, никаких DB-побочных эффектов.

Wiring «продакшн-как-в-`bot/main.py`»: настоящие SqlAlchemy-репо
(`SqlAlchemyPlayerRepository`, `SqlAlchemyRouletteSpinRepository`,
`SqlAlchemyAnticheatRepository`), настоящие сервисы
(`SqlAlchemyAuditLogger`, `SqlAlchemyIdempotencyService`), реальный
`AddLength` length-granter. Только `IAnticheatAdminAlerter` —
`FakeAnticheatAdminAlerter` (production: Telegram-side-effect).
RNG — детерминированный `_ScriptedRandom`, который возвращает заранее
выбранные исходы (повторяет приём из unit-тестов use-case-а).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TypeVar

import pytest
from sqlalchemy import func, select

from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.roulette import (
    SpinFreeRoulette,
    SpinFreeRouletteCommand,
)
from pipirik_wars.domain.balance.config import BalanceConfig, RouletteOutcomeKind
from pipirik_wars.domain.player import Length, Player, Thickness
from pipirik_wars.domain.roulette.errors import (
    InsufficientLengthForRouletteError,
    RouletteThicknessGateError,
)
from pipirik_wars.domain.shared.ports import IRandom
from pipirik_wars.domain.shared.ports.audit import AuditAction, AuditSource
from pipirik_wars.infrastructure.db.models import (
    AuditLogORM,
    RouletteSpinORM,
    UserORM,
)
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyAnticheatRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemyPrizeLotRepository,
    SqlAlchemyRouletteSpinRepository,
)
from pipirik_wars.infrastructure.db.services import (
    SqlAlchemyAuditLogger,
    SqlAlchemyIdempotencyService,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from tests.fakes import FakeAnticheatAdminAlerter, FakeBalanceConfig, FakeClock
from tests.unit.domain.balance.factories import valid_balance_payload

_T = TypeVar("_T")
NOW = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)

_NON_LENGTH_KINDS: list[RouletteOutcomeKind] = [
    RouletteOutcomeKind.ITEM,
    RouletteOutcomeKind.SCROLL_REGULAR,
    RouletteOutcomeKind.SCROLL_BLESSED,
]
"""CRYPTO_LOT исключён: при `crypto_pool_empty=True` его вес перетекает
в LENGTH (см. unit-тест `TestCryptoPoolDrainage`); чтобы получить
не-LENGTH исход, балансу подсовывается соответствующий `kind` через
`_balance_with_only_kind`. Раздельно тестировать CRYPTO_LOT при
пустом пуле смысла нет — он эквивалентен LENGTH-сценарию."""


# ────────────────────────────── helpers ──────────────────────────────


class _ScriptedRandom(IRandom):
    """Детерминированный IRandom для integration-тестов.

    Контракт идентичен unit-тестам (`tests/unit/application/roulette/
    test_spin_free_roulette.py::_ScriptedRandom`):

    - `randint(low, high)` возвращает `_fixed_length_cm` (для
      length-bucket-а — единственный bucket в `_balance_with_only_kind`
      имеет диапазон `[1..100]`, в который 50 заведомо попадает);
    - `weighted_choice(items, weights)` возвращает первый элемент
      (`_balance_with_only_kind` оставляет ровно один outcome-kind с
      положительным весом, так что picker вернёт его).
    """

    __slots__ = ("_fixed_length_cm",)

    def __init__(self, *, fixed_length_cm: int = 50) -> None:
        self._fixed_length_cm = fixed_length_cm

    def randint(self, low: int, high: int) -> int:
        if not low <= self._fixed_length_cm <= high:
            raise ValueError(
                f"_ScriptedRandom: fixed_length_cm={self._fixed_length_cm} out of [{low},{high}]",
            )
        return self._fixed_length_cm

    def weighted_choice(self, items: Sequence[_T], weights: Sequence[int]) -> _T:
        return items[0]

    def uniform(self, low: float, high: float) -> float:
        raise AssertionError("_ScriptedRandom.uniform not expected")

    def choice(self, items: Sequence[_T]) -> _T:
        raise AssertionError("_ScriptedRandom.choice not expected")

    def deterministic_uint(self, seed: str, modulo: int) -> int:
        raise AssertionError("_ScriptedRandom.deterministic_uint not expected")

    def shuffle(self, items: Sequence[_T]) -> tuple[_T, ...]:
        raise AssertionError("_ScriptedRandom.shuffle not expected")


def _balance_with_only_kind(kind: RouletteOutcomeKind) -> FakeBalanceConfig:
    """Билдер `BalanceConfig`-а с единственным outcome-kind в `roulette.free`.

    Все остальные outcome-веса = 0; `length_buckets` — один с
    диапазоном `[1, 100]`. Это даёт детерминированный pick: любой
    `weighted_choice` после фильтрации zero-weights отдаёт `kind`.
    Идентичный приём в unit-тесте use-case-а — для согласованности
    integration- и unit-уровней.
    """
    payload = valid_balance_payload()
    payload["roulette"] = {
        **payload["roulette"],
        "free": {
            **payload["roulette"]["free"],
            "outcomes": [
                {"kind": k.value, "weight": 1.0 if k is kind else 0.0} for k in RouletteOutcomeKind
            ],
            "length_buckets": [
                {"name": "only", "min_cm": 1, "max_cm": 100, "weight": 1.0},
            ],
        },
    }
    return FakeBalanceConfig(BalanceConfig.model_validate(payload))


async def _seed_player_with_thickness(
    uow: SqlAlchemyUnitOfWork,
    *,
    tg_id: int,
    length_cm: int,
    thickness_level: int = 2,
) -> Player:
    """Положить игрока в БД с заданными `length_cm` / `thickness_level`."""
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        created = await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))
        upd = created.with_length(Length(cm=length_cm), now=NOW)
        if thickness_level != upd.thickness.level:
            upd = upd.with_thickness(Thickness(level=thickness_level), now=NOW)
        return await repo.save(upd)


def _build_use_case(
    uow: SqlAlchemyUnitOfWork,
    *,
    balance: FakeBalanceConfig,
    random: IRandom,
) -> SpinFreeRoulette:
    """Production-like wiring: настоящие SqlAlchemy-репо + AddLength."""
    clock = FakeClock(NOW)
    audit = SqlAlchemyAuditLogger(uow=uow)
    idempotency = SqlAlchemyIdempotencyService(uow=uow)
    players = SqlAlchemyPlayerRepository(uow=uow)
    length_granter = AddLength(
        uow=uow,
        players=players,
        anticheat=SqlAlchemyAnticheatRepository(uow=uow),
        audit=audit,
        balance=balance,
        clock=clock,
        idempotency=idempotency,
        admin_alerter=FakeAnticheatAdminAlerter(),
    )
    return SpinFreeRoulette(
        uow=uow,
        players=players,
        roulette_spins=SqlAlchemyRouletteSpinRepository(uow=uow),
        prize_lots=SqlAlchemyPrizeLotRepository(uow=uow),
        length_granter=length_granter,
        balance=balance,
        audit=audit,
        idempotency=idempotency,
        random=random,
        clock=clock,
    )


async def _length_cm(uow: SqlAlchemyUnitOfWork, *, player_id: int) -> int:
    async with uow:
        stmt = select(UserORM.length_cm).where(UserORM.id == player_id)
        return (await uow.session.execute(stmt)).scalar_one()


async def _count_spins(uow: SqlAlchemyUnitOfWork, *, player_id: int) -> int:
    async with uow:
        stmt = (
            select(func.count())
            .select_from(RouletteSpinORM)
            .where(RouletteSpinORM.player_id == player_id)
        )
        return (await uow.session.execute(stmt)).scalar_one()


async def _audit_actions(
    uow: SqlAlchemyUnitOfWork,
    *,
    actor_id: int,
) -> list[AuditLogORM]:
    async with uow:
        stmt = select(AuditLogORM).where(AuditLogORM.actor_id == actor_id).order_by(AuditLogORM.id)
        return list((await uow.session.execute(stmt)).scalars().all())


# ────────────────────────────── tests ──────────────────────────────


class TestSpinFreeRouletteRoundTripLength:
    @pytest.mark.asyncio
    async def test_length_outcome_grants_reward(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """LENGTH-исход: `length_cm` = -100 + reward, 1 строка в `roulette_spins`,
        3 audit-записи (cost + ROULETTE_SPIN + reward)."""
        player = await _seed_player_with_thickness(
            uow,
            tg_id=70001,
            length_cm=500,
        )
        assert player.id is not None

        balance = _balance_with_only_kind(RouletteOutcomeKind.LENGTH)
        random = _ScriptedRandom(fixed_length_cm=50)
        use_case = _build_use_case(uow, balance=balance, random=random)

        result = await use_case.execute(
            SpinFreeRouletteCommand(player_id=player.id, idempotency_key="msg:1"),
        )

        assert result.idempotent is False
        assert result.spent_cm == 100
        assert result.outcome is not None
        assert result.outcome.kind is RouletteOutcomeKind.LENGTH
        assert result.outcome.length_cm == 50

        # users.length_cm = 500 - 100 + 50 = 450
        assert await _length_cm(uow, player_id=player.id) == 450

        # roulette_spins: одна строка с правильным kind и length_cm
        assert await _count_spins(uow, player_id=player.id) == 1
        async with uow:
            spin_stmt = select(
                RouletteSpinORM.kind,
                RouletteSpinORM.length_cm,
                RouletteSpinORM.idempotency_key,
            ).where(RouletteSpinORM.player_id == player.id)
            spin_row = (await uow.session.execute(spin_stmt)).one()
        assert spin_row.kind == "length"
        assert spin_row.length_cm == 50
        assert spin_row.idempotency_key == "msg:1"

        # audit_log: три записи в правильном порядке.
        entries = await _audit_actions(uow, actor_id=player.tg_id)
        actions = [e.action for e in entries]
        sources = [e.source for e in entries]
        assert actions == [
            AuditAction.LENGTH_GRANT.value,
            AuditAction.ROULETTE_SPIN.value,
            AuditAction.LENGTH_GRANT.value,
        ]
        assert sources == [
            AuditSource.ROULETTE_FREE_COST.value,
            AuditSource.UNKNOWN.value,  # ROULETTE_SPIN — без явного source
            AuditSource.ROULETTE_FREE_REWARD.value,
        ]
        # cost-запись: delta_cm=-100, before/after — 500/400
        cost_entry = entries[0]
        assert cost_entry.delta_cm == -100
        assert cost_entry.before == {"length_cm": 500}
        assert cost_entry.after == {"length_cm": 400}
        # reward-запись: delta_cm=+50, before/after — 400/450
        reward_entry = entries[2]
        assert reward_entry.delta_cm == 50
        assert reward_entry.before == {"length_cm": 400}
        assert reward_entry.after == {"length_cm": 450}


class TestSpinFreeRouletteRoundTripNonLength:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", _NON_LENGTH_KINDS)
    async def test_non_length_outcome_only_deducts_cost(
        self,
        uow: SqlAlchemyUnitOfWork,
        kind: RouletteOutcomeKind,
    ) -> None:
        """ITEM/SCROLL_REGULAR/SCROLL_BLESSED: `length_cm -= 100`, 1 строка в
        `roulette_spins` с `length_cm=NULL`, 2 audit-записи (cost +
        ROULETTE_SPIN, reward отсутствует)."""
        player = await _seed_player_with_thickness(
            uow,
            tg_id=71000 + abs(hash(kind.value)) % 999,
            length_cm=300,
        )
        assert player.id is not None

        balance = _balance_with_only_kind(kind)
        random = _ScriptedRandom(fixed_length_cm=50)
        use_case = _build_use_case(uow, balance=balance, random=random)

        result = await use_case.execute(
            SpinFreeRouletteCommand(player_id=player.id, idempotency_key=f"non-len:{kind.value}"),
        )

        assert result.idempotent is False
        assert result.spent_cm == 100
        assert result.outcome is not None
        assert result.outcome.kind is kind
        assert result.outcome.length_cm is None

        # users.length_cm = 300 - 100 = 200 (reward не выдаётся для не-LENGTH)
        assert await _length_cm(uow, player_id=player.id) == 200

        # roulette_spins: одна строка с правильным kind и length_cm=NULL
        async with uow:
            spin_stmt = select(
                RouletteSpinORM.kind,
                RouletteSpinORM.length_cm,
            ).where(RouletteSpinORM.player_id == player.id)
            spin_row = (await uow.session.execute(spin_stmt)).one()
        assert spin_row.kind == kind.value
        assert spin_row.length_cm is None

        # audit_log: ровно две записи (cost LENGTH_GRANT + ROULETTE_SPIN).
        entries = await _audit_actions(uow, actor_id=player.tg_id)
        actions = [e.action for e in entries]
        assert actions == [
            AuditAction.LENGTH_GRANT.value,
            AuditAction.ROULETTE_SPIN.value,
        ]
        # Reward-LENGTH_GRANT-а быть не должно.
        assert sum(1 for e in entries if e.source == AuditSource.ROULETTE_FREE_REWARD.value) == 0


class TestSpinFreeRouletteIdempotency:
    @pytest.mark.asyncio
    async def test_replay_with_same_key_is_no_op(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Повторный вызов с тем же `idempotency_key` → no-op:
        `length_cm` не меняется, в `roulette_spins` одна строка,
        в `audit_log` три записи как после первого вызова."""
        player = await _seed_player_with_thickness(
            uow,
            tg_id=70002,
            length_cm=500,
        )
        assert player.id is not None

        balance = _balance_with_only_kind(RouletteOutcomeKind.LENGTH)
        random = _ScriptedRandom(fixed_length_cm=50)
        use_case = _build_use_case(uow, balance=balance, random=random)

        first = await use_case.execute(
            SpinFreeRouletteCommand(player_id=player.id, idempotency_key="dup:1"),
        )
        assert first.idempotent is False

        # Слепок состояния после первого вызова.
        length_after_first = await _length_cm(uow, player_id=player.id)
        spins_after_first = await _count_spins(uow, player_id=player.id)
        audit_after_first = len(await _audit_actions(uow, actor_id=player.tg_id))

        second = await use_case.execute(
            SpinFreeRouletteCommand(player_id=player.id, idempotency_key="dup:1"),
        )
        assert second.idempotent is True
        assert second.spent_cm == 0
        assert second.outcome is None

        # Никаких новых side-effect-ов.
        assert await _length_cm(uow, player_id=player.id) == length_after_first
        assert await _count_spins(uow, player_id=player.id) == spins_after_first
        assert len(await _audit_actions(uow, actor_id=player.tg_id)) == audit_after_first


class TestSpinFreeRouletteGates:
    @pytest.mark.asyncio
    async def test_thickness_gate_below_min_raises_no_db_writes(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`thickness_level=1 < min_thickness_level=2` →
        `RouletteThicknessGateError` без DB-побочных эффектов."""
        player = await _seed_player_with_thickness(
            uow,
            tg_id=70003,
            length_cm=500,
            thickness_level=1,
        )
        assert player.id is not None
        # Снимок DB до вызова.
        length_before = await _length_cm(uow, player_id=player.id)
        spins_before = await _count_spins(uow, player_id=player.id)
        audit_before = len(await _audit_actions(uow, actor_id=player.tg_id))

        balance = _balance_with_only_kind(RouletteOutcomeKind.LENGTH)
        random = _ScriptedRandom(fixed_length_cm=50)
        use_case = _build_use_case(uow, balance=balance, random=random)

        with pytest.raises(RouletteThicknessGateError) as exc:
            await use_case.execute(
                SpinFreeRouletteCommand(player_id=player.id, idempotency_key="gate"),
            )
        assert exc.value.thickness_level == 1
        assert exc.value.required_level == 2

        # Никаких изменений в БД (UoW откатил всё).
        assert await _length_cm(uow, player_id=player.id) == length_before
        assert await _count_spins(uow, player_id=player.id) == spins_before
        assert len(await _audit_actions(uow, actor_id=player.tg_id)) == audit_before

    @pytest.mark.asyncio
    async def test_insufficient_length_raises_no_db_writes(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`length_cm=50 < cost_cm=100` →
        `InsufficientLengthForRouletteError` без DB-побочных эффектов."""
        player = await _seed_player_with_thickness(
            uow,
            tg_id=70004,
            length_cm=50,
        )
        assert player.id is not None
        length_before = await _length_cm(uow, player_id=player.id)
        spins_before = await _count_spins(uow, player_id=player.id)
        audit_before = len(await _audit_actions(uow, actor_id=player.tg_id))

        balance = _balance_with_only_kind(RouletteOutcomeKind.LENGTH)
        random = _ScriptedRandom(fixed_length_cm=50)
        use_case = _build_use_case(uow, balance=balance, random=random)

        with pytest.raises(InsufficientLengthForRouletteError) as exc:
            await use_case.execute(
                SpinFreeRouletteCommand(player_id=player.id, idempotency_key="poor"),
            )
        assert exc.value.length_cm == 50
        assert exc.value.cost_cm == 100

        # Никаких изменений в БД.
        assert await _length_cm(uow, player_id=player.id) == length_before
        assert await _count_spins(uow, player_id=player.id) == spins_before
        assert len(await _audit_actions(uow, actor_id=player.tg_id)) == audit_before
