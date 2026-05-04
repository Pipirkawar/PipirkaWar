"""Unit-тесты `PromoteFromQueue` (Спринт 1.2.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.signup_queue import (
    PromoteFromQueue,
    PromoteFromQueueResult,
)
from pipirik_wars.domain.player import Player, Username
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.domain.signup_queue import SignupQueueEntry
from tests.fakes import (
    FakeAuditLogger,
    FakeClock,
    FakeDauCounter,
    FakeDauLimit,
    FakePlayerRepository,
    FakeSignupQueueRepository,
    FakeUnitOfWork,
)

_BASE_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


def _build(
    *,
    initial_dau: int = 0,
    max_dau: int = 5,
) -> tuple[
    PromoteFromQueue,
    FakeUnitOfWork,
    FakePlayerRepository,
    FakeSignupQueueRepository,
    FakeAuditLogger,
    FakeDauCounter,
    FakeDauLimit,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    queue = FakeSignupQueueRepository()
    audit = FakeAuditLogger()
    counter = FakeDauCounter(initial=initial_dau)
    limit = FakeDauLimit(initial=max_dau)
    use_case = PromoteFromQueue(
        uow=uow,
        players=players,
        signup_queue=queue,
        dau_counter=counter,
        dau_limit=limit,
        audit=audit,
        clock=FakeClock(_BASE_NOW),
    )
    return use_case, uow, players, queue, audit, counter, limit


async def _seed(
    queue: FakeSignupQueueRepository,
    *,
    tg_ids: list[int],
    base: datetime = _BASE_NOW,
) -> None:
    for offset, tg_id in enumerate(tg_ids):
        await queue.enqueue(
            entry=SignupQueueEntry(
                id=None,
                tg_id=tg_id,
                username=f"u{tg_id}",
                locale="ru",
                position=0,
                enqueued_at=base + timedelta(seconds=offset),
            ),
        )


@pytest.mark.asyncio
class TestPromoteFromQueue:
    async def test_empty_queue_returns_empty_promoted(self) -> None:
        use_case, uow, players, _, audit, counter, _ = _build(initial_dau=0, max_dau=5)

        result = await use_case.execute()

        assert isinstance(result, PromoteFromQueueResult)
        assert result.promoted == ()
        assert result.skipped_already_registered == ()
        assert result.available_slots == 5
        assert result.promoted_count == 0
        assert players.rows == []
        assert audit.entries == []
        assert await counter.current() == 0
        assert uow.commits == 1
        assert uow.rollbacks == 0

    async def test_full_capacity_zero_slots_short_circuits(self) -> None:
        use_case, uow, players, queue, audit, _, _ = _build(initial_dau=5, max_dau=5)
        await _seed(queue, tg_ids=[101, 102])

        result = await use_case.execute()

        assert result.promoted == ()
        assert result.available_slots == 0
        assert players.rows == []
        # Очередь не тронута.
        assert await queue.size() == 2
        assert audit.entries == []
        assert uow.commits == 1

    async def test_promotes_first_n_when_slots_smaller_than_queue(self) -> None:
        use_case, _, players, queue, audit, counter, _ = _build(initial_dau=0, max_dau=2)
        await _seed(queue, tg_ids=[101, 102, 103])

        result = await use_case.execute()

        assert result.promoted_count == 2
        promoted_ids = sorted(p.tg_id for p in result.promoted)
        assert promoted_ids == [101, 102]
        # Третий остался в очереди и стал первым.
        assert await queue.size() == 1
        rest = await queue.get_by_tg_id(103)
        assert rest is not None
        assert rest.position == 1
        # `record_active(...)` зовётся для каждого поднятого.
        assert await counter.current() == 2
        # `players.rows` содержит обоих с присвоенными id.
        assert {p.tg_id for p in players.rows} == {101, 102}
        assert all(p.id is not None for p in players.rows)
        # Audit-записи: по одной на каждого поднятого.
        promote_actions = [
            entry for entry in audit.entries if entry.action == AuditAction.PLAYER_PROMOTED
        ]
        assert len(promote_actions) == 2

    async def test_promote_audit_records_have_idempotency_keys(self) -> None:
        use_case, _, _, queue, audit, _, _ = _build(initial_dau=0, max_dau=10)
        await _seed(queue, tg_ids=[201, 202])

        await use_case.execute()

        keys = {entry.idempotency_key for entry in audit.entries}
        assert "promote_player:201" in keys
        assert "promote_player:202" in keys

    async def test_promote_audit_before_contains_queue_position(self) -> None:
        use_case, _, _, queue, audit, _, _ = _build(initial_dau=0, max_dau=10)
        await _seed(queue, tg_ids=[301, 302])

        await use_case.execute()

        first = next(
            entry
            for entry in audit.entries
            if entry.action == AuditAction.PLAYER_PROMOTED and entry.target_id == "301"
        )
        assert first.before is not None
        assert first.before["queued_position"] == 1
        assert "queued_at" in first.before

    async def test_already_registered_is_skipped_silently(self) -> None:
        use_case, _, players, queue, audit, counter, _ = _build(initial_dau=0, max_dau=5)
        # Игрок 401 уже зарегистрирован «через другой путь».
        existing = Player.new(tg_id=401, username=Username(value="dup"), now=_BASE_NOW)
        await players.add(existing)
        await _seed(queue, tg_ids=[401, 402])

        result = await use_case.execute()

        assert result.skipped_already_registered == (401,)
        # 402 успешно поднят.
        assert {p.tg_id for p in result.promoted} == {402}
        # Audit для 401 (повторного) НЕ пишется; audit для 402 — пишется.
        promoted_audits = [
            entry for entry in audit.entries if entry.action == AuditAction.PLAYER_PROMOTED
        ]
        assert {entry.target_id for entry in promoted_audits} == {"402"}
        # `record_active` зовётся только для реально поднятых.
        assert await counter.current() == 1

    async def test_dau_grows_per_promoted_player(self) -> None:
        use_case, _, _, queue, _, counter, _ = _build(initial_dau=2, max_dau=5)
        await _seed(queue, tg_ids=[501, 502, 503])

        await use_case.execute()

        # initial_dau=2, slots=3 → подняли всех 3 → dau=5.
        assert await counter.current() == 5

    async def test_capacity_exactly_matches_queue_drains_it(self) -> None:
        use_case, _, _, queue, _, _, _ = _build(initial_dau=0, max_dau=2)
        await _seed(queue, tg_ids=[601, 602])

        result = await use_case.execute()

        assert result.promoted_count == 2
        assert await queue.size() == 0

    async def test_uow_rolls_back_when_player_repo_raises_unexpected(self) -> None:
        use_case, uow, players, queue, audit, _, _ = _build(initial_dau=0, max_dau=5)
        await _seed(queue, tg_ids=[701])

        original_add = players.add

        async def raising_add(player: Player) -> Player:
            if player.tg_id == 701:
                raise RuntimeError("db blew up")
            return await original_add(player)

        players.add = raising_add  # type: ignore[method-assign]

        with pytest.raises(RuntimeError):
            await use_case.execute()

        assert uow.commits == 0
        assert uow.rollbacks == 1
        assert audit.entries == []
