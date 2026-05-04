"""Unit-тесты `FinishForestRun` (Спринт 1.3.C).

Покрытие:
- happy path: длина начислена, выдан `NEWBIE`, lock снят, audit пишется
  в `LENGTH_GRANT` + `TITLE_GRANT`; UoW коммитит ровно 1 раз;
- идемпотентность: повторный финиш на уже-`FINISHED`-записи — no-op,
  никаких mutations / audit-записей;
- титул не перевыдаётся, если у игрока уже есть title (например, ручная
  выдача; идемпотентно по `player.title is None`);
- `NameDrop` + игрок без имени → имя auto-applied + `NAME_GRANT` в audit;
- `NameDrop` + игрок С именем → имя НЕ перетирается, audit `NAME_GRANT`
  не пишется (handler из 1.3.D даст inline «Заменить / Выбросить»);
- `ItemDrop` / `NoDrop` → имя не выдаётся;
- `ForestRunNotFoundError`, если по `run_id` нет записи в `forest_runs`;
- `PlayerNotFoundError`, если ссылка на игрока «висит».
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import FinishForestRunInput
from pipirik_wars.application.forest import FinishForestRun, ForestRunFinished
from pipirik_wars.application.security import ActivityLockService
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
from pipirik_wars.domain.player import (
    Player,
    PlayerName,
    PlayerNotFoundError,
    Title,
    Username,
)
from pipirik_wars.domain.security import ActivityLock, LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeClock,
    FakeForestRunRepository,
    FakePlayerRepository,
    FakeUnitOfWork,
)

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
_STARTED = _NOW - timedelta(minutes=15)
_ENDS = _NOW


def _build_use_case(
    *,
    clock: FakeClock | None = None,
) -> tuple[
    FinishForestRun,
    FakePlayerRepository,
    FakeForestRunRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
    FakeActivityLockRepository,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    runs = FakeForestRunRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    lock_repo = FakeActivityLockRepository()
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    use_case = FinishForestRun(
        uow=uow,
        players=players,
        runs=runs,
        locks=locks,
        audit=audit,
        clock=used_clock,
    )
    return use_case, players, runs, audit, uow, used_clock, lock_repo


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int = 42,
    title: Title | None = None,
    name: PlayerName | None = None,
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
    branch_name: str = "normal",
    length_delta_cm: int = 5,
    drop: NoDrop | ItemDrop | NameDrop | None = None,
) -> ForestRun:
    run = ForestRun(
        id=None,
        player_id=player_id,
        status=ForestRunStatus.IN_PROGRESS,
        started_at=_STARTED,
        ends_at=_ENDS,
        branch_name=branch_name,
        length_delta_cm=length_delta_cm,
        drop=drop or NoDrop(),
        finished_at=None,
    )
    return await runs.add(run)


async def _seed_lock(
    lock_repo: FakeActivityLockRepository,
    *,
    player_id: int,
    expires_at: datetime,
) -> None:
    lock_repo.locks[("player", player_id)] = ActivityLock(
        actor_kind="player",
        actor_id=player_id,
        reason=LockReason.FOREST,
        acquired_at=_STARTED,
        expires_at=expires_at,
    )


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_grants_length_and_title_and_releases_lock(self) -> None:
        use_case, players, runs, audit, uow, _clock, lock_repo = _build_use_case()
        player = await _seed_player(players)
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            length_delta_cm=7,
            drop=NoDrop(),
        )
        assert run.id is not None
        await _seed_lock(lock_repo, player_id=player.id, expires_at=_ENDS)

        result = await use_case.execute(FinishForestRunInput(run_id=run.id))

        assert isinstance(result, ForestRunFinished)
        assert result.was_already_finished is False
        assert result.granted_title is True
        assert result.granted_name is False
        assert result.player_after.length.cm == player.length.cm + 7
        assert result.player_after.title is Title.NEWBIE
        assert result.run.status is ForestRunStatus.FINISHED
        assert result.run.finished_at == _NOW

        assert lock_repo.locks.get(("player", player.id)) is None
        assert uow.commits == 1
        assert uow.rollbacks == 0
        actions = [e.action for e in audit.entries]
        assert actions == [AuditAction.LENGTH_GRANT, AuditAction.TITLE_GRANT]
        assert audit.entries[0].idempotency_key == f"forest_run_finished:length:{run.id}"
        assert audit.entries[1].idempotency_key == f"forest_run_finished:title:{run.id}"


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_already_finished_is_noop(self) -> None:
        use_case, players, runs, audit, uow, _clock, _lock_repo = _build_use_case()
        player = await _seed_player(players, title=Title.NEWBIE)
        assert player.id is not None
        run = await _seed_run(runs, player_id=player.id)
        assert run.id is not None
        runs.rows[0] = run.mark_finished(finished_at=_STARTED)

        result = await use_case.execute(FinishForestRunInput(run_id=run.id))

        assert result.was_already_finished is True
        assert result.granted_title is False
        assert result.granted_name is False
        assert result.player_before == result.player_after
        # no audit, no mutations
        assert audit.entries == []
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_title_not_regranted_if_already_present(self) -> None:
        use_case, players, runs, audit, _uow, _clock, lock_repo = _build_use_case()
        player = await _seed_player(players, title=Title.NEWBIE)
        assert player.id is not None
        run = await _seed_run(runs, player_id=player.id, length_delta_cm=3)
        assert run.id is not None
        await _seed_lock(lock_repo, player_id=player.id, expires_at=_ENDS)

        result = await use_case.execute(FinishForestRunInput(run_id=run.id))

        assert result.granted_title is False
        actions = [e.action for e in audit.entries]
        assert AuditAction.TITLE_GRANT not in actions
        assert AuditAction.LENGTH_GRANT in actions


class TestNameDrop:
    @pytest.mark.asyncio
    async def test_auto_apply_name_when_player_has_no_name(self) -> None:
        use_case, players, runs, audit, _uow, _clock, lock_repo = _build_use_case()
        player = await _seed_player(players)
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            drop=NameDrop(name=Name(value="Pirat")),
        )
        assert run.id is not None
        await _seed_lock(lock_repo, player_id=player.id, expires_at=_ENDS)

        result = await use_case.execute(FinishForestRunInput(run_id=run.id))

        assert result.granted_name is True
        assert result.player_after.name == PlayerName(value="Pirat")
        actions = [e.action for e in audit.entries]
        assert AuditAction.NAME_GRANT in actions
        name_entry = next(e for e in audit.entries if e.action is AuditAction.NAME_GRANT)
        assert name_entry.idempotency_key == f"forest_run_finished:name:{run.id}"
        assert name_entry.after == {"name": "Pirat"}

    @pytest.mark.asyncio
    async def test_name_not_overwritten_if_player_already_named(self) -> None:
        use_case, players, runs, audit, _uow, _clock, _lock_repo = _build_use_case()
        player = await _seed_player(
            players,
            name=PlayerName(value="Existing"),
        )
        assert player.id is not None
        run = await _seed_run(
            runs,
            player_id=player.id,
            drop=NameDrop(name=Name(value="NewName")),
        )
        assert run.id is not None

        result = await use_case.execute(FinishForestRunInput(run_id=run.id))

        assert result.granted_name is False
        assert result.player_after.name == PlayerName(value="Existing")
        actions = [e.action for e in audit.entries]
        assert AuditAction.NAME_GRANT not in actions

    @pytest.mark.asyncio
    async def test_item_drop_does_not_auto_apply_name(self) -> None:
        use_case, players, runs, audit, _uow, _clock, _lock_repo = _build_use_case()
        player = await _seed_player(players)
        assert player.id is not None
        item = Item(
            id="item.hat.cap",
            slot=Slot.HAT,
            display_name="Cap",
            rarity=Rarity.COMMON,
        )
        run = await _seed_run(runs, player_id=player.id, drop=ItemDrop(item=item))
        assert run.id is not None

        result = await use_case.execute(FinishForestRunInput(run_id=run.id))

        assert result.granted_name is False
        assert result.player_after.name is None
        assert AuditAction.NAME_GRANT not in [e.action for e in audit.entries]


class TestErrors:
    @pytest.mark.asyncio
    async def test_run_not_found_raises(self) -> None:
        use_case, _players, _runs, audit, uow, _clock, _lock_repo = _build_use_case()

        with pytest.raises(ForestRunNotFoundError) as exc:
            await use_case.execute(FinishForestRunInput(run_id=999))

        assert exc.value.run_id == 999
        assert audit.entries == []
        assert uow.commits == 0
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        use_case, players, runs, audit, uow, _clock, _lock_repo = _build_use_case()
        # ForestRun-запись есть, а игрока — нет (висячая ссылка)
        run = await _seed_run(runs, player_id=999)
        assert run.id is not None
        # players.rows пуст

        with pytest.raises(PlayerNotFoundError) as exc:
            await use_case.execute(FinishForestRunInput(run_id=run.id))

        assert exc.value.tg_id == 999
        assert audit.entries == []
        assert uow.commits == 0
        assert uow.rollbacks == 1
        # Длина игрока остаётся «как было» (нет игрока — нет mutations).
        assert players.rows == []
