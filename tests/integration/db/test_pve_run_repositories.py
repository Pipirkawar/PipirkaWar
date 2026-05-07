"""Integration-тесты `SqlAlchemy{Mountain,Dungeon}RunRepository`.

Round-trip: `add()` → `get_by_id` / `get_active_by_player` → `save()`
+ partial-unique инвариант `(player_id, status='in_progress')` +
обработка ошибок (preset id, save без id, неизвестный id, неизвестный
item в каталоге).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pipirik_wars.domain.balance.config import PveSign
from pipirik_wars.domain.dungeon import (
    DungeonRun,
    DungeonRunStatus,
    IDungeonRunRepository,
)
from pipirik_wars.domain.forest import Item, Rarity, Slot
from pipirik_wars.domain.mountains import (
    IMountainRunRepository,
    MountainRun,
    MountainRunStatus,
)
from pipirik_wars.domain.player import Player
from pipirik_wars.domain.pve.entities import (
    PveItemDrop,
    PveOutcomeBranch,
    PveRunOutcome,
)
from pipirik_wars.infrastructure.db.repositories import (
    SqlAlchemyDungeonRunRepository,
    SqlAlchemyMountainRunRepository,
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.shared.errors import IntegrityError as DomainIntegrityError
from tests.fakes import FakeBalanceConfig
from tests.unit.domain.balance.factories import build_valid_balance

NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)


def _hat_item() -> Item:
    return Item(
        id="item.hat.test_1",
        slot=Slot.HAT,
        display_name="Тестовый hat #1",
        rarity=Rarity.COMMON,
    )


def _ring_item() -> Item:
    return Item(
        id="item.ring.test_2",
        slot=Slot.RING,
        display_name="Тестовый ring #2",
        rarity=Rarity.COMMON,
    )


def _outcome_gain_no_drop() -> PveRunOutcome:
    return PveRunOutcome(
        branch=PveOutcomeBranch(name="small_gain", sign=PveSign.GAIN, length_cm=10),
        length_delta_cm=10,
        drops=(),
    )


def _outcome_gain_with_drop() -> PveRunOutcome:
    return PveRunOutcome(
        branch=PveOutcomeBranch(name="normal_gain", sign=PveSign.GAIN, length_cm=20),
        length_delta_cm=20,
        drops=(PveItemDrop(item=_hat_item()),),
    )


def _outcome_gain_two_drops() -> PveRunOutcome:
    return PveRunOutcome(
        branch=PveOutcomeBranch(name="big_gain", sign=PveSign.GAIN, length_cm=30),
        length_delta_cm=30,
        drops=(
            PveItemDrop(item=_hat_item()),
            PveItemDrop(item=_ring_item()),
        ),
    )


def _outcome_loss() -> PveRunOutcome:
    return PveRunOutcome(
        branch=PveOutcomeBranch(name="small_loss", sign=PveSign.LOSS, length_cm=15),
        length_delta_cm=-15,
        drops=(),
    )


async def _seed_player(uow: SqlAlchemyUnitOfWork, *, tg_id: int) -> Player:
    repo = SqlAlchemyPlayerRepository(uow=uow)
    async with uow:
        return await repo.add(Player.new(tg_id=tg_id, username=None, now=NOW))


def _make_mountain_repo(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyMountainRunRepository:
    return SqlAlchemyMountainRunRepository(
        uow=uow,
        balance=FakeBalanceConfig(build_valid_balance()),
    )


def _make_dungeon_repo(uow: SqlAlchemyUnitOfWork) -> SqlAlchemyDungeonRunRepository:
    return SqlAlchemyDungeonRunRepository(
        uow=uow,
        balance=FakeBalanceConfig(build_valid_balance()),
    )


def _build_mountain_run(
    *,
    player_id: int,
    outcome: PveRunOutcome,
    started_at: datetime = NOW,
    cooldown: timedelta = timedelta(minutes=30),
) -> MountainRun:
    return MountainRun.starting(
        player_id=player_id,
        outcome=outcome,
        started_at=started_at,
        ends_at=started_at + cooldown,
    )


def _build_dungeon_run(
    *,
    player_id: int,
    outcome: PveRunOutcome,
    started_at: datetime = NOW,
    cooldown: timedelta = timedelta(minutes=50),
) -> DungeonRun:
    return DungeonRun.starting(
        player_id=player_id,
        outcome=outcome,
        started_at=started_at,
        ends_at=started_at + cooldown,
    )


# --- Параметризация: один и тот же набор сценариев для обеих локаций. -------


_LocationName = str
_RepoFactory = Callable[[SqlAlchemyUnitOfWork], Any]
_RunFactory = Callable[..., Any]
_LocationParam = tuple[_LocationName, _RepoFactory, _RunFactory, Any]


def _mountain_param() -> _LocationParam:
    return ("mountain", _make_mountain_repo, _build_mountain_run, MountainRunStatus)


def _dungeon_param() -> _LocationParam:
    return ("dungeon", _make_dungeon_repo, _build_dungeon_run, DungeonRunStatus)


_LOCATIONS = [_mountain_param(), _dungeon_param()]


class TestPveRunRepositoryRoundTrip:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("loc", _LOCATIONS, ids=[loc[0] for loc in _LOCATIONS])
    async def test_add_assigns_id_and_status_in_progress(
        self,
        uow: SqlAlchemyUnitOfWork,
        loc: _LocationParam,
    ) -> None:
        _name, repo_factory, run_factory, status_enum = loc
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = repo_factory(uow)

        async with uow:
            stored = await repo.add(
                run_factory(player_id=player.id, outcome=_outcome_gain_no_drop()),
            )

        assert stored.id is not None
        assert stored.status is status_enum.IN_PROGRESS
        assert stored.player_id == player.id
        assert stored.branch_name == "small_gain"
        assert stored.length_delta_cm == 10
        assert stored.drops == ()
        assert stored.finished_at is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("loc", _LOCATIONS, ids=[loc[0] for loc in _LOCATIONS])
    async def test_add_with_preset_id_rejected(
        self,
        uow: SqlAlchemyUnitOfWork,
        loc: _LocationParam,
    ) -> None:
        _name, repo_factory, run_factory, _status = loc
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = repo_factory(uow)

        async with uow:
            stored = await repo.add(
                run_factory(player_id=player.id, outcome=_outcome_gain_no_drop()),
            )

        with pytest.raises(DomainIntegrityError, match="pre-set id"):
            async with uow:
                await repo.add(stored)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("loc", _LOCATIONS, ids=[loc[0] for loc in _LOCATIONS])
    async def test_partial_unique_blocks_second_active_run(
        self,
        uow: SqlAlchemyUnitOfWork,
        loc: _LocationParam,
    ) -> None:
        _name, repo_factory, run_factory, _status = loc
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = repo_factory(uow)

        async with uow:
            await repo.add(run_factory(player_id=player.id, outcome=_outcome_gain_no_drop()))

        with pytest.raises(DomainIntegrityError):
            async with uow:
                await repo.add(
                    run_factory(player_id=player.id, outcome=_outcome_gain_with_drop()),
                )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("loc", _LOCATIONS, ids=[loc[0] for loc in _LOCATIONS])
    async def test_after_finish_can_add_new_active(
        self,
        uow: SqlAlchemyUnitOfWork,
        loc: _LocationParam,
    ) -> None:
        _name, repo_factory, run_factory, status_enum = loc
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = repo_factory(uow)

        async with uow:
            stored = await repo.add(
                run_factory(player_id=player.id, outcome=_outcome_gain_no_drop()),
            )

        async with uow:
            finished = stored.mark_finished(finished_at=NOW + timedelta(minutes=31))
            await repo.save(finished)

        async with uow:
            second = await repo.add(
                run_factory(
                    player_id=player.id,
                    outcome=_outcome_gain_with_drop(),
                    started_at=NOW + timedelta(minutes=60),
                ),
            )
        assert second.id is not None
        assert second.id != stored.id
        assert second.status is status_enum.IN_PROGRESS

    @pytest.mark.asyncio
    @pytest.mark.parametrize("loc", _LOCATIONS, ids=[loc[0] for loc in _LOCATIONS])
    async def test_get_active_by_player_returns_only_in_progress(
        self,
        uow: SqlAlchemyUnitOfWork,
        loc: _LocationParam,
    ) -> None:
        _name, repo_factory, run_factory, status_enum = loc
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = repo_factory(uow)

        async with uow:
            assert await repo.get_active_by_player(player_id=player.id) is None

        async with uow:
            stored = await repo.add(
                run_factory(player_id=player.id, outcome=_outcome_gain_with_drop()),
            )

        async with uow:
            active = await repo.get_active_by_player(player_id=player.id)
            assert active is not None
            assert active.id == stored.id
            assert active.status is status_enum.IN_PROGRESS

        async with uow:
            await repo.save(stored.mark_finished(finished_at=NOW + timedelta(minutes=31)))

        async with uow:
            assert await repo.get_active_by_player(player_id=player.id) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("loc", _LOCATIONS, ids=[loc[0] for loc in _LOCATIONS])
    @pytest.mark.parametrize(
        "outcome_factory",
        [_outcome_gain_no_drop, _outcome_gain_with_drop, _outcome_gain_two_drops, _outcome_loss],
        ids=["gain-no-drop", "gain-one-drop", "gain-two-drops", "loss"],
    )
    async def test_round_trip_outcome_variants(
        self,
        uow: SqlAlchemyUnitOfWork,
        loc: _LocationParam,
        outcome_factory: Callable[[], PveRunOutcome],
    ) -> None:
        _name, repo_factory, run_factory, _status = loc
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = repo_factory(uow)
        outcome = outcome_factory()

        async with uow:
            stored = await repo.add(run_factory(player_id=player.id, outcome=outcome))

        async with uow:
            reloaded = await repo.get_active_by_player(player_id=player.id)
            assert reloaded is not None
            assert reloaded.id == stored.id
            assert reloaded.drops == outcome.drops
            assert reloaded.branch_name == outcome.branch.name
            assert reloaded.length_delta_cm == outcome.length_delta_cm

    @pytest.mark.asyncio
    @pytest.mark.parametrize("loc", _LOCATIONS, ids=[loc[0] for loc in _LOCATIONS])
    async def test_save_unknown_id_raises(
        self,
        uow: SqlAlchemyUnitOfWork,
        loc: _LocationParam,
    ) -> None:
        _name, repo_factory, run_factory, _status = loc
        repo = repo_factory(uow)
        ghost = run_factory(player_id=12345, outcome=_outcome_gain_no_drop())
        ghost_with_id = replace(ghost, id=99999)
        with pytest.raises(DomainIntegrityError, match="not found"):
            async with uow:
                await repo.save(ghost_with_id)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("loc", _LOCATIONS, ids=[loc[0] for loc in _LOCATIONS])
    async def test_save_without_id_rejected(
        self,
        uow: SqlAlchemyUnitOfWork,
        loc: _LocationParam,
    ) -> None:
        _name, repo_factory, run_factory, _status = loc
        repo = repo_factory(uow)
        new_run = run_factory(player_id=1, outcome=_outcome_gain_no_drop())
        with pytest.raises(DomainIntegrityError, match="requires id"):
            async with uow:
                await repo.save(new_run)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("loc", _LOCATIONS, ids=[loc[0] for loc in _LOCATIONS])
    async def test_get_by_id_missing_returns_none(
        self,
        uow: SqlAlchemyUnitOfWork,
        loc: _LocationParam,
    ) -> None:
        _name, repo_factory, _run_factory, _status = loc
        repo = repo_factory(uow)
        async with uow:
            assert await repo.get_by_id(run_id=99999) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("loc", _LOCATIONS, ids=[loc[0] for loc in _LOCATIONS])
    async def test_save_persists_loss_branch_sign(
        self,
        uow: SqlAlchemyUnitOfWork,
        loc: _LocationParam,
    ) -> None:
        """`branch_sign` выводится из знака `length_delta_cm` репо-уровнем."""
        _name, repo_factory, run_factory, status_enum = loc
        player = await _seed_player(uow, tg_id=42)
        assert player.id is not None
        repo = repo_factory(uow)

        async with uow:
            stored = await repo.add(
                run_factory(player_id=player.id, outcome=_outcome_loss()),
            )

        async with uow:
            reloaded = await repo.get_by_id(run_id=stored.id)
            assert reloaded is not None
            assert reloaded.length_delta_cm == -15
            assert reloaded.status is status_enum.IN_PROGRESS


_RepoT = IMountainRunRepository | IDungeonRunRepository


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locator", "factory"),
    [
        ("mountain", _make_mountain_repo),
        ("dungeon", _make_dungeon_repo),
    ],
)
async def test_unknown_item_in_drops_raises_on_load(
    uow: SqlAlchemyUnitOfWork,
    locator: str,
    factory: Callable[[SqlAlchemyUnitOfWork], _RepoT],
) -> None:
    """Если каталог не содержит item_id из drops — ошибка при чтении."""
    player = await _seed_player(uow, tg_id=42)
    assert player.id is not None
    full_balance = build_valid_balance()
    repo: _RepoT = factory(uow)

    run: MountainRun | DungeonRun
    if locator == "mountain":
        run = _build_mountain_run(player_id=player.id, outcome=_outcome_gain_with_drop())
    else:
        run = _build_dungeon_run(player_id=player.id, outcome=_outcome_gain_with_drop())

    async with uow:
        stored: Any = await repo.add(run)  # type: ignore[arg-type]

    catalog_no_hat = tuple(e for e in full_balance.items_catalog if e.id != "item.hat.test_1")
    bogus = full_balance.model_copy(update={"items_catalog": catalog_no_hat})
    if locator == "mountain":
        bogus_repo: _RepoT = SqlAlchemyMountainRunRepository(
            uow=uow,
            balance=FakeBalanceConfig(bogus),
        )
    else:
        bogus_repo = SqlAlchemyDungeonRunRepository(
            uow=uow,
            balance=FakeBalanceConfig(bogus),
        )
    with pytest.raises(DomainIntegrityError, match="unknown item"):
        async with uow:
            await bogus_repo.get_by_id(run_id=stored.id)
