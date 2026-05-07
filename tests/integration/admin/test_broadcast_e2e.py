"""Integration-тест `/announce`-flow (Спринт 2.5-D.4).

Эта проверка соединяет фактические production-адаптеры
`AsyncIOBroadcastTaskSpawner` (фоновая задача через `asyncio.create_task`)
с use-case-ом `RunBroadcastAnnouncement`. Цель — убедиться, что:

1. Шедулер действительно запускает coro в фоне (не в текущем тике).
2. По завершении задача убирается из внутреннего set-а (нет утечки).
3. Throttle-интервалы между батчами в реальном `asyncio`-loop-е
   соблюдаются с разумной точностью (sleep — настоящий `asyncio.sleep`,
   но мы используем `event_loop.time()` для бюджета теста).

Тест умышленно держит интервал маленьким (`batch_interval_seconds=0.05`,
`batch_size=2`, recipient=4 → 2 батча → ~0.05s sleep).
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import (
    BroadcastLocaleFilter,
    RunBroadcastAnnouncement,
    RunBroadcastAnnouncementInput,
)
from pipirik_wars.domain.admin import AdminRole
from pipirik_wars.domain.player import Player, PlayerStatus, Username
from pipirik_wars.infrastructure.telegram.broadcast import (
    AsyncIOBroadcastTaskSpawner,
)
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.broadcast import FakeBroadcastSender
from tests.fakes.clock import FakeClock
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.uow import FakeUnitOfWork

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _seed_player(players: FakePlayerRepository, *, tg_id: int, locale_override: str) -> None:
    new_id = (max((p.id or 0 for p in players.rows), default=0)) + 1
    base = Player.new(tg_id=tg_id, username=Username(value=f"u{tg_id}"), now=_NOW)
    seeded = replace(
        base,
        id=new_id,
        status=PlayerStatus.ACTIVE,
        locale_override=locale_override,
    )
    players.rows.append(seeded)


@pytest.mark.asyncio
async def test_async_spawner_runs_broadcast_off_thread() -> None:
    """`AsyncIOBroadcastTaskSpawner.spawn(coro)` действительно отдаёт
    coro фоновой `asyncio`-задаче и не выполняет её в текущем тике."""
    spawner = AsyncIOBroadcastTaskSpawner()
    sentinel: list[str] = []

    async def background() -> None:
        await asyncio.sleep(0)
        sentinel.append("ran")

    spawner.spawn(background())

    # До yield-а control-а очереди — coro ещё не выполнялась.
    assert sentinel == []
    # Один прогон event-loop-а — coro исполняется.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert sentinel == ["ran"]


@pytest.mark.asyncio
async def test_run_broadcast_announcement_throttles_between_batches_real_sleep() -> None:
    """Фактический `asyncio.sleep` между батчами — measurable wall-clock."""
    sender = FakeBroadcastSender(default_result="sent")
    admins = FakeAdminRepository()
    players = FakePlayerRepository()
    admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN)
    for tg in range(100, 104):
        _seed_player(players, tg_id=tg, locale_override="ru")

    use_case = RunBroadcastAnnouncement(
        uow=FakeUnitOfWork(),
        admins=admins,
        players=players,
        sender=sender,
        audit=FakeAdminAuditLogger(),
        clock=FakeClock(_NOW),
        authz=FakeAdminAuthzAllowAll(),
        # Real `asyncio.sleep` — мы хотим интегрировать с реальным loop-ом.
        sleep=asyncio.sleep,
        batch_size=2,
        batch_interval_seconds=0.05,
    )

    loop = asyncio.get_running_loop()
    started_at = loop.time()
    out = await use_case.execute(
        RunBroadcastAnnouncementInput(
            actor_tg_id=42,
            locale_filter=BroadcastLocaleFilter.RU,
            message="hello!",
        ),
    )
    elapsed = loop.time() - started_at

    # 4 адресата, batch_size=2 → 2 батча → 1 sleep (между батчами 1↔2).
    # Перед первым батчем sleep не делается; после последнего — тоже.
    # Поэтому ожидаемый throttle-бюджет — около 0.05s.
    assert out.recipient_count == 4
    assert out.sent_count == 4
    assert elapsed >= 0.05
    # Верхняя граница свободная: даже на нагруженном CI 0.05s sleep
    # не должен превратиться в секунды.
    assert elapsed < 1.5, f"throttle-bound seems broken: elapsed={elapsed:.3f}"


@pytest.mark.asyncio
async def test_async_spawner_does_not_leak_tasks_after_completion() -> None:
    """После завершения coro spawner не держит ссылок (`_tasks` пуст)."""
    spawner = AsyncIOBroadcastTaskSpawner()

    async def quick() -> None:
        await asyncio.sleep(0)

    spawner.spawn(quick())
    spawner.spawn(quick())

    # Дождаться завершения и yield-а done-callback-а.
    for _ in range(5):
        await asyncio.sleep(0)

    # `_tasks` помечен `__slots__`-приватом, проверяем через атрибут.
    assert spawner._tasks == set()
