"""Юнит-тесты `RegisterReferral` (Спринт 2.4.C).

Покрывают acceptance ПД 2.4.C:
- happy-path: новый игрок + существующий реферер → создаётся `Referral`,
  `signup_granted_at` остаётся `None`;
- self-referral (`referrer == referred`) → `SelfReferralError`;
- реферер не существует → `ReferrerNotRegisteredError`;
- новичок не существует → `PlayerNotFoundError` (баг в caller-е);
- повторный вызов с тем же `referred` → `ReferralAlreadyRegistered`,
  существующая запись возвращается без побочных эффектов;
- race-условие (UNIQUE-violation на add) → `ReferralAlreadyRegistered`
  с записью-победителем гонки.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.dto.inputs import RegisterReferralInput
from pipirik_wars.application.referral import (
    RegisterReferral,
)
from pipirik_wars.application.referral.register import (
    ReferralAlreadyRegistered,
    ReferralRegistered,
)
from pipirik_wars.domain.player import Player, PlayerStatus, Thickness
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.player.value_objects import Length, Username
from pipirik_wars.domain.referral import (
    Referral,
    ReferrerNotRegisteredError,
    SelfReferralError,
)
from tests.fakes import (
    FakeClock,
    FakePlayerRepository,
    FakeReferralRepository,
    FakeUnitOfWork,
)

NOW = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)


def _make_player(*, player_id: int, tg_id: int) -> Player:
    return Player(
        id=player_id,
        tg_id=tg_id,
        username=Username(value=f"user{player_id}"),
        length=Length(cm=2),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


def _build() -> tuple[
    RegisterReferral,
    FakePlayerRepository,
    FakeReferralRepository,
    FakeUnitOfWork,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    referrals = FakeReferralRepository()
    use_case = RegisterReferral(
        uow=uow,
        players=players,
        referrals=referrals,
        clock=FakeClock(NOW),
    )
    return use_case, players, referrals, uow


@pytest.mark.asyncio
class TestRegisterReferralHappyPath:
    async def test_creates_referral_when_both_players_exist(self) -> None:
        use_case, players, referrals, uow = _build()
        players.rows.append(_make_player(player_id=1, tg_id=1001))
        players.rows.append(_make_player(player_id=2, tg_id=2002))

        result = await use_case.execute(
            RegisterReferralInput(referrer_tg_id=1001, referred_tg_id=2002)
        )

        assert isinstance(result, ReferralRegistered)
        assert result.referral.referrer_id == 1
        assert result.referral.referred_id == 2
        assert result.referral.signup_granted_at is None
        assert result.referral.last_milestone_thickness == 0
        assert len(referrals.items) == 1
        assert uow.commits == 1


@pytest.mark.asyncio
class TestRegisterReferralValidation:
    async def test_self_referral_at_dto_level(self) -> None:
        # DTO bouncer
        with pytest.raises(ValueError, match="must differ"):
            RegisterReferralInput(referrer_tg_id=1001, referred_tg_id=1001)

    async def test_self_referral_at_use_case_level(self) -> None:
        # Construct DTO via model_construct to bypass DTO validation,
        # then use-case must re-check (defense-in-depth).
        use_case, _, _, _ = _build()
        bypass = RegisterReferralInput.model_construct(referrer_tg_id=1001, referred_tg_id=1001)
        with pytest.raises(SelfReferralError):
            await use_case.execute(bypass)

    async def test_referrer_not_registered_raises(self) -> None:
        use_case, players, _, _ = _build()
        # Только новичок есть, реферера нет.
        players.rows.append(_make_player(player_id=2, tg_id=2002))

        with pytest.raises(ReferrerNotRegisteredError) as exc:
            await use_case.execute(RegisterReferralInput(referrer_tg_id=1001, referred_tg_id=2002))
        assert exc.value.referrer_tg_id == 1001

    async def test_referred_not_registered_raises(self) -> None:
        use_case, players, _, _ = _build()
        # Реферер есть, новичка нет (баг в caller-е, но defensive).
        players.rows.append(_make_player(player_id=1, tg_id=1001))

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(RegisterReferralInput(referrer_tg_id=1001, referred_tg_id=2002))


@pytest.mark.asyncio
class TestRegisterReferralIdempotency:
    async def test_repeat_with_same_referred_returns_existing(self) -> None:
        use_case, players, referrals, _ = _build()
        players.rows.append(_make_player(player_id=1, tg_id=1001))
        players.rows.append(_make_player(player_id=2, tg_id=2002))

        first = await use_case.execute(
            RegisterReferralInput(referrer_tg_id=1001, referred_tg_id=2002)
        )
        second = await use_case.execute(
            RegisterReferralInput(referrer_tg_id=1001, referred_tg_id=2002)
        )

        assert isinstance(first, ReferralRegistered)
        assert isinstance(second, ReferralAlreadyRegistered)
        assert second.referral.id == first.referral.id
        assert len(referrals.items) == 1

    async def test_different_referrer_for_same_referred_returns_existing(self) -> None:
        """Если новичок уже рефнут, повторный /start с другим ref_<id> игнорируется."""
        use_case, players, referrals, _ = _build()
        players.rows.append(_make_player(player_id=1, tg_id=1001))
        players.rows.append(_make_player(player_id=3, tg_id=3003))
        players.rows.append(_make_player(player_id=2, tg_id=2002))

        first = await use_case.execute(
            RegisterReferralInput(referrer_tg_id=1001, referred_tg_id=2002)
        )
        second = await use_case.execute(
            RegisterReferralInput(referrer_tg_id=3003, referred_tg_id=2002)
        )

        assert isinstance(first, ReferralRegistered)
        assert isinstance(second, ReferralAlreadyRegistered)
        # Победил первый реферер, не второй.
        assert second.referral.referrer_id == 1
        assert len(referrals.items) == 1

    async def test_race_handled_via_already_registered_result(self) -> None:
        """Имитация race: get_by_referred_id вернул None, но add() поймал
        UNIQUE-violation. Use-case должен сделать re-fetch и вернуть
        `ReferralAlreadyRegistered`.
        """
        use_case, players, referrals, _ = _build()
        players.rows.append(_make_player(player_id=1, tg_id=1001))
        players.rows.append(_make_player(player_id=2, tg_id=2002))

        # Симулируем гонку: подкладываем запись прямо в items минуя add(),
        # но get_by_referred_id всё ещё «вернёт None» в момент первого
        # вызова — для этого моноким-патчим repo.
        original_get = referrals.get_by_referred_id
        original_add = referrals.add
        seen_first_get = {"value": False}

        async def _shadowed_get(referred_id: int) -> Referral | None:
            if not seen_first_get["value"]:
                seen_first_get["value"] = True
                return None
            return await original_get(referred_id)

        async def _add_after_inserting_competitor(referral: Referral) -> Referral:
            # Конкурент успел вставить.
            referrals.items.append(
                Referral(
                    id=999,
                    referrer_id=999,  # «другой» реферер
                    referred_id=referral.referred_id,
                    created_at=NOW,
                )
            )
            return await original_add(referral)

        referrals.get_by_referred_id = _shadowed_get  # type: ignore[method-assign]
        referrals.add = _add_after_inserting_competitor  # type: ignore[method-assign]

        result = await use_case.execute(
            RegisterReferralInput(referrer_tg_id=1001, referred_tg_id=2002)
        )

        assert isinstance(result, ReferralAlreadyRegistered)
        assert result.referral.referrer_id == 999
