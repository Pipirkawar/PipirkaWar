"""Unit-тесты `ApplyForestNameDrop` (Спринт 1.3.D)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import ApplyForestNameDropInput
from pipirik_wars.application.forest import ApplyForestNameDrop, ForestNameDropApplied
from pipirik_wars.domain.forest import (
    ForestRun,
    ForestRunNotFoundError,
    ForestRunStatus,
    Item,
    ItemDrop,
    Name,
    NameDrop,
    NoDrop,
    Rarity,
    Slot,
)
from pipirik_wars.domain.forest.errors import (
    ForestDropMismatchError,
    ForestRunOwnershipError,
)
from pipirik_wars.domain.player import (
    Player,
    PlayerName,
    PlayerNotFoundError,
    Title,
    Username,
)
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeAuditLogger,
    FakeClock,
    FakeForestRunRepository,
    FakePlayerRepository,
    FakeUnitOfWork,
)

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_STARTED = _NOW - timedelta(minutes=15)


def _build_use_case() -> tuple[
    ApplyForestNameDrop,
    FakePlayerRepository,
    FakeForestRunRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    runs = FakeForestRunRepository()
    audit = FakeAuditLogger()
    clock = FakeClock(_NOW)
    use_case = ApplyForestNameDrop(
        uow=uow,
        players=players,
        runs=runs,
        audit=audit,
        clock=clock,
    )
    return use_case, players, runs, audit, uow, clock


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int = 42,
    name: PlayerName | None = None,
    title: Title | None = Title.NEWBIE,
) -> Player:
    player = await players.add(
        Player.new(tg_id=tg_id, username=Username(value="alice"), now=_STARTED),
    )
    if title is not None:
        player = await players.save(player.with_title(title, now=_STARTED))
    if name is not None:
        player = await players.save(player.with_name(name, now=_STARTED))
    return player


async def _seed_run(
    runs: FakeForestRunRepository,
    *,
    player_id: int,
    drop: NoDrop | ItemDrop | NameDrop,
    status: ForestRunStatus = ForestRunStatus.FINISHED,
) -> ForestRun:
    run = ForestRun(
        id=None,
        player_id=player_id,
        status=status,
        started_at=_STARTED,
        ends_at=_NOW,
        finished_at=_NOW,
        branch_name="normal",
        length_delta_cm=5,
        drop=drop,
    )
    return await runs.add(run)


class TestApplyForestNameDropHappyPath:
    @pytest.mark.asyncio
    async def test_replaces_name_and_writes_audit(self) -> None:
        use_case, players, runs, audit, uow, _ = _build_use_case()
        player = await _seed_player(
            players,
            name=PlayerName(value="Старое"),
        )
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            drop=NameDrop(name=Name(value="Новое")),
        )
        assert run.id is not None

        result = await use_case.execute(ApplyForestNameDropInput(run_id=run.id, tg_id=player.tg_id))

        assert isinstance(result, ForestNameDropApplied)
        assert result.was_already_applied is False
        assert result.new_name == PlayerName(value="Новое")
        assert result.player_after.name == PlayerName(value="Новое")
        assert result.player_before.name == PlayerName(value="Старое")
        assert uow.commits == 1
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.NAME_GRANT
        assert entry.target_kind == "forest_run"
        assert entry.target_id == str(run.id)
        assert entry.reason == "forest_name_replacement"
        assert entry.idempotency_key == f"forest_name_replace:{run.id}"
        assert entry.before == {"name": "Старое"}
        assert entry.after == {"name": "Новое"}


class TestApplyForestNameDropIdempotency:
    @pytest.mark.asyncio
    async def test_no_op_when_player_already_has_drop_name(self) -> None:
        use_case, players, runs, audit, uow, _ = _build_use_case()
        player = await _seed_player(
            players,
            name=PlayerName(value="Коляндр"),
        )
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            drop=NameDrop(name=Name(value="Коляндр")),
        )
        assert run.id is not None

        result = await use_case.execute(ApplyForestNameDropInput(run_id=run.id, tg_id=player.tg_id))

        assert result.was_already_applied is True
        assert result.player_before is result.player_after
        assert audit.entries == []
        assert uow.commits == 1


class TestApplyForestNameDropErrors:
    @pytest.mark.asyncio
    async def test_run_not_found(self) -> None:
        use_case, players, _, audit, uow, _ = _build_use_case()
        player = await _seed_player(players, name=PlayerName(value="X"))

        with pytest.raises(ForestRunNotFoundError):
            await use_case.execute(ApplyForestNameDropInput(run_id=999, tg_id=player.tg_id))
        assert audit.entries == []
        # Транзакция открылась и откатилась — `commits` остаётся 0.
        assert uow.commits == 0

    @pytest.mark.asyncio
    async def test_player_not_found(self) -> None:
        use_case, players, runs, audit, uow, _ = _build_use_case()
        player = await _seed_player(players)
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            drop=NameDrop(name=Name(value="Y")),
        )
        assert run.id is not None

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(ApplyForestNameDropInput(run_id=run.id, tg_id=999_999))
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_ownership_mismatch(self) -> None:
        use_case, players, runs, audit, uow, _ = _build_use_case()
        owner = await _seed_player(players, tg_id=1)
        intruder = await _seed_player(players, tg_id=2)
        assert owner.id is not None and intruder.id is not None
        run = await _seed_run(
            runs,
            player_id=owner.id,
            drop=NameDrop(name=Name(value="Z")),
        )
        assert run.id is not None

        with pytest.raises(ForestRunOwnershipError):
            await use_case.execute(ApplyForestNameDropInput(run_id=run.id, tg_id=intruder.tg_id))
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_drop_mismatch_for_no_drop(self) -> None:
        use_case, players, runs, audit, uow, _ = _build_use_case()
        player = await _seed_player(players)
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            drop=NoDrop(),
        )
        assert run.id is not None

        with pytest.raises(ForestDropMismatchError):
            await use_case.execute(ApplyForestNameDropInput(run_id=run.id, tg_id=player.tg_id))
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_drop_mismatch_for_item_drop(self) -> None:
        use_case, players, runs, audit, uow, _ = _build_use_case()
        player = await _seed_player(players)
        assert player.id is not None
        item = Item(
            id="item.hat.x",
            display_name="X",
            slot=Slot.HAT,
            rarity=Rarity.COMMON,
        )
        run = await _seed_run(
            runs,
            player_id=player.id,
            drop=ItemDrop(item=item),
        )
        assert run.id is not None

        with pytest.raises(ForestDropMismatchError):
            await use_case.execute(ApplyForestNameDropInput(run_id=run.id, tg_id=player.tg_id))
        assert audit.entries == []
