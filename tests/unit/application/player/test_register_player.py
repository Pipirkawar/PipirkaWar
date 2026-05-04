"""Unit-тесты `RegisterPlayer` (Спринт 1.1.3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.dto.inputs import RegisterPlayerInput
from pipirik_wars.application.player import RegisterPlayer
from pipirik_wars.domain.player import (
    PlayerAlreadyRegisteredError,
    PlayerStatus,
)
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeAuditLogger,
    FakeClock,
    FakePlayerRepository,
    FakeUnitOfWork,
)


def _build_use_case(
    *,
    clock: FakeClock | None = None,
) -> tuple[RegisterPlayer, FakePlayerRepository, FakeAuditLogger, FakeUnitOfWork, FakeClock]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(datetime(2026, 5, 4, 12, 0, tzinfo=UTC))
    use_case = RegisterPlayer(uow=uow, players=players, audit=audit, clock=used_clock)
    return use_case, players, audit, uow, used_clock


class TestRegisterPlayer:
    @pytest.mark.asyncio
    async def test_creates_player_with_initial_values_per_gdd_1_1(self) -> None:
        use_case, players, audit, uow, clock = _build_use_case()

        saved = await use_case.execute(
            RegisterPlayerInput(tg_id=12345, username="alice"),
        )

        assert saved.id == 1
        assert saved.tg_id == 12345
        assert saved.length.cm == 2
        assert saved.thickness.level == 1
        assert saved.title is None
        assert saved.name is None
        assert saved.status is PlayerStatus.ACTIVE
        assert saved.username is not None
        assert saved.username.value == "alice"
        assert saved.created_at == clock.now()
        assert saved.updated_at == clock.now()
        assert len(players.rows) == 1
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_writes_audit_entry_register(self) -> None:
        use_case, _, audit, _, clock = _build_use_case()

        await use_case.execute(RegisterPlayerInput(tg_id=42))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.PLAYER_REGISTER
        assert entry.actor_id == 42
        assert entry.target_kind == "player"
        assert entry.target_id == "42"
        assert entry.before is None
        assert entry.after is not None
        assert entry.after["tg_id"] == 42
        assert entry.after["length_cm"] == 2
        assert entry.after["thickness_level"] == 1
        assert entry.after["username"] is None
        assert entry.idempotency_key == "register_player:42"
        assert entry.occurred_at == clock.now()

    @pytest.mark.asyncio
    async def test_username_none_supported(self) -> None:
        use_case, _, _, _, _ = _build_use_case()

        saved = await use_case.execute(
            RegisterPlayerInput(tg_id=42, username=None),
        )

        assert saved.username is None

    @pytest.mark.asyncio
    async def test_duplicate_tg_id_raises_already_registered(self) -> None:
        use_case, players, audit, uow, _ = _build_use_case()

        await use_case.execute(RegisterPlayerInput(tg_id=42))
        with pytest.raises(PlayerAlreadyRegisteredError) as exc_info:
            await use_case.execute(RegisterPlayerInput(tg_id=42))

        assert exc_info.value.tg_id == 42
        assert len(players.rows) == 1
        # Первый execute → commit, второй (с raise) → rollback.
        assert uow.commits == 1
        assert uow.rollbacks == 1
        # Аудит про второй вызов не пишется.
        assert len(audit.entries) == 1
