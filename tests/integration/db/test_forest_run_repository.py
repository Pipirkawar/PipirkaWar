"""Integration-тесты `SqlAlchemyForestRunRepository`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.forest import (
    ForestRun,
    ForestRunStatus,
    Item,
    ItemDrop,
    Name,
    NameDrop,
    NoDrop,
    OutcomeBranch,
    Rarity,
    Slot,
)
from pipirik_wars.domain.forest.entities import ForestRunOutcome
from pipirik_wars.domain.player import Player
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyForestRunRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError
from tests.fakes import FakeBalanceConfig
from tests.unit.domain.balance.factories import build_valid_balance

NOW = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)


def _outcome_no_drop() -> ForestRunOutcome:
    return ForestRunOutcome(
        branch=OutcomeBranch(name="scarce", length_cm=3),
        length_cm=3,
        drop=NoDrop(),
    )


def _outcome_with_item() -> ForestRunOutcome:
    return ForestRunOutcome(
        branch=OutcomeBranch(name="normal", length_cm=12),
        length_cm=12,
        drop=ItemDrop(
            item=Item(
                id="item.hat.test_1",
                slot=Slot.HAT,
                display_name="Тестовый hat #1",
                rarity=Rarity.COMMON,
            )
        ),
    )


def _outcome_with_name() -> ForestRunOutcome:
    return ForestRunOutcome(
        branch=OutcomeBranch(name="abundant", length_cm=18),
        length_cm=18,
        drop=NameDrop(name=Name(value="ИмяТест-01")),
    )


def _build_run(
    *,
    player_id: int,
    outcome: ForestRunOutcome,
    started_at: datetime = NOW,
    cooldown: timedelta = timedelta(minutes=10),
) -> ForestRun:
    return ForestRun.starting(
        player_id=player_id,
        outcome=outcome,
        started_at=started_at,
        ends_at=started_at + cooldown,
    )


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


def _make_repo(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyForestRunRepository:
    return SqlAlchemyForestRunRepository(
        uow=uow,
        balance=FakeBalanceConfig(build_valid_balance()),
    )


class TestSqlAlchemyForestRunRepository:
    @pytest.mark.asyncio
    async def test_add_assigns_id_and_status_in_progress(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            stored = await repo.add(_build_run(player_id=player.id, outcome=_outcome_no_drop()))

        assert stored.id is not None
        assert stored.status is ForestRunStatus.IN_PROGRESS
        assert stored.player_id == player.id
        assert stored.branch_name == "scarce"
        assert stored.length_delta_cm == 3
        assert isinstance(stored.drop, NoDrop)
        assert stored.finished_at is None

    @pytest.mark.asyncio
    async def test_add_with_preset_id_rejected(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            stored = await repo.add(_build_run(player_id=player.id, outcome=_outcome_no_drop()))

        with pytest.raises(DomainIntegrityError, match="pre-set id"):
            async with uow:
                await repo.add(stored)

    @pytest.mark.asyncio
    async def test_partial_unique_blocks_second_active_run(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            await repo.add(_build_run(player_id=player.id, outcome=_outcome_no_drop()))

        with pytest.raises(DomainIntegrityError):
            async with uow:
                await repo.add(_build_run(player_id=player.id, outcome=_outcome_with_item()))

    @pytest.mark.asyncio
    async def test_after_finish_can_add_new_active(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            stored = await repo.add(_build_run(player_id=player.id, outcome=_outcome_no_drop()))

        async with uow:
            finished = stored.mark_finished(finished_at=NOW + timedelta(minutes=11))
            await repo.save(finished)

        # После «финиша» partial-unique должен пропустить новую активную запись.
        async with uow:
            second = await repo.add(
                _build_run(
                    player_id=player.id,
                    outcome=_outcome_with_item(),
                    started_at=NOW + timedelta(minutes=20),
                )
            )
        assert second.id is not None
        assert second.id != stored.id
        assert second.status is ForestRunStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_get_active_by_player_returns_only_in_progress(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = _make_repo(uow)

        async with uow:
            assert await repo.get_active_by_player(player_id=player.id) is None

        async with uow:
            stored = await repo.add(_build_run(player_id=player.id, outcome=_outcome_no_drop()))

        async with uow:
            active = await repo.get_active_by_player(player_id=player.id)
            assert active is not None
            assert active.id == stored.id
            assert active.status is ForestRunStatus.IN_PROGRESS

        # Финишируем — get_active возвращает None.
        async with uow:
            await repo.save(stored.mark_finished(finished_at=NOW + timedelta(minutes=11)))

        async with uow:
            assert await repo.get_active_by_player(player_id=player.id) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "outcome_factory",
        [_outcome_no_drop, _outcome_with_item, _outcome_with_name],
        ids=["no-drop", "item-drop", "name-drop"],
    )
    async def test_round_trip_drop_variants(
        self,
        uow: SqlAlchemyUnitOfWork,
        outcome_factory: Callable[[], ForestRunOutcome],
    ) -> None:
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = _make_repo(uow)
        outcome = outcome_factory()

        async with uow:
            stored = await repo.add(_build_run(player_id=player.id, outcome=outcome))

        async with uow:
            reloaded = await repo.get_active_by_player(player_id=player.id)
            assert reloaded is not None
            assert reloaded.id == stored.id
            assert reloaded.drop == outcome.drop
            assert reloaded.branch_name == outcome.branch.name
            assert reloaded.length_delta_cm == outcome.length_cm

    @pytest.mark.asyncio
    async def test_save_unknown_id_raises(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = _make_repo(uow)
        ghost = ForestRun.starting(
            player_id=12345,
            outcome=_outcome_no_drop(),
            started_at=NOW,
            ends_at=NOW + timedelta(minutes=10),
        )
        # Подделать id вручную, чтобы попасть на ветку «not found».
        ghost_with_id = replace(ghost, id=99999)
        with pytest.raises(DomainIntegrityError, match="not found"):
            async with uow:
                await repo.save(ghost_with_id)

    @pytest.mark.asyncio
    async def test_save_without_id_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        repo = _make_repo(uow)
        new_run = _build_run(player_id=1, outcome=_outcome_no_drop())
        with pytest.raises(DomainIntegrityError, match="requires id"):
            async with uow:
                await repo.save(new_run)
