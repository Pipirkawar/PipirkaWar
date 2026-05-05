"""Unit-тесты `UpgradeThickness` (Спринт 1.4.A, ГДД §3.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import UpgradeThicknessInput
from pipirik_wars.application.progression import (
    ThicknessUpgraded,
    UpgradeThickness,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.domain.progression import (
    AnticheatSoftBanError,
    InsufficientLengthError,
)
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.shared.errors import ConcurrencyError
from tests.fakes import (
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakePlayerRepository,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int = 42,
    length_cm: int,
    thickness_level: int = 1,
    anticheat_ban_until: datetime | None = None,
) -> Player:
    """Положить в репо предзаполненного игрока."""
    player = Player(
        id=1,
        tg_id=tg_id,
        username=Username(value="alice"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=thickness_level),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
        anticheat_ban_until=anticheat_ban_until,
    )
    players.rows.append(player)
    return player


def _build_use_case() -> tuple[
    UpgradeThickness,
    FakePlayerRepository,
    FakeBalanceConfig,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    audit = FakeAuditLogger()
    balance = FakeBalanceConfig(build_valid_balance())
    clock = FakeClock(_NOW)
    use_case = UpgradeThickness(
        uow=uow,
        players=players,
        balance=balance,
        audit=audit,
        clock=clock,
    )
    return use_case, players, balance, audit, uow, clock


@pytest.mark.asyncio
class TestUpgradeThicknessHappyPath:
    async def test_first_upgrade_costs_4000_cm(self) -> None:
        # cost(1→2) = 2² · 1000 = 4000.
        use_case, players, _, audit, _, _ = _build_use_case()
        _seed_player(players, length_cm=4_500, thickness_level=1)

        result = await use_case.execute(UpgradeThicknessInput(tg_id=42))

        assert isinstance(result, ThicknessUpgraded)
        assert result.cost_cm == 4_000
        assert result.new_thickness == 2
        assert result.player_after.thickness.level == 2
        assert result.player_after.length.cm == 500
        # ровно два аудит-события (LENGTH_REVOKE + THICKNESS_UPGRADE).
        assert len(audit.entries) == 2
        actions = {e.action for e in audit.entries}
        assert actions == {AuditAction.LENGTH_REVOKE, AuditAction.THICKNESS_UPGRADE}
        # idempotency_key включает player_id и new_level.
        upgrade_audit = next(e for e in audit.entries if e.action is AuditAction.THICKNESS_UPGRADE)
        assert upgrade_audit.idempotency_key == "thickness_upgrade:1:2"
        assert upgrade_audit.before == {"thickness": 1}
        assert upgrade_audit.after == {"thickness": 2}
        assert upgrade_audit.reason == "player_initiated"

    async def test_second_upgrade_costs_9000_cm(self) -> None:
        # cost(2→3) = 3² · 1000 = 9000.
        use_case, players, _, _, _, _ = _build_use_case()
        _seed_player(players, length_cm=29_500, thickness_level=2)

        result = await use_case.execute(UpgradeThicknessInput(tg_id=42))

        assert result.cost_cm == 9_000
        assert result.new_thickness == 3
        assert result.player_after.length.cm == 20_500

    async def test_persisted_player_returned(self) -> None:
        use_case, players, _, _, _, _ = _build_use_case()
        _seed_player(players, length_cm=4_100, thickness_level=1)

        result = await use_case.execute(UpgradeThicknessInput(tg_id=42))

        # Тот же объект, что лежит в FakePlayerRepository (после save).
        stored = await players.get_by_tg_id(42)
        assert stored is not None
        assert stored.thickness.level == 2
        assert stored.length.cm == 100
        assert result.player_after.thickness.level == stored.thickness.level


@pytest.mark.asyncio
class TestUpgradeThicknessExpectedCost:
    async def test_passes_when_expected_matches(self) -> None:
        use_case, players, _, _, _, _ = _build_use_case()
        _seed_player(players, length_cm=4_100, thickness_level=1)

        result = await use_case.execute(
            UpgradeThicknessInput(tg_id=42, expected_cost_cm=4_000),
        )

        assert result.cost_cm == 4_000

    async def test_raises_when_expected_does_not_match(self) -> None:
        use_case, players, _, audit, _, _ = _build_use_case()
        _seed_player(players, length_cm=4_100, thickness_level=1)

        with pytest.raises(ConcurrencyError) as exc_info:
            await use_case.execute(
                UpgradeThicknessInput(tg_id=42, expected_cost_cm=3_000),
            )

        assert "3000" in str(exc_info.value)
        assert "4000" in str(exc_info.value)
        # ничего не сохранилось / не записалось в аудит.
        assert audit.entries == []
        stored = await players.get_by_tg_id(42)
        assert stored is not None
        assert stored.thickness.level == 1
        assert stored.length.cm == 4_100


@pytest.mark.asyncio
class TestUpgradeThicknessErrors:
    async def test_player_not_found(self) -> None:
        use_case, _, _, audit, _, _ = _build_use_case()

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(UpgradeThicknessInput(tg_id=999))
        assert audit.entries == []

    async def test_insufficient_length_after_spend(self) -> None:
        # cost(1→2) = 4000. После списания должно остаться ≥ 20 см → нужно ≥ 4020 см.
        use_case, players, _, audit, _, _ = _build_use_case()
        _seed_player(players, length_cm=4_019, thickness_level=1)

        with pytest.raises(InsufficientLengthError) as exc_info:
            await use_case.execute(UpgradeThicknessInput(tg_id=42))

        assert exc_info.value.cost_cm == 4_000
        assert exc_info.value.length_cm == 4_019
        assert exc_info.value.action == "thickness_upgrade"
        # игрок не изменился, аудит чист.
        assert audit.entries == []
        stored = await players.get_by_tg_id(42)
        assert stored is not None
        assert stored.thickness.level == 1
        assert stored.length.cm == 4_019

    async def test_insufficient_at_exact_boundary(self) -> None:
        # 4019: остаток после списания = 19 < 20 — ошибка.
        use_case, players, _, _, _, _ = _build_use_case()
        _seed_player(players, length_cm=4_019, thickness_level=1)

        with pytest.raises(InsufficientLengthError):
            await use_case.execute(UpgradeThicknessInput(tg_id=42))

    async def test_passes_at_exact_boundary_plus_1(self) -> None:
        # 4020: остаток после списания = 20 = MIN — проходит.
        use_case, players, _, _, _, _ = _build_use_case()
        _seed_player(players, length_cm=4_020, thickness_level=1)

        result = await use_case.execute(UpgradeThicknessInput(tg_id=42))

        assert result.player_after.length.cm == 20
        assert result.new_thickness == 2


@pytest.mark.asyncio
class TestUpgradeThicknessAnticheatGate:
    """Soft-ban-гейт `AnticheatGuard` (Спринт 1.6.E, ГДД §3.3.5).

    Если игрок в активном soft-ban-е — `UpgradeThickness` бросает
    `AnticheatSoftBanError` ДО любого списания / mutate / audit.
    """

    async def test_active_ban_raises_before_mutate(self) -> None:
        use_case, players, _, audit, _, _ = _build_use_case()
        ban_until = _NOW + timedelta(days=14)
        _seed_player(
            players,
            length_cm=10_000,
            thickness_level=1,
            anticheat_ban_until=ban_until,
        )

        with pytest.raises(AnticheatSoftBanError) as exc_info:
            await use_case.execute(UpgradeThicknessInput(tg_id=42))

        assert exc_info.value.tg_id == 42
        assert exc_info.value.banned_until == ban_until
        # ничего не сохранилось / не записалось в аудит.
        assert audit.entries == []
        stored = await players.get_by_tg_id(42)
        assert stored is not None
        assert stored.thickness.level == 1
        assert stored.length.cm == 10_000

    async def test_expired_ban_passes(self) -> None:
        use_case, players, _, _, _, _ = _build_use_case()
        # Бан истёк час назад — должен пропускать.
        _seed_player(
            players,
            length_cm=10_000,
            thickness_level=1,
            anticheat_ban_until=_NOW - timedelta(hours=1),
        )

        result = await use_case.execute(UpgradeThicknessInput(tg_id=42))

        assert result.new_thickness == 2
        assert result.cost_cm == 4_000

    async def test_no_ban_passes(self) -> None:
        use_case, players, _, _, _, _ = _build_use_case()
        _seed_player(
            players,
            length_cm=10_000,
            thickness_level=1,
            anticheat_ban_until=None,
        )

        result = await use_case.execute(UpgradeThicknessInput(tg_id=42))

        assert result.new_thickness == 2

    async def test_active_ban_check_runs_before_cost_check(self) -> None:
        """Если игрок в бане И не хватает длины — приоритет у бана."""

        use_case, players, _, audit, _, _ = _build_use_case()
        # Длины не хватает (нужно 4020, есть 1000) И активен бан.
        _seed_player(
            players,
            length_cm=1_000,
            thickness_level=1,
            anticheat_ban_until=_NOW + timedelta(days=1),
        )

        # Должен бросить именно `AnticheatSoftBanError`, а не `InsufficientLengthError`.
        with pytest.raises(AnticheatSoftBanError):
            await use_case.execute(UpgradeThicknessInput(tg_id=42))
        assert audit.entries == []
