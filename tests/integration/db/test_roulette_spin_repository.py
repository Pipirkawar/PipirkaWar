"""Integration-тесты `SqlAlchemyRouletteSpinRepository` (Спринт 3.5-B, B.4).

Покрытие:

* round-trip `record → SELECT` для всех 5 типов `RouletteOutcomeKind`
  (LENGTH с length_cm; ITEM/SCROLL_REGULAR/SCROLL_BLESSED/CRYPTO_LOT —
  с `length_cm IS NULL`);
* идемпотентность `record(...)` — повторный вызов с тем же
  `idempotency_key` не создаёт второй строки и не падает с
  `IntegrityError`;
* изоляция между игроками — `record(player1)` не виден через
  `last_free_spin_at(player2)`;
* `last_free_spin_at` — `None` для несуществующего игрока;
* `last_free_spin_at` — возвращает максимум `occurred_at` (а не
  первую/последнюю по `id`-порядку);
* DB-CHECK `kind ↔ length_cm` ловит прямой INSERT с rогон-инвариантом
  (last-line-of-defense).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from pipirik_wars.domain.balance.config import RouletteOutcomeKind
from pipirik_wars.domain.player import Player
from pipirik_wars.domain.roulette import RouletteOutcome, RouletteSpin
from pipirik_wars.infrastructure.db.models import RouletteSpinORM
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyPlayerRepository,
    SqlAlchemyRouletteSpinRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork

NOW = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)
EVEN_LATER = NOW + timedelta(minutes=10)


_NON_LENGTH_KINDS: list[RouletteOutcomeKind] = [
    RouletteOutcomeKind.ITEM,
    RouletteOutcomeKind.SCROLL_REGULAR,
    RouletteOutcomeKind.SCROLL_BLESSED,
    RouletteOutcomeKind.CRYPTO_LOT,
]


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


def _make_repo(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyRouletteSpinRepository:
    return SqlAlchemyRouletteSpinRepository(uow=uow)


class TestSqlAlchemyRouletteSpinRepositoryRoundTripLength:
    @pytest.mark.asyncio
    async def test_record_length_outcome_persists_kind_and_length_cm(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """LENGTH-исход → строка с `kind='length'` и заполненным `length_cm`."""
        player = await _seed_player(uow, tg_id=10001)
        assert player.id is not None
        repo = _make_repo(uow)

        spin = RouletteSpin(
            player_id=player.id,
            occurred_at=NOW,
            outcome=RouletteOutcome(
                kind=RouletteOutcomeKind.LENGTH,
                length_cm=42,
            ),
            idempotency_key="roulette_free:10001:msg-1",
        )
        async with uow:
            await repo.record(spin=spin)

        async with uow:
            stmt = select(
                RouletteSpinORM.kind,
                RouletteSpinORM.length_cm,
                RouletteSpinORM.idempotency_key,
            ).where(RouletteSpinORM.player_id == player.id)
            row = (await uow.session.execute(stmt)).one()
        assert row.kind == "length"
        assert row.length_cm == 42
        assert row.idempotency_key == "roulette_free:10001:msg-1"


class TestSqlAlchemyRouletteSpinRepositoryRoundTripNonLength:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", _NON_LENGTH_KINDS)
    async def test_record_non_length_outcome_persists_with_null_length_cm(
        self,
        uow: SqlAlchemyUnitOfWork,
        kind: RouletteOutcomeKind,
    ) -> None:
        """ITEM/SCROLL_*/CRYPTO_LOT → строка с правильным `kind` и `length_cm=NULL`."""
        player = await _seed_player(uow, tg_id=11000 + hash(kind.value) % 999)
        assert player.id is not None
        repo = _make_repo(uow)

        spin = RouletteSpin(
            player_id=player.id,
            occurred_at=NOW,
            outcome=RouletteOutcome(kind=kind, length_cm=None),
            idempotency_key=f"roulette_free:{player.id}:nonlen-{kind.value}",
        )
        async with uow:
            await repo.record(spin=spin)

        async with uow:
            stmt = select(
                RouletteSpinORM.kind,
                RouletteSpinORM.length_cm,
            ).where(RouletteSpinORM.player_id == player.id)
            row = (await uow.session.execute(stmt)).one()
        assert row.kind == kind.value
        assert row.length_cm is None


class TestSqlAlchemyRouletteSpinRepositoryIdempotency:
    @pytest.mark.asyncio
    async def test_record_twice_with_same_key_creates_one_row(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Повторный `record` с тем же `idempotency_key` → no-op (одна строка)."""
        player = await _seed_player(uow, tg_id=20001)
        assert player.id is not None
        repo = _make_repo(uow)

        spin = RouletteSpin(
            player_id=player.id,
            occurred_at=NOW,
            outcome=RouletteOutcome(
                kind=RouletteOutcomeKind.SCROLL_BLESSED,
                length_cm=None,
            ),
            idempotency_key="roulette_free:20001:dup",
        )
        async with uow:
            await repo.record(spin=spin)
        async with uow:
            await repo.record(spin=spin)

        async with uow:
            count_stmt = (
                select(func.count())
                .select_from(RouletteSpinORM)
                .where(
                    RouletteSpinORM.player_id == player.id,
                )
            )
            count = (await uow.session.execute(count_stmt)).scalar_one()
        assert count == 1

    @pytest.mark.asyncio
    async def test_record_with_same_key_but_different_payload_keeps_first(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """ON CONFLICT DO NOTHING → первая запись остаётся, вторая молча проглатывается."""
        player = await _seed_player(uow, tg_id=20002)
        assert player.id is not None
        repo = _make_repo(uow)

        first = RouletteSpin(
            player_id=player.id,
            occurred_at=NOW,
            outcome=RouletteOutcome(
                kind=RouletteOutcomeKind.LENGTH,
                length_cm=10,
            ),
            idempotency_key="roulette_free:20002:dup",
        )
        second = RouletteSpin(
            player_id=player.id,
            occurred_at=LATER,
            outcome=RouletteOutcome(
                kind=RouletteOutcomeKind.SCROLL_REGULAR,
                length_cm=None,
            ),
            idempotency_key="roulette_free:20002:dup",
        )
        async with uow:
            await repo.record(spin=first)
        async with uow:
            await repo.record(spin=second)

        async with uow:
            stmt = select(
                RouletteSpinORM.kind,
                RouletteSpinORM.length_cm,
            ).where(RouletteSpinORM.player_id == player.id)
            row = (await uow.session.execute(stmt)).one()
        assert row.kind == "length"
        assert row.length_cm == 10


class TestSqlAlchemyRouletteSpinRepositoryLastFreeSpinAt:
    @pytest.mark.asyncio
    async def test_last_free_spin_at_returns_none_for_player_without_spins(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`last_free_spin_at` возвращает `None`, если у игрока нет прокруток."""
        player = await _seed_player(uow, tg_id=30001)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            last = await repo.last_free_spin_at(player_id=player.id)
        assert last is None

    @pytest.mark.asyncio
    async def test_last_free_spin_at_returns_none_for_unknown_player(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`last_free_spin_at` возвращает `None` и для несуществующего player_id."""
        repo = _make_repo(uow)

        async with uow:
            last = await repo.last_free_spin_at(player_id=999_999)
        assert last is None

    @pytest.mark.asyncio
    async def test_last_free_spin_at_returns_max_occurred_at(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`last_free_spin_at` возвращает максимум `occurred_at` (не первую/последнюю по id)."""
        player = await _seed_player(uow, tg_id=30002)
        assert player.id is not None
        repo = _make_repo(uow)

        # Записываем три спина в порядке EVEN_LATER → NOW → LATER (id-порядок ≠ time-порядок).
        spins = [
            RouletteSpin(
                player_id=player.id,
                occurred_at=EVEN_LATER,
                outcome=RouletteOutcome(kind=RouletteOutcomeKind.ITEM),
                idempotency_key="roulette_free:30002:msg-3",
            ),
            RouletteSpin(
                player_id=player.id,
                occurred_at=NOW,
                outcome=RouletteOutcome(
                    kind=RouletteOutcomeKind.LENGTH,
                    length_cm=5,
                ),
                idempotency_key="roulette_free:30002:msg-1",
            ),
            RouletteSpin(
                player_id=player.id,
                occurred_at=LATER,
                outcome=RouletteOutcome(kind=RouletteOutcomeKind.SCROLL_REGULAR),
                idempotency_key="roulette_free:30002:msg-2",
            ),
        ]
        async with uow:
            for spin in spins:
                await repo.record(spin=spin)

        async with uow:
            last = await repo.last_free_spin_at(player_id=player.id)
        assert last is not None
        # SQLite сбрасывает TZ-инфу — сравниваем после нормализации до UTC.
        assert last.replace(tzinfo=UTC) == EVEN_LATER


class TestSqlAlchemyRouletteSpinRepositoryIsolation:
    @pytest.mark.asyncio
    async def test_record_one_player_does_not_affect_other(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Спин одного игрока не виден через `last_free_spin_at` другого."""
        p1 = await _seed_player(uow, tg_id=40001)
        p2 = await _seed_player(uow, tg_id=40002)
        assert p1.id is not None
        assert p2.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.record(
                spin=RouletteSpin(
                    player_id=p1.id,
                    occurred_at=NOW,
                    outcome=RouletteOutcome(
                        kind=RouletteOutcomeKind.LENGTH,
                        length_cm=7,
                    ),
                    idempotency_key="roulette_free:40001:msg-1",
                ),
            )

        async with uow:
            last_p1 = await repo.last_free_spin_at(player_id=p1.id)
            last_p2 = await repo.last_free_spin_at(player_id=p2.id)
        assert last_p1 is not None
        assert last_p2 is None

    @pytest.mark.asyncio
    async def test_idempotency_keys_are_globally_unique(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """`idempotency_key` уникален глобально (а не per-player)."""
        p1 = await _seed_player(uow, tg_id=40003)
        p2 = await _seed_player(uow, tg_id=40004)
        assert p1.id is not None
        assert p2.id is not None
        repo = _make_repo(uow)

        # Маловероятно в проде (use-case склеивает player_id в ключ),
        # но БД защищает от коллизий через UNIQUE-index. Если ключ
        # совпал — вторая запись молча проглатывается, как и при
        # одинаковом player_id.
        async with uow:
            await repo.record(
                spin=RouletteSpin(
                    player_id=p1.id,
                    occurred_at=NOW,
                    outcome=RouletteOutcome(kind=RouletteOutcomeKind.ITEM),
                    idempotency_key="shared-key",
                ),
            )
        async with uow:
            await repo.record(
                spin=RouletteSpin(
                    player_id=p2.id,
                    occurred_at=LATER,
                    outcome=RouletteOutcome(kind=RouletteOutcomeKind.ITEM),
                    idempotency_key="shared-key",
                ),
            )

        async with uow:
            count_stmt = select(func.count()).select_from(RouletteSpinORM)
            count = (await uow.session.execute(count_stmt)).scalar_one()
            owner_stmt = select(RouletteSpinORM.player_id).where(
                RouletteSpinORM.idempotency_key == "shared-key",
            )
            owner = (await uow.session.execute(owner_stmt)).scalar_one()
        assert count == 1
        assert owner == p1.id


class TestSqlAlchemyRouletteSpinRepositoryDbInvariants:
    """DB-инварианты — last-line-of-defense поверх доменного `__post_init__`."""

    @pytest.mark.asyncio
    async def test_db_check_rejects_length_kind_with_null_length_cm(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """CHECK ловит прямой INSERT `kind='length'` с `length_cm=NULL`."""
        player = await _seed_player(uow, tg_id=50001)
        assert player.id is not None

        with pytest.raises(IntegrityError):
            async with uow:
                bad = RouletteSpinORM(
                    player_id=player.id,
                    occurred_at=NOW,
                    kind="length",
                    length_cm=None,
                    idempotency_key="bad-1",
                )
                uow.session.add(bad)
                await uow.session.flush()

    @pytest.mark.asyncio
    async def test_db_check_rejects_non_length_kind_with_length_cm(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """CHECK ловит прямой INSERT `kind='item'` с заполненным `length_cm`."""
        player = await _seed_player(uow, tg_id=50002)
        assert player.id is not None

        with pytest.raises(IntegrityError):
            async with uow:
                bad = RouletteSpinORM(
                    player_id=player.id,
                    occurred_at=NOW,
                    kind="item",
                    length_cm=42,
                    idempotency_key="bad-2",
                )
                uow.session.add(bad)
                await uow.session.flush()

    @pytest.mark.asyncio
    async def test_db_check_rejects_unknown_kind(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """CHECK ловит прямой INSERT с неизвестным `kind`-значением."""
        player = await _seed_player(uow, tg_id=50003)
        assert player.id is not None

        with pytest.raises(IntegrityError):
            async with uow:
                bad = RouletteSpinORM(
                    player_id=player.id,
                    occurred_at=NOW,
                    kind="unknown_kind",
                    length_cm=None,
                    idempotency_key="bad-3",
                )
                uow.session.add(bad)
                await uow.session.flush()
