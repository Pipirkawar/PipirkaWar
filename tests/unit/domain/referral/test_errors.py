"""Юнит-тесты доменных ошибок реферальной системы (Спринт 2.4.A)."""

from __future__ import annotations

from pipirik_wars.domain.referral import (
    MilestoneAlreadyGrantedError,
    ReferralAlreadyExistsError,
    ReferralError,
    ReferrerNotRegisteredError,
    SelfReferralError,
    SignupBonusAlreadyGrantedError,
)


class TestErrorHierarchy:
    """Все доменные ошибки наследуются от `ReferralError`."""

    def test_self_referral_is_referral_error(self) -> None:
        assert issubclass(SelfReferralError, ReferralError)

    def test_already_exists_is_referral_error(self) -> None:
        assert issubclass(ReferralAlreadyExistsError, ReferralError)

    def test_referrer_not_registered_is_referral_error(self) -> None:
        assert issubclass(ReferrerNotRegisteredError, ReferralError)

    def test_signup_already_granted_is_referral_error(self) -> None:
        assert issubclass(SignupBonusAlreadyGrantedError, ReferralError)

    def test_milestone_already_granted_is_referral_error(self) -> None:
        assert issubclass(MilestoneAlreadyGrantedError, ReferralError)


class TestErrorPayloads:
    """Все ошибки сохраняют payload-поля для логирования."""

    def test_self_referral_carries_player_id(self) -> None:
        exc = SelfReferralError(player_id=42)
        assert exc.player_id == 42
        assert "42" in str(exc)

    def test_already_exists_carries_referred_id(self) -> None:
        exc = ReferralAlreadyExistsError(referred_id=99)
        assert exc.referred_id == 99
        assert "99" in str(exc)

    def test_referrer_not_registered_carries_tg_id(self) -> None:
        exc = ReferrerNotRegisteredError(referrer_tg_id=12345)
        assert exc.referrer_tg_id == 12345
        assert "12345" in str(exc)

    def test_signup_already_granted_carries_referred_id(self) -> None:
        exc = SignupBonusAlreadyGrantedError(referred_id=7)
        assert exc.referred_id == 7
        assert "7" in str(exc)

    def test_milestone_already_granted_carries_referred_id_and_thickness(self) -> None:
        exc = MilestoneAlreadyGrantedError(referred_id=3, thickness=5)
        assert exc.referred_id == 3
        assert exc.thickness == 5
        assert "3" in str(exc)
        assert "5" in str(exc)
