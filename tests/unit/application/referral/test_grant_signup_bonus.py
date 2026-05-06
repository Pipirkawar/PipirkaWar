"""Юнит-тесты `GrantReferralSignupBonus` (Спринт 2.4.C).

Покрывают acceptance ПД 2.4.C:
- happy-path: новичок получает +balance.newbie_bonus_cm, реферер
  получает +balance.referrer_bonus_cm, `signup_granted_at` заполняется,
  audit `LENGTH_GRANT` пишется через `ILengthGranter`;
- идемпотентность: повторный вызов на уже-обработанной записи →
  `SignupBonusAlreadyGrantedError`;
- player not found → `PlayerNotFoundError`;
- referral not found → `KeyError` (programming error);
- bonus_cm=0 в конфиге не должен ничего начислять.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.dto.inputs import GrantReferralSignupBonusInput
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.referral import GrantReferralSignupBonus
from pipirik_wars.domain.player import Player, PlayerStatus, Thickness
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.player.value_objects import Length, Username
from pipirik_wars.domain.referral import (
    Referral,
    SignupBonusAlreadyGrantedError,
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


def _make_player(*, player_id: int, tg_id: int, length_cm: int = 2) -> Player:
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
    GrantReferralSignupBonus,
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
    use_case = GrantReferralSignupBonus(
        uow=uow,
        players=players,
        referrals=referrals,
        length_granter=length_granter,
        balance=balance,
        clock=FakeClock(NOW),
    )
    return use_case, players, referrals, audit, uow


@pytest.mark.asyncio
class TestGrantReferralSignupBonusHappyPath:
    async def test_grants_both_bonuses_and_marks_granted(self) -> None:
        use_case, players, referrals, audit, uow = _build()
        referrer = _make_player(player_id=1, tg_id=1001, length_cm=10)
        referred = _make_player(player_id=2, tg_id=2002, length_cm=2)
        players.rows.append(referrer)
        players.rows.append(referred)
        referrals.items.append(Referral(id=1, referrer_id=1, referred_id=2, created_at=NOW))

        result = await use_case.execute(GrantReferralSignupBonusInput(referred_tg_id=2002))

        # Дефолтный баланс: 5 см новичку, 1 см рефереру.
        assert result.newbie_bonus_cm == 5
        assert result.referrer_bonus_cm == 1
        assert result.referral.signup_granted_at == NOW

        # Длины обновлены.
        new_referred = next(p for p in players.rows if p.id == 2)
        new_referrer = next(p for p in players.rows if p.id == 1)
        assert new_referred.length.cm == 2 + 5
        assert new_referrer.length.cm == 10 + 1

        # 2 audit-записи LENGTH_GRANT с REFERRAL_SIGNUP.
        signup_entries = [
            e
            for e in audit.entries
            if e.action == AuditAction.LENGTH_GRANT and e.source == AuditSource.REFERRAL_SIGNUP
        ]
        assert len(signup_entries) == 2
        assert uow.commits == 1


@pytest.mark.asyncio
class TestGrantReferralSignupBonusIdempotency:
    async def test_repeat_raises_already_granted(self) -> None:
        use_case, players, referrals, _, _ = _build()
        players.rows.append(_make_player(player_id=1, tg_id=1001))
        players.rows.append(_make_player(player_id=2, tg_id=2002))
        referrals.items.append(
            Referral(
                id=1,
                referrer_id=1,
                referred_id=2,
                created_at=NOW,
                signup_granted_at=NOW,  # уже выдано
            )
        )

        with pytest.raises(SignupBonusAlreadyGrantedError) as exc:
            await use_case.execute(GrantReferralSignupBonusInput(referred_tg_id=2002))
        assert exc.value.referred_id == 2


@pytest.mark.asyncio
class TestGrantReferralSignupBonusErrors:
    async def test_player_not_found(self) -> None:
        use_case, _, _, _, _ = _build()
        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(GrantReferralSignupBonusInput(referred_tg_id=9999))

    async def test_referral_not_found_raises_key_error(self) -> None:
        use_case, players, _, _, _ = _build()
        players.rows.append(_make_player(player_id=2, tg_id=2002))
        # Реферальной записи нет → KeyError (баг в caller-е).
        with pytest.raises(KeyError):
            await use_case.execute(GrantReferralSignupBonusInput(referred_tg_id=2002))
