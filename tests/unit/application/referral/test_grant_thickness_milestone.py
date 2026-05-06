"""Юнит-тесты `GrantReferralThicknessMilestone` (Спринт 2.4.C).

Покрывают acceptance ПД 2.4.C:
- happy-path для уровня 3: реферер получает +10 см, milestone-маркер обновляется;
- happy-path для уровня 5: реферер получает +30 см;
- толщина не входит в milestone-список (1, 2, 4) → `ReferralMilestoneNotApplicable`;
- идемпотентность: повторный вызов на той же толщине →
  `MilestoneAlreadyGrantedError`;
- игрок без реферера → `ReferralMilestoneNotApplicable`;
- player not found → `PlayerNotFoundError`;
- понижение milestone (5→3 после 5→3) → `MilestoneAlreadyGrantedError`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.dto.inputs import (
    GrantReferralThicknessMilestoneInput,
)
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.referral import (
    GrantReferralThicknessMilestone,
    ReferralMilestoneGranted,
    ReferralMilestoneNotApplicable,
)
from pipirik_wars.domain.player import Player, PlayerStatus, Thickness
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.player.value_objects import Length, Username
from pipirik_wars.domain.referral import (
    MilestoneAlreadyGrantedError,
    Referral,
)
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.domain.shared.ports.audit import AuditSource
from tests.fakes import (
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClock,
    FakeIdempotencyKey,
    FakePlayerRepository,
    FakeReferralRepository,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

NOW = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)


def _make_player(*, player_id: int, tg_id: int, length_cm: int = 10) -> Player:
    return Player(
        id=player_id,
        tg_id=tg_id,
        username=Username(value=f"user{player_id}"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


def _build() -> tuple[
    GrantReferralThicknessMilestone,
    FakePlayerRepository,
    FakeReferralRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    referrals = FakeReferralRepository()
    audit = FakeAuditLogger()
    balance = FakeBalanceConfig(build_valid_balance())
    length_granter = AddLength(
        uow=uow,
        players=players,
        anticheat=FakeAnticheatRepository(),
        audit=audit,
        balance=balance,
        clock=FakeClock(NOW),
        idempotency=FakeIdempotencyKey(),
        admin_alerter=FakeAnticheatAdminAlerter(),
    )
    use_case = GrantReferralThicknessMilestone(
        uow=uow,
        players=players,
        referrals=referrals,
        length_granter=length_granter,
        balance=balance,
    )
    return use_case, players, referrals, audit, uow


@pytest.mark.asyncio
class TestGrantReferralMilestoneHappyPath:
    @pytest.mark.parametrize(
        ("thickness", "expected_bonus"),
        [(3, 10), (5, 30)],
    )
    async def test_grants_correct_bonus_for_milestone(
        self, thickness: int, expected_bonus: int
    ) -> None:
        use_case, players, referrals, audit, _ = _build()
        referrer = _make_player(player_id=1, tg_id=1001, length_cm=20)
        referred = _make_player(player_id=2, tg_id=2002, length_cm=2)
        players.rows.append(referrer)
        players.rows.append(referred)
        referrals.items.append(Referral(id=1, referrer_id=1, referred_id=2, created_at=NOW))

        result = await use_case.execute(
            GrantReferralThicknessMilestoneInput(referred_tg_id=2002, new_thickness_level=thickness)
        )

        assert isinstance(result, ReferralMilestoneGranted)
        assert result.thickness == thickness
        assert result.referrer_bonus_cm == expected_bonus

        new_referrer = next(p for p in players.rows if p.id == 1)
        assert new_referrer.length.cm == 20 + expected_bonus
        # Длина новичка не меняется.
        new_referred = next(p for p in players.rows if p.id == 2)
        assert new_referred.length.cm == 2
        # Маркер обновлён.
        assert result.referral.last_milestone_thickness == thickness
        # 1 audit-запись с REFERRAL_THICKNESS.
        thick_entries = [
            e
            for e in audit.entries
            if e.action == AuditAction.LENGTH_GRANT and e.source == AuditSource.REFERRAL_THICKNESS
        ]
        assert len(thick_entries) == 1


@pytest.mark.asyncio
class TestGrantReferralMilestoneNotApplicable:
    @pytest.mark.parametrize("level", [1, 2, 4, 6, 7, 10])
    async def test_thickness_not_in_milestones_returns_not_applicable(self, level: int) -> None:
        use_case, players, referrals, audit, _ = _build()
        players.rows.append(_make_player(player_id=1, tg_id=1001))
        players.rows.append(_make_player(player_id=2, tg_id=2002))
        referrals.items.append(Referral(id=1, referrer_id=1, referred_id=2, created_at=NOW))

        result = await use_case.execute(
            GrantReferralThicknessMilestoneInput(referred_tg_id=2002, new_thickness_level=level)
        )

        assert isinstance(result, ReferralMilestoneNotApplicable)
        # Никаких audit-записей.
        assert audit.entries == []

    async def test_player_without_referrer_returns_not_applicable(self) -> None:
        """Если игрока никто не приглашал, повышение толщины ничего не начисляет."""
        use_case, players, _, audit, _ = _build()
        players.rows.append(_make_player(player_id=2, tg_id=2002))

        result = await use_case.execute(
            GrantReferralThicknessMilestoneInput(referred_tg_id=2002, new_thickness_level=3)
        )

        assert isinstance(result, ReferralMilestoneNotApplicable)
        assert audit.entries == []


@pytest.mark.asyncio
class TestGrantReferralMilestoneIdempotency:
    async def test_repeat_same_milestone_raises_already_granted(self) -> None:
        use_case, players, referrals, _, _ = _build()
        players.rows.append(_make_player(player_id=1, tg_id=1001))
        players.rows.append(_make_player(player_id=2, tg_id=2002))
        referrals.items.append(
            Referral(
                id=1,
                referrer_id=1,
                referred_id=2,
                created_at=NOW,
                last_milestone_thickness=3,
            )
        )

        with pytest.raises(MilestoneAlreadyGrantedError) as exc:
            await use_case.execute(
                GrantReferralThicknessMilestoneInput(referred_tg_id=2002, new_thickness_level=3)
            )
        assert exc.value.referred_id == 2
        assert exc.value.thickness == 3

    async def test_lower_milestone_after_higher_raises_already_granted(self) -> None:
        """Игрок 5→3: milestone 3 не должен пере-выдаваться рефереру."""
        use_case, players, referrals, _, _ = _build()
        players.rows.append(_make_player(player_id=1, tg_id=1001))
        players.rows.append(_make_player(player_id=2, tg_id=2002))
        referrals.items.append(
            Referral(
                id=1,
                referrer_id=1,
                referred_id=2,
                created_at=NOW,
                last_milestone_thickness=5,
            )
        )

        with pytest.raises(MilestoneAlreadyGrantedError):
            await use_case.execute(
                GrantReferralThicknessMilestoneInput(referred_tg_id=2002, new_thickness_level=3)
            )


@pytest.mark.asyncio
class TestGrantReferralMilestoneErrors:
    async def test_player_not_found(self) -> None:
        use_case, _, _, _, _ = _build()
        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(
                GrantReferralThicknessMilestoneInput(referred_tg_id=9999, new_thickness_level=3)
            )
